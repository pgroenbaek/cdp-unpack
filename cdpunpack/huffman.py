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

from .bitreader import BitReader
from .error import CdpError


LEAF_FLAG = 0x8000
REBUILD_THRESHOLD = 0x7FFF
UNPROCESSED = 0xFFFFFFFE


class AdaptiveHuffmanTree:

    def __init__(self, num_symbols_raw: int):
        n = (num_symbols_raw + 1) & 0xFFE

        if n <= 0:
            raise CdpError("invalid Huffman symbol count")

        self.num_leaves = n
        self.total_nodes = n * 2 - 1
        self.root_idx = self.total_nodes - 1

        self.freq = [0] * self.total_nodes
        self.parent = [0] * self.total_nodes
        self.child = [0] * self.total_nodes
        self.sym_to_node = [0] * n

        # Leaves.
        for i in range(n):
            self.freq[i] = 1
            self.child[i] = i | LEAF_FLAG
            self.sym_to_node[i] = i

        # Internal nodes, bottom-up.
        j = 0

        for k in range(n, self.total_nodes):
            self.freq[k] = self.freq[j] + self.freq[j + 1]
            self.child[k] = j

            self.parent[j] = k
            self.parent[j + 1] = k

            j += 2

        self.parent[self.root_idx] = self.root_idx

    def decode(self, br: BitReader) -> int:
        v = self.child[self.root_idx]
        depth = 0

        while (v & LEAF_FLAG) == 0:
            idx = v + br.read_bit()

            if idx >= self.total_nodes:
                raise CdpError("Huffman tree index out of bounds")

            v = self.child[idx]

            depth += 1

            if depth > 50:
                raise CdpError("Huffman tree decode depth exceeded")

        sym = v & ~LEAF_FLAG

        if sym >= self.num_leaves:
            raise CdpError("Huffman symbol out of range")

        self.update(sym)

        return sym

    def update(self, symbol: int) -> None:
        if symbol < 0 or symbol >= self.num_leaves:
            raise CdpError(f"Huffman symbol {symbol} out of range")

        if self.freq[self.root_idx] > REBUILD_THRESHOLD:
            self.rebuild()

        i = self.sym_to_node[symbol]

        while True:
            self.freq[i] += 1
            f = self.freq[i]

            if (
                i + 1 < self.total_nodes
                and self.freq[i + 1] < f
            ):
                j = i + 2

                while (
                    j < self.total_nodes
                    and self.freq[j] < f
                ):
                    j += 1

                j -= 1

                ci = self.child[i]
                cj = self.child[j]

                # Point cj's children/symbol at position i.
                if (cj & LEAF_FLAG) == 0:
                    if cj + 1 >= self.total_nodes:
                        raise CdpError("invalid Huffman internal node")

                    self.parent[cj] = i
                    self.parent[cj + 1] = i
                else:
                    sym = cj & ~LEAF_FLAG

                    if sym >= self.num_leaves:
                        raise CdpError("invalid Huffman leaf")

                    self.sym_to_node[sym] = i

                # Point ci's children/symbol at position j.
                if (ci & LEAF_FLAG) == 0:
                    if ci + 1 >= self.total_nodes:
                        raise CdpError("invalid Huffman internal node")

                    self.parent[ci] = j
                    self.parent[ci + 1] = j
                else:
                    sym = ci & ~LEAF_FLAG

                    if sym >= self.num_leaves:
                        raise CdpError("invalid Huffman leaf")

                    self.sym_to_node[sym] = j

                self.freq[i], self.freq[j] = (
                    self.freq[j],
                    self.freq[i],
                )

                self.freq[j] = f

                self.child[i], self.child[j] = (
                    self.child[j],
                    self.child[i],
                )

                i = j

            p = self.parent[i]

            if p == i or p == self.root_idx:
                break

            if p >= self.total_nodes:
                raise CdpError("invalid Huffman parent")

            i = p

        self.freq[self.root_idx] += 1

    def rebuild(self) -> None:
        root_idx = self.root_idx
        remaining_leaves = self.num_leaves

        # Phase 1.
        for i in range(root_idx):
            if self.child[i] & LEAF_FLAG:
                self.freq[i] = (self.freq[i] + 1) >> 1

            self.parent[i] = UNPROCESSED

        self.parent[root_idx] = UNPROCESSED

        pair_scan = 0
        node_scan = 0

        while True:
            # Find next unprocessed node.
            found = False

            while pair_scan < root_idx:
                if self.parent[pair_scan] == UNPROCESSED:
                    found = True
                    break

                pair_scan += 1

            if not found or pair_scan >= root_idx:
                self.parent[root_idx] = 0xFFFFFFFF
                return

            left = pair_scan
            right = pair_scan + 1
            pair_scan += 2

            # Advance node_scan.
            while node_scan <= root_idx:
                if self.child[node_scan] & LEAF_FLAG:
                    remaining_leaves -= 1

                elif self.parent[node_scan] == UNPROCESSED:
                    break

                node_scan += 1

            slot = node_scan

            if slot > root_idx:
                raise CdpError("Huffman rebuild ran past root")

            node_scan += 1
            next_scan = node_scan

            new_freq = (
                self.freq[left]
                + self.freq[right]
            )

            insert_at = slot

            # Shift-right path
            if (
                slot > 0
                and self.freq[slot - 1] > new_freq
            ):
                scan = slot - 1

                while (
                    scan >= 0
                    and self.freq[scan] > new_freq
                ):
                    c = self.child[scan]

                    if (c & LEAF_FLAG) == 0:
                        if c + 1 >= self.total_nodes:
                            raise CdpError(
                                "invalid Huffman child during rebuild"
                            )

                        self.parent[c] += 1
                        self.parent[c + 1] += 1

                    else:
                        sym = c & ~LEAF_FLAG

                        if sym >= self.num_leaves:
                            raise CdpError(
                                "invalid Huffman symbol during rebuild"
                            )

                        self.sym_to_node[sym] += 1

                    scan -= 1

                pos = scan + 1
                count = slot - pos

                if count > 0:
                    for k in range(count - 1, -1, -1):
                        self.freq[pos + k + 1] = self.freq[pos + k]
                        self.child[pos + k + 1] = self.child[pos + k]

                insert_at = pos

            # Leaf-promotion path
            elif remaining_leaves > 0:
                scan_pos = next_scan
                dst = slot
                nxt = next_scan

                while True:
                    while scan_pos < root_idx:
                        if self.child[scan_pos] & LEAF_FLAG:
                            break

                        scan_pos += 1

                    if (
                        scan_pos >= root_idx
                        or self.freq[scan_pos] >= new_freq
                    ):
                        break

                    self.freq[dst] = self.freq[scan_pos]
                    self.child[dst] = self.child[scan_pos]
                    self.parent[dst] = UNPROCESSED

                    c = self.child[scan_pos]

                    if (c & LEAF_FLAG) == 0:
                        raise CdpError(
                            "leaf promotion encountered non-leaf"
                        )

                    sym = c & ~LEAF_FLAG

                    if sym >= self.num_leaves:
                        raise CdpError(
                            "invalid symbol during leaf promotion"
                        )

                    self.sym_to_node[sym] = dst

                    dst = nxt

                    self.child[scan_pos] = 0
                    nxt += 1

                    node_scan = nxt

                    remaining_leaves -= 1

                    if remaining_leaves <= 0:
                        break

                    scan_pos += 1

                insert_at = dst

            self.freq[insert_at] = new_freq
            self.child[insert_at] = left

            self.parent[left] = insert_at
            self.parent[right] = insert_at

