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
from typing import List

from cdpunpack.huffman import AdaptiveHuffmanTree
from cdpunpack.bitreader import BitReader


def encode_symbols(tree: AdaptiveHuffmanTree, symbols: List[int]) -> bytes:
    bits = []

    for symbol in symbols:
        node = tree.symbol_to_node[symbol]
        path = []

        while node != tree.root_idx:
            parent = tree.parent[node]

            if parent == node:
                break

            left = tree.child[parent]

            if left == node:
                path.append(0)
            elif left & 0x8000:
                raise AssertionError("invalid tree: parent points to leaf")
            else:
                right = left + 1
                if right >= tree.total_nodes:
                    raise AssertionError("invalid tree: right child out of bounds")

                if right != node:
                    raise AssertionError("invalid tree parent/child relationship")

                path.append(1)

            node = parent

        bits.extend(reversed(path))

        # Keep encoder-side adaptive state synchronized with decoder-side state.
        tree.update(symbol)

    # Pack LSB-first, matching BitReader.
    data = bytearray()

    for i in range(0, len(bits), 8):
        byte = 0

        for j, bit in enumerate(bits[i:i + 8]):
            byte |= bit << j

        data.append(byte)

    return bytes(data)


def test_encode_decode_round_trip():
    symbols = list(range(256)) + [0, 1, 2, 0, 0, 1, 255, 128]

    enc = AdaptiveHuffmanTree(273)
    data = encode_symbols(enc, symbols)

    dec = AdaptiveHuffmanTree(273)
    br = BitReader(data)

    for expected in symbols:
        assert dec.decode(br) == expected


def test_encode_decode_across_rebuild():
    symbols = [i % 256 for i in range(35_000)]

    enc = AdaptiveHuffmanTree(273)
    data = encode_symbols(enc, symbols)

    dec = AdaptiveHuffmanTree(273)
    br = BitReader(data)

    for idx, expected in enumerate(symbols):
        assert dec.decode(br) == expected, f"mismatch at {idx}"