"""
This file is part of CDPUnpack.

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

class BitReader:
    """
    Bits are consumed LSB-first.
    
    Reading beyond EOF returns zero.
    """

    def __init__(self, data: bytes):
        self.data = data
        self.len_bits = len(data) * 8
        self.pos = 0

    def read_bit(self) -> int:
        if self.pos >= self.len_bits:
            return 0

        byte_pos = self.pos >> 3
        bit_pos = self.pos & 7

        self.pos += 1
        return (self.data[byte_pos] >> bit_pos) & 1

    def read_bits(self, n: int) -> int:
        if n <= 0:
            return 0

        available = min(n, self.len_bits - self.pos)

        if available <= 0:
            return 0

        result = 0

        for i in range(available):
            result |= self.read_bit() << i

        return result

    def bit_position(self) -> int:
        return self.pos
