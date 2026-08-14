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

from cdpunpack.bitreader import BitReader


def test_round_trip_single_bits():
    data = bytes([0x4D, 0x01])

    br = BitReader(data)

    bits = [1, 0, 1, 1, 0, 0, 1, 0, 1]

    for expected in bits:
        assert br.read_bit() == expected


def test_round_trip_multi_bits():
    data = bytes([0xF6, 0xBF])

    br = BitReader(data)

    assert br.read_bits(5) == 0b10110
    assert br.read_bits(8) == 0xFF
    assert br.read_bits(3) == 0b101


def test_empty_stream():
    br = BitReader(b"")

    assert br.read_bit() == 0
    assert br.read_bits(8) == 0


def test_byte_packing_order():
    data = bytes([0x29])

    br = BitReader(data)

    bits = [1, 0, 0, 1, 0, 1, 0, 0]

    for expected in bits:
        assert br.read_bit() == expected