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

from typing import Tuple

from .bitreader import BitReader
from .error import CdpError
from .huffman import AdaptiveHuffmanTree


LENGTH_TABLE = [
    (0, 0),
    (1, 0),
    (2, 0),
    (3, 0),
    (4, 0),
    (5, 1),
    (7, 1),
    (9, 2),
    (13, 2),
    (17, 3),
    (25, 3),
    (33, 4),
    (49, 4),
    (65, 5),
    (97, 5),
    (129, 7),
]

EOF_SYMBOL = 272
NUM_LIT_SYMBOLS = 273


def mode_params(mode: int) -> Tuple[int, int, int]:
    if mode == 0:
        return 8, 16, 4

    if mode == 1:
        return 12, 64, 6

    if mode == 2:
        return 14, 64, 8

    raise CdpError(f"invalid compression mode {mode}")


def copy_match(
    output: bytearray,
    distance: int,
    match_len: int,
    max_size: int,
) -> None:
    """
    Important: bytes are appended one at a time, which naturally permits
    overlapping LZSS matches.
    """
    for _ in range(match_len):
        if len(output) >= max_size:
            break

        if distance <= len(output):
            b = output[len(output) - distance]
        else:
            b = 0

        output.append(b)


def decompress_huffman(
    stream: bytes,
    uncompressed_size: int,
    dist_bits_total: int,
    num_dist_symbols: int,
    dist_extra_bits: int,
) -> bytes:

    dist_mask = (1 << dist_bits_total) - 1

    lit_tree = AdaptiveHuffmanTree(NUM_LIT_SYMBOLS)
    dist_tree = AdaptiveHuffmanTree(num_dist_symbols)

    br = BitReader(stream)

    output = bytearray()

    while len(output) < uncompressed_size:
        symbol = lit_tree.decode(br)

        if symbol == EOF_SYMBOL:
            break

        if symbol > EOF_SYMBOL:
            raise CdpError(
                f"invalid Huffman symbol {symbol}"
            )

        if symbol < 256:
            output.append(symbol)

        else:
            table_index = symbol - 256

            if table_index < 0 or table_index >= len(LENGTH_TABLE):
                raise CdpError(
                    f"invalid length symbol {symbol}"
                )

            base, extra = LENGTH_TABLE[table_index]

            if extra:
                extra_val = br.read_bits(extra)
            else:
                extra_val = 0

            match_len = base + extra_val + 3

            dist_symbol = dist_tree.decode(br)
            dist_extra = br.read_bits(dist_extra_bits)

            distance = ((dist_symbol << dist_extra_bits) | dist_extra) & dist_mask

            if distance == 0:
                distance = 1

            copy_match(output, distance, match_len, uncompressed_size)

    if len(output) > uncompressed_size:
        del output[uncompressed_size:]

    return bytes(output)


def decompress_bitstream(
    stream: bytes,
    uncompressed_size: int,
    dist_bits_total: int,
    dist_extra_bits: int,
) -> bytes:

    dist_mask = (1 << dist_bits_total) - 1

    if dist_bits_total < 16:
        len_overflow = (1 << (16 - dist_bits_total)) - 1
    else:
        len_overflow = 0

    offset_shift = min(dist_bits_total, 15)

    br = BitReader(stream)
    output = bytearray()

    # Mode 0
    if dist_extra_bits == 0:

        while len(output) < uncompressed_size:
            flags = br.read_bits(32)
            mask = 1

            while mask != 0 and len(output) < uncompressed_size:
                if (flags & mask) == 0:
                    # Literal.
                    output.append(br.read_bits(8))

                    mask <<= 1

                else:
                    # Match.
                    mask <<= 1

                    if mask == 0:
                        break

                    len_code = 1 if flags & mask else 0

                    mask <<= 1

                    if mask == 0:
                        break

                    if flags & mask:
                        len_code |= 2

                    mask <<= 1

                    if mask == 0:
                        break

                    if flags & mask:
                        len_code |= 4

                    # Escape.
                    if len_code == 7:
                        len_code = br.read_bits(8)

                    distance = br.read_bits(8)

                    if distance == 0:
                        distance = 1

                    match_len = len_code + 3

                    copy_match(output, distance, match_len, uncompressed_size)

                    mask <<= 1

        if len(output) > uncompressed_size:
            del output[uncompressed_size:]

        return bytes(output)

    # Modes 1 and 2
    while len(output) < uncompressed_size:
        flags = br.read_bits(32)
        mask = 1

        while mask != 0 and len(output) < uncompressed_size:
            if (flags & mask) == 0:
                # First bit = 0.
                mask <<= 1

                if mask == 0:
                    break

                if (flags & mask) == 0:
                    # 00 = literal.
                    output.append(br.read_bits(8))

                else:
                    # 01 = short copy.
                    run_len = br.read_bits(8) + 3

                    for _ in range(run_len):
                        if len(output) >= uncompressed_size:
                            break

                        output.append(br.read_bits(8))

                mask <<= 1

            else:
                # 1 = back reference.
                word = br.read_bits(16)

                distance = word & dist_mask

                len_code = (word >> offset_shift) & len_overflow

                if len_code == len_overflow:
                    len_code = br.read_bits(8)

                if distance == 0:
                    distance = 1

                match_len = len_code + 3

                copy_match(output, distance, match_len, uncompressed_size)

                mask <<= 1

    if len(output) > uncompressed_size:
        del output[uncompressed_size:]

    return bytes(output)


def decompress_lzss(
    compressed_data: bytes,
    uncompressed_size: int,
) -> bytes:

    if not compressed_data:
        raise CdpError("empty LZSS blob")

    first_byte = compressed_data[0]

    mode = (first_byte >> 4) & 3
    level = first_byte & 0xF

    # Stored.
    if level == 0:
        end = min(
            1 + uncompressed_size,
            len(compressed_data),
        )

        result = compressed_data[1:end]

        if len(result) != uncompressed_size:
            raise CdpError(
                "stored blob is shorter than declared "
                f"uncompressed size "
                f"({len(result)} != {uncompressed_size})"
            )

        return result

    dist_bits_total, num_dist_symbols, dist_extra_bits = mode_params(mode)

    stream = compressed_data[1:]

    if level < 7:
        result = decompress_bitstream(
            stream,
            uncompressed_size,
            dist_bits_total,
            dist_extra_bits,
        )

    else:
        result = decompress_huffman(
            stream,
            uncompressed_size,
            dist_bits_total,
            num_dist_symbols,
            dist_extra_bits,
        )

    if len(result) != uncompressed_size:
        raise CdpError(
            "decompressed size mismatch: "
            f"got {len(result)}, "
            f"expected {uncompressed_size}"
        )

    return result
