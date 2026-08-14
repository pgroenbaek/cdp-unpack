"""
This file is part of CdpUnpack.

Copyright (C) 2026 Peter Grønbæk Andersen <peter@grnbk.io>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import pytest

from cdpunpack.error import CdpError
from cdpunpack.bitreader import BitReader
from cdpunpack.huffman import AdaptiveHuffmanTree
from cdpunpack.lzss import (
    LENGTH_TABLE,
    copy_match,
    decompress_bitstream,
    decompress_huffman,
    decompress_lzss,
    mode_params,
)


def pack_bits(bits: list[int]) -> bytes:
    """
    Pack bits LSB-first, matching BitReader.
    """
    result = bytearray((len(bits) + 7) // 8)

    for i, bit in enumerate(bits):
        if bit:
            result[i // 8] |= 1 << (i % 8)

    return bytes(result)


def bits_for_byte(value: int) -> list[int]:
    return [(value >> i) & 1 for i in range(8)]


def make_mode0_stream(items: list[tuple[str, int, int | None]]) -> bytes:
    """
    Build a mode-0 bitstream.

    items:
        ("literal", value, None)
        ("match", len_code, distance)

    The first 32 bits are flags. Payload follows afterwards.
    """
    flags = [0] * 32
    payload = []
    flag_pos = 0

    for kind, value, distance in items:
        if kind == "literal":
            # 0 = literal
            flags[flag_pos] = 0
            payload.extend(bits_for_byte(value))
            flag_pos += 1

        elif kind == "match":
            # 1 = match, followed by 3-bit length code.
            flags[flag_pos] = 1
            flag_pos += 1

            if value >= 7:
                # 111 means escape, followed by an 8-bit length.
                flags[flag_pos] = 1
                flags[flag_pos + 1] = 1
                flags[flag_pos + 2] = 1
                flag_pos += 3
                payload.extend(bits_for_byte(value))
            else:
                flags[flag_pos] = value & 1
                flags[flag_pos + 1] = (value >> 1) & 1
                flags[flag_pos + 2] = (value >> 2) & 1
                flag_pos += 3

            payload.extend(bits_for_byte(distance))

        else:
            raise AssertionError(f"unknown item type: {kind}")

        if flag_pos > 32:
            raise AssertionError("too many flag bits for one block")

    return pack_bits(flags) + pack_bits(payload)


def make_mode12_literal_stream(data: bytes) -> bytes:
    """
    Build a mode-1/mode-2 literal-only stream.

    Each literal consumes two flag bits: 00.

    The current Python decoder uses a single 32-bit flag word, so this
    fixture is intentionally limited to 16 literals.
    """
    if len(data) > 16:
        raise AssertionError(
            "mode 1/2 literal fixture cannot contain more than "
            "16 literals with the current decoder"
        )

    return b"\x00\x00\x00\x00" + data


def make_mode12_stream(
    items: list[tuple[str, int, int | bytes | None]],
) -> bytes:
    """
    Build one mode-1/mode-2 bitstream block.

    Flag encoding used by decompress_bitstream():

        00 = literal
        01 = short copy
        1  = back reference

    The decoder reads one 32-bit flag word followed by the payload.
    """
    flags = [0] * 32
    payload = []
    flag_pos = 0

    for kind, value, extra in items:
        if kind == "literal":
            if flag_pos + 2 > 32:
                raise AssertionError("too many flag bits")

            # 00 = literal
            flags[flag_pos] = 0
            flags[flag_pos + 1] = 0
            flag_pos += 2

            payload.extend(bits_for_byte(value))

        elif kind == "short":
            if flag_pos + 2 > 32:
                raise AssertionError("too many flag bits")

            data = bytes(extra)

            if len(data) != value + 3:
                raise AssertionError(
                    "short copy payload length does not match len_code"
                )

            # 01 = short copy
            flags[flag_pos] = 0
            flags[flag_pos + 1] = 1
            flag_pos += 2

            payload.extend(bits_for_byte(value))

            for byte in data:
                payload.extend(bits_for_byte(byte))

        elif kind == "match":
            if flag_pos + 1 > 32:
                raise AssertionError("too many flag bits")

            # 1 = back reference
            flags[flag_pos] = 1
            flag_pos += 1

            word = value

            payload.extend(bits_for_byte(word & 0xFF))
            payload.extend(bits_for_byte((word >> 8) & 0xFF))

        else:
            raise AssertionError(f"unknown item type: {kind}")

    return pack_bits(flags) + pack_bits(payload)


def huffman_symbol_bits(tree: AdaptiveHuffmanTree, symbol: int) -> list[int]:
    """
    Return the current tree path used to decode `symbol`.
    """
    node = tree.symbol_to_node[symbol]
    bits = []

    while node != tree.root_idx:
        parent = tree.parent[node]

        if parent >= tree.total_nodes:
            raise AssertionError("invalid parent while constructing fixture")

        if tree.child[parent] == node:
            bits.append(0)
        else:
            bits.append(1)

        node = parent

    bits.reverse()
    return bits


def make_huffman_literal_stream(
    data: bytes,
    num_dist_symbols: int,
) -> bytes:
    """
    Construct a valid adaptive-Huffman literal stream.

    This is a test fixture generator, not a compressor.
    """
    lit_tree = AdaptiveHuffmanTree(273)
    dist_tree = AdaptiveHuffmanTree(num_dist_symbols)

    del dist_tree  # No distance symbols are needed for literals.

    bits = []

    for byte in data:
        bits.extend(huffman_symbol_bits(lit_tree, byte))
        lit_tree.update(byte)

    return pack_bits(bits)


def make_huffman_symbol_stream(
    symbols: list[int],
    num_dist_symbols: int = 16,
) -> bytes:
    """
    Construct a stream containing the given literal-tree symbols.
    """
    tree = AdaptiveHuffmanTree(273)
    bits = []

    for symbol in symbols:
        bits.extend(huffman_symbol_bits(tree, symbol))
        tree.update(symbol)

    return pack_bits(bits)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (0, (8, 16, 4)),
        (1, (12, 64, 6)),
        (2, (14, 64, 8)),
    ],
)
def test_mode_params(mode, expected):
    assert mode_params(mode) == expected


@pytest.mark.parametrize("mode", [-1, 3, 4, 255])
def test_mode_params_invalid(mode):
    with pytest.raises(CdpError, match="invalid compression mode"):
        mode_params(mode)


def test_copy_match():
    output = bytearray(b"hello")

    copy_match(output, 5, 5, 100)

    assert output == b"hellohello"


def test_copy_match_overlapping():
    output = bytearray(b"a")

    copy_match(output, 1, 10, 100)

    assert output == b"aaaaaaaaaaa"


def test_copy_match_respects_max_size():
    output = bytearray(b"abc")

    copy_match(output, 1, 100, 5)

    assert len(output) == 5


def test_copy_match_distance_beyond_output():
    output = bytearray()

    copy_match(output, 10, 4, 100)

    assert output == b"\x00\x00\x00\x00"


def test_round_trip_empty():
    data = b""

    compressed = bytes([0x20])

    assert decompress_lzss(compressed, len(data)) == data


def test_round_trip_single_byte():
    data = b"\x42"

    compressed = bytes([0x20, 0x42])

    assert decompress_lzss(compressed, len(data)) == data


def test_round_trip_store_mode():
    data = b"stored uncompressed"

    compressed = bytes([0x20]) + data

    assert compressed[0] == 0x20
    assert decompress_lzss(compressed, len(data)) == data


def test_store_mode_truncated():
    compressed = bytes([0x20]) + b"short"

    with pytest.raises(
        CdpError,
        match=r"stored blob is shorter than declared uncompressed size",
    ):
        decompress_lzss(compressed, 100)


def test_empty_lzss_blob():
    with pytest.raises(CdpError, match="empty LZSS blob"):
        decompress_lzss(b"", 0)


def test_bitstream_mode0_single_literal():
    stream = make_mode0_stream([
        ("literal", 0x42, None),
    ])

    result = decompress_bitstream(
        stream,
        1,
        dist_bits_total=8,
        dist_extra_bits=0,
    )

    assert result == b"\x42"


def test_bitstream_mode0_hello():
    data = b"hello world hello hello world"

    stream = make_mode0_stream([
        ("literal", byte, None)
        for byte in data
    ])

    result = decompress_bitstream(
        stream,
        len(data),
        dist_bits_total=8,
        dist_extra_bits=0,
    )

    assert result == data


def test_bitstream_mode0_match():
    # Literal 'a', followed by a distance-1 match of length 4.
    #
    # len_code = 1 => match length = 1 + 3 = 4
    stream = make_mode0_stream([
        ("literal", ord("a"), None),
        ("match", 1, 1),
    ])

    result = decompress_bitstream(
        stream,
        5,
        dist_bits_total=8,
        dist_extra_bits=0,
    )

    assert result == b"aaaaa"


def test_bitstream_mode0_escape():
    # len_code == 7 triggers the explicit 8-bit length.
    #
    # 7 + 3 = 10 bytes copied.
    stream = make_mode0_stream([
        ("literal", ord("a"), None),
        ("match", 7, 1),
    ])

    result = decompress_bitstream(
        stream,
        11,
        dist_bits_total=8,
        dist_extra_bits=0,
    )

    assert result == b"a" * 11


def test_bitstream_mode0_multiple_literals():
    data = bytes(range(1, 32))

    stream = make_mode0_stream([
        ("literal", byte, None)
        for byte in data
    ])

    result = decompress_bitstream(
        stream,
        len(data),
        dist_bits_total=8,
        dist_extra_bits=0,
    )

    assert result == data


@pytest.mark.parametrize(
    ("mode", "dist_bits_total", "dist_extra_bits"),
    [
        (1, 12, 6),
        (2, 14, 8),
    ],
)
def test_bitstream_literal(mode, dist_bits_total, dist_extra_bits):
    data = b"hello world"

    stream = make_mode12_literal_stream(data)

    result = decompress_bitstream(
        stream,
        len(data),
        dist_bits_total,
        dist_extra_bits,
    )

    assert result == data


@pytest.mark.parametrize(
    ("mode", "dist_bits", "dist_extra"),
    [
        (1, 12, 6),
        (2, 14, 8),
    ],
)
def test_bitstream_short_copy(mode, dist_bits, dist_extra):
    data = b"abcabc"

    stream = make_mode12_stream([
        ("literal", ord("a"), None),
        ("literal", ord("b"), None),
        ("literal", ord("c"), None),
        ("short", 0, b"abc"),
    ])

    result = decompress_bitstream(
        stream,
        len(data),
        dist_bits_total=dist_bits,
        dist_extra_bits=dist_extra,
    )

    assert result == data


@pytest.mark.parametrize(
    ("mode", "dist_bits", "dist_extra"),
    [
        (1, 12, 6),
        (2, 14, 8),
    ],
)
def test_bitstream_back_reference(mode, dist_bits, dist_extra):
    offset_shift = min(dist_bits, 15)

    # distance = 1
    # len_code = 1
    # match_len = 1 + 3 = 4
    word = 1 | (1 << offset_shift)

    stream = make_mode12_stream([
        ("literal", ord("a"), None),
        ("match", word, None),
    ])

    result = decompress_bitstream(
        stream,
        5,
        dist_bits_total=dist_bits,
        dist_extra_bits=dist_extra,
    )

    assert result == b"aaaaa"


@pytest.mark.parametrize(
    ("mode", "dist_bits", "dist_extra"),
    [
        (1, 12, 6),
        (2, 14, 8),
    ],
)
def test_bitstream_long_match_escape(mode, dist_bits, dist_extra):
    # Force len_code == len_overflow so the decoder reads the
    # following 8-bit length.
    len_overflow = (1 << (16 - dist_bits)) - 1
    offset_shift = min(dist_bits, 15)

    word = 1 | (len_overflow << offset_shift)

    # Escape length byte = 7 => match length = 10.
    flags = [0, 0, 1]
    flags.extend([0] * (32 - len(flags)))

    payload = (
        bits_for_byte(ord("a"))
        + bits_for_byte(word & 0xFF)
        + bits_for_byte((word >> 8) & 0xFF)
        + bits_for_byte(7)
    )

    stream = pack_bits(flags) + pack_bits(payload)

    result = decompress_bitstream(
        stream,
        11,
        dist_bits_total=dist_bits,
        dist_extra_bits=dist_extra,
    )

    assert result == b"a" * 11


@pytest.mark.parametrize(
    ("mode", "num_dist_symbols", "dist_extra_bits"),
    [
        (0, 16, 4),
        (1, 64, 6),
        (2, 64, 8),
    ],
)
def test_huffman_literals(mode, num_dist_symbols, dist_extra_bits):
    data = b"hello world"

    stream = make_huffman_literal_stream(
        data,
        num_dist_symbols,
    )

    result = decompress_huffman(
        stream,
        len(data),
        dist_bits_total=mode_params(mode)[0],
        num_dist_symbols=num_dist_symbols,
        dist_extra_bits=dist_extra_bits,
    )

    assert result == data


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("level", [7, 8, 9])
def test_huffman_dispatch(mode, level):
    data = b"hello world"

    dist_bits, num_dist_symbols, dist_extra_bits = mode_params(mode)

    stream = make_huffman_literal_stream(
        data,
        num_dist_symbols,
    )

    compressed = bytes([(mode << 4) | level]) + stream

    result = decompress_lzss(compressed, len(data))

    assert result == data

@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_bitstream_all_modes_all_levels(mode, level):
    # Keep this fixture within one 32-bit flag word for all modes.
    #
    # Mode 0:
    #   one literal consumes one flag bit.
    #
    # Modes 1/2:
    #   one literal consumes two flag bits.
    #
    # 16 literals therefore fit every mode.
    data = bytes(
        (i * 97 + 31) % 256
        for i in range(16)
    )

    if mode == 0:
        stream = make_mode0_stream([
            ("literal", byte, None)
            for byte in data
        ])
    else:
        stream = make_mode12_literal_stream(data)

    compressed = bytes([(mode << 4) | level]) + stream

    result = decompress_lzss(
        compressed,
        len(data),
    )

    assert result == data


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("level", [7, 8, 9])
def test_huffman_all_modes_all_levels(mode, level):
    data = bytes(range(1, 32))

    dist_bits, num_dist_symbols, dist_extra_bits = mode_params(mode)

    stream = make_huffman_literal_stream(
        data,
        num_dist_symbols,
    )

    compressed = bytes([(mode << 4) | level]) + stream

    assert decompress_lzss(compressed, len(data)) == data


def test_huffman_eof_symbol():
    # EOF_SYMBOL is 272.
    stream = make_huffman_symbol_stream([272])

    result = decompress_huffman(
        stream,
        100,
        dist_bits_total=8,
        num_dist_symbols=16,
        dist_extra_bits=4,
    )

    assert result == b""


def test_huffman_invalid_symbol():
    # 273 is a valid tree leaf but is > EOF_SYMBOL.
    stream = make_huffman_symbol_stream([273])

    with pytest.raises(CdpError, match=r"invalid Huffman symbol 273"):
        decompress_huffman(
            stream,
            1,
            dist_bits_total=8,
            num_dist_symbols=16,
            dist_extra_bits=4,
        )


def test_length_table():
    assert LENGTH_TABLE[0] == (0, 0)
    assert LENGTH_TABLE[1] == (1, 0)
    assert LENGTH_TABLE[2] == (2, 0)
    assert LENGTH_TABLE[3] == (3, 0)
    assert LENGTH_TABLE[4] == (4, 0)
    assert LENGTH_TABLE[5] == (5, 1)
    assert LENGTH_TABLE[6] == (7, 1)
    assert LENGTH_TABLE[7] == (9, 2)
    assert LENGTH_TABLE[8] == (13, 2)
    assert LENGTH_TABLE[9] == (17, 3)
    assert LENGTH_TABLE[10] == (25, 3)
    assert LENGTH_TABLE[11] == (33, 4)
    assert LENGTH_TABLE[12] == (49, 4)
    assert LENGTH_TABLE[13] == (65, 5)
    assert LENGTH_TABLE[14] == (97, 5)
    assert LENGTH_TABLE[15] == (129, 7)