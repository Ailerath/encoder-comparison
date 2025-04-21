from __future__ import annotations

"""
HuffmanCoder

This class implements the full pipeline from symbol frequency analysis to prefix tree
construction, followed by canonical code conversion for header encoding.
It also handles a run-length encoding shortcut for very simple cases.

The main goal is to compare compression size and runtime performance against arithmetic coding.
"""

from collections import Counter
from heapq import heappush, heappop
from io import BytesIO
from typing import Dict, List

#
#Tree node(used internally to construct prefix codes)
#

class _Node:
    """Represents a node in the Huffman tree (leaf or internal).

    Leaves store a symbol; branches have left/right children.
    Each node tracks a frequency, used to build the optimal tree.
    """
    __slots__ =("freq", "symbol", "left", "right")

    def __init__(self, freq: int, symbol: int | None = None,
                 left: "_Node | None" = None, right: "_Node | None" = None):
        self.freq, self.symbol, self.left, self.right = freq, symbol, left, right

    def __lt__(self, other: "_Node") -> bool:
        return(self.freq, self.symbol or -1) <(other.freq, other.symbol or -1)


#
#Main coder interface
#

class HuffmanCoder:
    """Canonical Huffman encoder/decoder with basic header packing.

    Includes optimizations for edge cases (e.g., single-symbol files).
    Should support full byte-range symbols
    """

    name = "Huffman"

    def encode(self, data: bytes) -> bytes:
        if not data:
            return b""

        #Handle simple data: if all bytes are the same, skip tree
        freq = Counter(data)
        if len(freq) == 1:
            sym = next(iter(freq))
            return b"RUN"+bytes([sym])+len(data).to_bytes(4, "big")

        #Build Huffman tree from symbol frequencies
        root = self._build_tree(freq)

        #Recursively assign bitstrings to symbols
        raw_map = self._build_code_map(root)

        #Canonicalize the code map
        canon, lengths = self._to_canonical(raw_map)

        buf = BytesIO()
        buf.write(len(data).to_bytes(4, "big"))       #Uncompressed size
        buf.write(bytes([len(canon)]))                #Number of distinct symbols

        #Write symbol-length pairs to header
        for s in canon:
            buf.write(bytes([s, lengths[s]]))

        #Serialize canonical codebook structure
        code_bits = "".join(canon[s] for s in canon)
        buf.write(len(code_bits).to_bytes(2, "big"))
        self._pack_bits(buf, code_bits)

        #Encode data using canonical codes
        payload_bits = "".join(canon[b] for b in data)
        buf.write(len(payload_bits).to_bytes(4, "big"))
        self._pack_bits(buf, payload_bits)

        return buf.getvalue()

    def decode(self, blob: bytes) -> bytes:
        if not blob:
            return b""
        if blob.startswith(b"RUN"):
            sym = blob[3]
            n   = int.from_bytes(blob[4:8], "big")
            return bytes([sym])*n

        mv = memoryview(blob)
        i = 0
        orig_len = int.from_bytes(mv[i:i+4], "big"); i += 4
        leaf_cnt = mv[i]; i += 1

        #Reconstruct (symbol, length) list from header
        symbols, lengths = [], []
        for _ in range(leaf_cnt):
            symbols.append(mv[i]); i += 1
            lengths.append(mv[i]); i += 1

        #Reconstruct the same canonical table as encoder
        canon_len_bits = int.from_bytes(mv[i:i+2], "big"); i += 2
        canon_bytes =(canon_len_bits+7) // 8
        canon_blob = mv[i:i+canon_bytes].tobytes(); i += canon_bytes
        canon_bits = "".join(f"{b:08b}" for b in canon_blob)[:canon_len_bits]

        table: Dict[str, int] ={}
        code = prev_len = 0
        bit_iter = iter(canon_bits)
        for sym, ln in sorted(zip(symbols, lengths), key=lambda x:(x[1], x[0])):
            if ln != prev_len:
                code <<=(ln-prev_len)
            table[f"{code:0{ln}b}"] = sym
            code += 1
            prev_len = ln

        #Decode bitstream using table until length is met
        payload_len_bits = int.from_bytes(mv[i:i+4], "big"); i += 4
        payload_bytes =(payload_len_bits+7) // 8
        payload_bits = "".join(f"{b:08b}" for b in mv[i:i+payload_bytes])[:payload_len_bits]

        out, cur = bytearray(), ""
        for bit in payload_bits:
            cur += bit
            if cur in table:
                out.append(table[cur])
                cur = ""
                if len(out) == orig_len:
                    break
        return bytes(out)

    #Tree generation: uses heap to always merge lowest frequency nodes
    @staticmethod
    def _build_tree(freq: Counter) -> _Node:
        heap: List[_Node] = [_Node(f, s) for s, f in freq.items()]
        heappush(heap, heappop(heap))  #ensure heap property holds
        while len(heap) > 1:
            n1, n2 = heappop(heap), heappop(heap)
            heappush(heap, _Node(n1.freq+n2.freq, None, n1, n2))
        return heap[0]

    #Recursively build map from byte bitstring
    def _build_code_map(self, node: _Node, prefix: str = "") -> Dict[int, str]:
        if node.symbol is not None:
            return{node.symbol: prefix or "0"}  #if only one symbol, default to 0
        m ={}
        m.update(self._build_code_map(node.left,  prefix+"0"))
        m.update(self._build_code_map(node.right, prefix+"1"))
        return m

    #Canonical code reshuffles codes to predictable bit order
    def _to_canonical(self, code_map: Dict[int, str]) -> tuple[Dict[int, str], Dict[int, int]]:
        lengths ={s: len(b) for s, b in code_map.items()}
        order = sorted(code_map, key=lambda s:(lengths[s], s))
        canonical: Dict[int, str] ={}
        code = prev_len = 0
        for sym in order:
            ln = lengths[sym]
            code <<=(ln-prev_len)
            canonical[sym] = f"{code:0{ln}b}"
            code += 1
            prev_len = ln
        return canonical, lengths

    #Convert bitstring into bytes
    @staticmethod
    def _pack_bits(buf: BytesIO, bits: str) -> None:
        for i in range(0, len(bits), 8):
            chunk = bits[i:i+8].ljust(8, "0")
            buf.write(int(chunk, 2).to_bytes(1, "big"))
