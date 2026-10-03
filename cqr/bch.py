"""BCH codes used by QR for format (15,5) and version (18,6) information.

Both are decoded by exhaustive nearest-codeword search (32 / 34 codewords),
which is optimal and trivially fast."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

FORMAT_GEN = 0x537      # x^10 + x^8 + x^5 + x^4 + x^2 + x + 1
FORMAT_MASK = 0x5412    # 101010000010010
VERSION_GEN = 0x1F25    # x^12 + x^11 + x^10 + x^9 + x^8 + x^5 + x^2 + 1


def encode_format(data5: int) -> int:
    """5 data bits -> 15-bit masked format word (ISO/IEC 18004 Annex C)."""
    if not 0 <= data5 < 32:
        raise ValueError("format data must be 5 bits")
    rem = data5
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * FORMAT_GEN)
    return ((data5 << 10) | rem) ^ FORMAT_MASK


def encode_version(version: int) -> int:
    """6-bit version number (7..40) -> 18-bit version word (Annex D)."""
    if not 7 <= version <= 40:
        raise ValueError("version information only exists for versions 7..40")
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * VERSION_GEN)
    return (version << 12) | rem


@lru_cache(maxsize=1)
def _format_table():
    return [encode_format(d) for d in range(32)]


@lru_cache(maxsize=1)
def _version_table():
    return {v: encode_version(v) for v in range(7, 41)}


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def decode_format(word15: int, max_errors: int = 3) -> Optional[Tuple[int, int]]:
    """Return (data5, n_corrected) for the nearest codeword, or None if the
    nearest codeword is further than max_errors bits away (BCH(15,5) has
    minimum distance 7, so up to 3 errors are corrected unambiguously)."""
    best, best_d = None, 99
    for d, cw in enumerate(_format_table()):
        h = _hamming(cw, word15 & 0x7FFF)
        if h < best_d:
            best, best_d = d, h
    if best_d > max_errors:
        return None
    return best, best_d


def decode_version(word18: int, max_errors: int = 3) -> Optional[Tuple[int, int]]:
    """Return (version, n_corrected) or None. BCH(18,6) has minimum distance 8."""
    best, best_d = None, 99
    for v, cw in _version_table().items():
        h = _hamming(cw, word18 & 0x3FFFF)
        if h < best_d:
            best, best_d = v, h
    if best_d > max_errors:
        return None
    return best, best_d
