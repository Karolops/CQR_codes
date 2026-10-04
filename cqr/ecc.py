"""Reed-Solomon error correction, block structure, interleaving and whitening.

CQR uses Reed-Solomon codes like QR, but the RS *symbol size is chosen to match
the module*: profiles with 9 or 12 bits per module use RS over GF(2^9) or
GF(2^12) so that one module is exactly one RS symbol, all other profiles use
QR's GF(2^8) (primitive polynomial 0x11D).  Measured effect (see
research/03_design_decisions.md, section 7): with byte symbols a 9- or 12-bit
module error always damages two bytes, with aligned symbols it damages one, so
the tolerable module error rate at equal parity almost doubles (7.0 % -> 13.0 %
for 9 bits, 6.9 % -> 14.8 % for 12 bits).  Aligned symbols for 3-6 bit profiles
bring nothing (measured), so bytes are kept there.

Block structure is computed rather than tabulated:

* total symbols     N = floor(data_modules * bits_per_module / s)   (s = symbol bits)
* number of blocks  B = ceil(N / (2^s - 1))
* EC symbols/block  E = 2 * ceil(r * N / B)      (r = nominal recovery fraction)
* data symbols      N - B*E, split as evenly as possible (first blocks shorter),
  exactly like QR's "group 1 / group 2" rule.

Symbols are interleaved like QR (data symbol i of every block, then EC symbol i
of every block) and XORed with a fixed pseudo-random sequence (whitening) so
that structured payloads never produce large uniform colour areas - this plays
the role of QR's mask patterns without needing mask bits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import reedsolo

from .profiles import EC_LEVELS

RS_PRIM_8 = 0x11D


def symbol_bits_for(bits_per_module: int) -> int:
    """RS symbol size used for a profile: aligned to the module for 9/12 bits."""
    return bits_per_module if bits_per_module in (9, 12) else 8


@dataclass(frozen=True)
class BlockStructure:
    total_codewords: int
    n_blocks: int
    ec_per_block: int
    data_lengths: Tuple[int, ...]   # data symbols in each block
    symbol_bits: int = 8

    @property
    def data_codewords(self) -> int:
        return sum(self.data_lengths)

    @property
    def ec_codewords(self) -> int:
        return self.n_blocks * self.ec_per_block

    @property
    def max_errors_per_block(self) -> int:
        return self.ec_per_block // 2


def block_structure(total_codewords: int, ec_level: str, symbol_bits: int = 8) -> BlockStructure:
    r = EC_LEVELS[ec_level][1]
    N = total_codewords
    if N < 4:
        raise ValueError("symbol too small")
    nsize = (1 << symbol_bits) - 1
    B = -(-N // nsize)
    E = 2 * int(np.ceil(r * N / B))
    E = max(E, 2)
    data_total = N - B * E
    if data_total < B:
        raise ValueError("not enough codewords for data")
    base, extra = divmod(data_total, B)
    lengths = tuple([base] * (B - extra) + [base + 1] * extra)
    return BlockStructure(N, B, E, lengths, symbol_bits)


def _codec(nsym: int, symbol_bits: int) -> reedsolo.RSCodec:
    # NOT cached on purpose: reedsolo keeps its field tables in module globals
    # that are (re)initialised by the RSCodec constructor, so a codec object is
    # only valid until another codec with a different field is constructed.
    if symbol_bits == 8:
        return reedsolo.RSCodec(nsym, nsize=255, fcr=0, prim=RS_PRIM_8, generator=2, c_exp=8)
    return reedsolo.RSCodec(nsym, nsize=(1 << symbol_bits) - 1, fcr=0, generator=2, c_exp=symbol_bits)


def rs_encode(data: Sequence[int], bs: BlockStructure) -> List[int]:
    """data (exactly bs.data_codewords symbols) -> interleaved, whitened symbol list."""
    if len(data) != bs.data_codewords:
        raise ValueError(f"expected {bs.data_codewords} data symbols, got {len(data)}")
    codec = _codec(bs.ec_per_block, bs.symbol_bits)
    blocks_data: List[List[int]] = []
    blocks_ec: List[List[int]] = []
    pos = 0
    for n in bs.data_lengths:
        block = [int(x) for x in data[pos:pos + n]]
        pos += n
        full = list(codec.encode(block))
        blocks_data.append(full[:n])
        blocks_ec.append(full[n:])
    out: List[int] = []
    for i in range(max(bs.data_lengths)):
        for blk in blocks_data:
            if i < len(blk):
                out.append(blk[i])
    for i in range(bs.ec_per_block):
        for blk in blocks_ec:
            out.append(blk[i])
    assert len(out) == bs.total_codewords
    return whiten(out, bs.symbol_bits)


def deinterleave(msg: Sequence, bs: BlockStructure) -> List[List]:
    """Inverse of the interleaving in rs_encode: returns per-block (data+ec) lists."""
    blocks: List[List] = [[] for _ in range(bs.n_blocks)]
    idx = 0
    for i in range(max(bs.data_lengths)):
        for b, n in enumerate(bs.data_lengths):
            if i < n:
                blocks[b].append(msg[idx]); idx += 1
    for i in range(bs.ec_per_block):
        for b in range(bs.n_blocks):
            blocks[b].append(msg[idx]); idx += 1
    return blocks


@dataclass
class RSResult:
    data: List[int]
    corrected: int           # total corrected symbols (errors + erasures) across blocks
    failed_blocks: int


def rs_decode(msg: Sequence[int], bs: BlockStructure,
              reliability: Optional[np.ndarray] = None) -> RSResult:
    """Decode a whitened, interleaved symbol sequence.

    reliability: optional per-symbol confidence (higher = more reliable).
    If plain decoding of a block fails, the least reliable symbols of that
    block are progressively declared erasures and decoding is retried (RS
    corrects v errors + e erasures when 2v + e <= E).
    """
    if len(msg) != bs.total_codewords:
        raise ValueError(f"expected {bs.total_codewords} codewords, got {len(msg)}")
    msg = whiten([int(x) for x in msg], bs.symbol_bits)
    rel_blocks = None
    if reliability is not None:
        rel_blocks = deinterleave(list(np.asarray(reliability, dtype=np.float64)), bs)
    blocks = deinterleave(msg, bs)
    codec = _codec(bs.ec_per_block, bs.symbol_bits)
    out: List[int] = []
    corrected = 0
    failed = 0
    E = bs.ec_per_block
    for b, block in enumerate(blocks):
        n = bs.data_lengths[b]
        arr = bytearray(block) if bs.symbol_bits == 8 else list(block)
        decoded = None
        attempts: List[List[int]] = [[]]
        if rel_blocks is not None:
            order = list(np.argsort(np.asarray(rel_blocks[b])))  # least reliable first
            # Never erase more than 3E/4 symbols: with E-1 erasures a single check
            # symbol remains and reedsolo accepts random input in ~40 % of cases
            # (measured: 0/150 false accepts at 3E/4, 2-3 % at E-8, 40-60 % at E-1).
            for k in sorted({E // 4, E // 2, (3 * E) // 4}):
                if 0 < k < E:
                    attempts.append([int(i) for i in order[:k]])
        for erase in attempts:
            try:
                res = codec.decode(arr, erase_pos=erase if erase else None)
                decoded = list(res[0][:n])
                corrected += len(res[2])
                break
            except reedsolo.ReedSolomonError:
                continue
        if decoded is None:
            failed += 1
            decoded = list(arr[:n])  # best effort: pass through uncorrected
        out += [int(x) for x in decoded]
    return RSResult(out, corrected, failed)


# ---- whitening -------------------------------------------------------------
_WHITEN_SEED = 0xC0DEC0DE


def whitening_sequence(n: int, symbol_bits: int = 8) -> np.ndarray:
    """Deterministic xorshift32 sequence of n symbol_bits-wide values (platform independent)."""
    out = np.empty(n, dtype=np.int64)
    x = _WHITEN_SEED
    for i in range(n):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out[i] = x >> (32 - symbol_bits)
    return out


def whiten(data: Sequence[int], symbol_bits: int = 8) -> List[int]:
    seq = whitening_sequence(len(data), symbol_bits)
    return [int(v) for v in (np.asarray(data, dtype=np.int64) ^ seq)]
