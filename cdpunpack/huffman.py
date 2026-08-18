"""
This file is part of CdpUnpack.

Copyright (c) 2026 cdptool contributors
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
    """
    Adaptive Huffman tree for CDP symbol compression.

    Implements a Gallager-Knuth-Vitter-style adaptive Huffman algorithm used by
    the unpacker. The tree uses the sibling property, storing nodes in a flat array
    ordered by non-decreasing frequency, with each internal node's children occupying
    adjacent positions.

    Leaf nodes store their symbol with a flag in the high bit of the child entry,
    while internal nodes store the index of their left child; the right child is
    implicitly the following node.

    After each symbol, frequencies are propagated up the leaf-to-root path and
    nodes are repositioned to preserve the frequency ordering. When the root
    frequency exceeds the supported range, the tree is rebuilt by reducing leaf
    frequencies.
    """

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
        self.symbol_to_node = [0] * n

        # Leaves.
        for i in range(n):
            self.freq[i] = 1
            self.child[i] = i | LEAF_FLAG
            self.symbol_to_node[i] = i

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

        symbol = v & ~LEAF_FLAG

        if symbol >= self.num_leaves:
            raise CdpError("Huffman symbol out of range")

        self.update(symbol)

        return symbol

    def update(self, symbol: int) -> None:
        if symbol < 0 or symbol >= self.num_leaves:
            raise CdpError(f"Huffman symbol {symbol} out of range")

        if self.freq[self.root_idx] > REBUILD_THRESHOLD:
            self.rebuild()

        i = self.symbol_to_node[symbol]

        while True:
            self.freq[i] += 1
            f = self.freq[i]

            if i + 1 < self.total_nodes and self.freq[i + 1] < f:
                j = i + 2

                while j < self.total_nodes and self.freq[j] < f:
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
                    symbol = cj & ~LEAF_FLAG

                    if symbol >= self.num_leaves:
                        raise CdpError("invalid Huffman leaf")

                    self.symbol_to_node[symbol] = i

                # Point ci's children/symbol at position j.
                if (ci & LEAF_FLAG) == 0:
                    if ci + 1 >= self.total_nodes:
                        raise CdpError("invalid Huffman internal node")

                    self.parent[ci] = j
                    self.parent[ci + 1] = j
                else:
                    symbol = ci & ~LEAF_FLAG

                    if symbol >= self.num_leaves:
                        raise CdpError("invalid Huffman leaf")

                    self.symbol_to_node[symbol] = j

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

            parent = self.parent[i]

            if parent == i or parent == self.root_idx:
                break

            if parent >= self.total_nodes:
                raise CdpError("invalid Huffman parent")

            i = parent

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

            new_freq = self.freq[left] + self.freq[right]
            insert_at = slot

            # Shift-right path
            if slot > 0 and self.freq[slot - 1] > new_freq:
                scan = slot - 1

                while scan >= 0 and self.freq[scan] > new_freq:
                    child = self.child[scan]

                    if (child & LEAF_FLAG) == 0:
                        if child + 1 >= self.total_nodes:
                            raise CdpError("invalid Huffman child during rebuild")

                        self.parent[child] += 1
                        self.parent[child + 1] += 1

                    else:
                        symbol = child & ~LEAF_FLAG

                        if symbol >= self.num_leaves:
                            raise CdpError("invalid Huffman symbol during rebuild")

                        self.symbol_to_node[symbol] += 1

                    scan -= 1

                position = scan + 1
                count = slot - position

                if count > 0:
                    for k in range(count - 1, -1, -1):
                        self.freq[position + k + 1] = self.freq[position + k]
                        self.child[position + k + 1] = self.child[position + k]

                insert_at = position

            # Leaf-promotion path
            elif remaining_leaves > 0:
                scan_position = next_scan
                destination = slot
                next_destination = next_scan

                while True:
                    while scan_position < root_idx:
                        if self.child[scan_position] & LEAF_FLAG:
                            break

                        scan_position += 1

                    if scan_position >= root_idx or self.freq[scan_position] >= new_freq:
                        break

                    self.freq[destination] = self.freq[scan_position]
                    self.child[destination] = self.child[scan_position]
                    self.parent[destination] = UNPROCESSED

                    child = self.child[scan_position]

                    if (child & LEAF_FLAG) == 0:
                        raise CdpError("leaf promotion encountered non-leaf")

                    symbol = child & ~LEAF_FLAG

                    if symbol >= self.num_leaves:
                        raise CdpError("invalid symbol during leaf promotion")

                    self.symbol_to_node[symbol] = destination

                    destination = next_destination

                    self.child[scan_position] = 0
                    next_destination += 1

                    node_scan = next_destination
                    
                    remaining_leaves -= 1

                    if remaining_leaves <= 0:
                        break

                    scan_position += 1

                insert_at = destination

            self.freq[insert_at] = new_freq
            self.child[insert_at] = left

            self.parent[left] = insert_at
            self.parent[right] = insert_at

