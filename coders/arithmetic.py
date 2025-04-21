from __future__ import annotations

"""
ArithmeticCoder

Implements an arithmetic coding model
Used to benchmark compression size and speed vs canonical Huffman coding.

The coder handles full 8-bit input, builds a frequency model per file, and uses
range scaling to narrow on symbol intervals.
"""

from collections import Counter
from io import BytesIO
from typing import List

#Constants for 32-bit range arithmetic coding
_TOP  = 1 << 32
_HALF = 1 << 31
_QTR  = 1 << 30

#
#Bit I/O buffers
#

class _BitOut:
    #Write bits one at a time and extend them into byte-aligned output.

    __slots__ =("bits",)

    def __init__(self):
        self.bits: List[int] = []

    def put(self, bit: int):
        self.bits.append(bit & 1)

    def extend(self, bit: int, n: int):
        self.bits.extend([bit & 1]*n)

    def finish(self) -> bytes:
        self.bits.extend([0] *(-len(self.bits) % 8))
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for b in self.bits[i:i+8]:
                byte =(byte << 1) | b
            out.append(byte)
        return bytes(out)


class _BitIn:
    #Read bits from byte buffer one at a time.

    __slots__ =("bits", "idx")

    def __init__(self, blob: bytes):
        self.bits = [((b >> i) & 1) for b in blob for i in range(7, -1, -1)]
        self.idx = 0

    def get(self) -> int:
        if self.idx >= len(self.bits):
            return 0  #pad with zero if bits run out
        bit = self.bits[self.idx]
        self.idx += 1
        return bit


#
#Public arithmetic coder
#

class ArithmeticCoder:
    #Static model arithmetic coder using per-file symbol frequencies.

    name = "Arithmetic"

    def encode(self, data: bytes) -> bytes:
        if not data:
            return b""

        freq = Counter(data)

        #Handle single-symbol inputs with a special case
        if len(freq) == 1:
            sym = next(iter(freq))
            return b"RUN"+bytes([sym])+len(data).to_bytes(4, "big")

        #Build frequency table(needed for partitioning)
        symbols = sorted(freq)
        cum, running = [0], 0
        for s in symbols:
            running += freq[s]
            cum.append(running)
        total = cum[-1]
        cum ={s: cum[i] for i, s in enumerate(symbols)}

        #Initialize interval and output bit buffer
        low, high, pending = 0, _TOP-1, 0
        bout = _BitOut()

        def emit(bit: int):
            nonlocal pending
            bout.put(bit)
            if pending:
                bout.extend(bit ^ 1, pending)
                pending = 0

        #Encode each byte by narrowing the interval
        for b in data:
            r = high-low+1
            low  += r*cum[b]     // total
            high  = low+r*freq[b] // total-1

            #Normalize interval to keep MSBs aligned
            while True:
                if high < _HALF:
                    emit(0)
                elif low >= _HALF:
                    low -= _HALF; high -= _HALF; emit(1)
                elif low >= _QTR and high < 3*_QTR:
                    low -= _QTR; high -= _QTR; pending += 1
                else:
                    break
                low  =(low  << 1) &(_TOP-1)
                high =((high << 1) | 1) &(_TOP-1)

        #Final bit after encoding all input
        pending += 1
        emit(0 if low < _QTR else 1)
        code_bits = bout.finish()

        #Write header and bitstream
        buf = BytesIO()
        buf.write(len(data).to_bytes(4, "big"))
        buf.write(bytes([len(symbols)]))
        for s in symbols:
            buf.write(bytes([s]))
            buf.write(freq[s].to_bytes(4, "big"))
        buf.write(code_bits)
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
        n  = int.from_bytes(mv[i:i+4], "big"); i += 4
        sc = mv[i]; i += 1

        #Parse table from header
        symbols, freq, total = [],{}, 0
        for _ in range(sc):
            s = mv[i]; i += 1
            f = int.from_bytes(mv[i:i+4], "big"); i += 4
            symbols.append(s); freq[s] = f; total += f

        cum, run ={}, 0
        for s in sorted(symbols):
            cum[s] = run
            run += freq[s]

        #Start with initial code value
        bitin = _BitIn(mv[i:].tobytes())
        code = 0
        for _ in range(32):
            code =(code << 1) | bitin.get()

        low, high = 0, _TOP-1
        out = bytearray()

        #Decode symbols one at a time by mapping into ranges
        while len(out) < n:
            r = high-low+1
            scaled =((code-low+1)*total-1) // r
            for s in symbols:
                if cum[s]+freq[s] > scaled >= cum[s]:
                    break
            out.append(s)

            #Narrow the range
            low  += r*cum[s] // total
            high = low+r*freq[s] // total-1

            #Normalize the interval
            while True:
                if high < _HALF:
                    pass
                elif low >= _HALF:
                    low -= _HALF; high -= _HALF; code -= _HALF
                elif low >= _QTR and high < 3*_QTR:
                    low -= _QTR; high -= _QTR; code -= _QTR
                else:
                    break
                low  =(low  << 1) &(_TOP-1)
                high =((high << 1) | 1) &(_TOP-1)
                code =((code << 1) | bitin.get()) &(_TOP-1)

        return bytes(out)
