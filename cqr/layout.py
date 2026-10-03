"""QR code symbol geometry (ISO/IEC 18004), versions 1-40.

CQR reuses the *exact* module layout of a regular QR code: finder patterns,
separators, timing patterns, alignment patterns, the dark module, the format
information area and (for versions >= 7) the version information area occupy
the same positions, and data modules are visited in the same zig-zag order.

All coordinates in this module are (row, col) with (0, 0) the top-left module.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

import numpy as np

# Module "kinds" stored in the layout map
K_DATA = 0
K_FINDER_DARK = 1   # dark modules of the three finder patterns (CQR colours these R/G/B)
K_FINDER_LIGHT = 2  # light modules inside the 7x7 finder squares
K_SEPARATOR = 3     # 1-module light border around each finder
K_TIMING_DARK = 4
K_TIMING_LIGHT = 5
K_ALIGN_DARK = 6
K_ALIGN_LIGHT = 7
K_FORMAT = 8        # 2 x 15 format information modules
K_VERSION = 9       # 2 x 18 version information modules (V >= 7)
K_DARK_MODULE = 10  # the always-dark module at (4V + 9, 8)

MIN_VERSION, MAX_VERSION = 1, 40

# Which finder is which, used by the encoder to assign the calibration colours.
FINDER_TL, FINDER_TR, FINDER_BL = 0, 1, 2


def size_for_version(version: int) -> int:
    if not MIN_VERSION <= version <= MAX_VERSION:
        raise ValueError(f"version must be in 1..40, got {version}")
    return 17 + 4 * version


def version_for_size(size: int) -> int:
    if size < 21 or size > 177 or (size - 17) % 4:
        raise ValueError(f"{size} is not a valid QR symbol size")
    return (size - 17) // 4


def alignment_positions(version: int) -> List[int]:
    """Centre coordinates (same list used for rows and columns) of alignment
    patterns. Uses the closed-form rule from Project Nayuki, which reproduces
    the ISO/IEC 18004 Annex E table exactly (cross-checked against segno)."""
    if version == 1:
        return []
    size = size_for_version(version)
    num_align = version // 7 + 2
    if version == 32:
        step = 26
    else:
        step = (version * 4 + num_align * 2 + 1) // (num_align * 2 - 2) * 2
    result = [6]
    pos = size - 7
    for _ in range(num_align - 1):
        result.append(pos)
        pos -= step
    return sorted(result)


@dataclass(frozen=True)
class Layout:
    version: int
    size: int
    kind: np.ndarray                    # (size, size) int8 map of module kinds
    data_order: np.ndarray              # (n_data, 2) int array of (row, col) in placement order
    finder_centres: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]
    align_centres: Tuple[Tuple[int, int], ...]

    @property
    def n_data_modules(self) -> int:
        return len(self.data_order)

    def finder_mask(self, which: int) -> np.ndarray:
        """Boolean mask of the dark modules of one finder pattern."""
        r0, c0 = self.finder_centres[which]
        m = np.zeros(self.kind.shape, dtype=bool)
        sub = self.kind[r0 - 3:r0 + 4, c0 - 3:c0 + 4]
        m[r0 - 3:r0 + 4, c0 - 3:c0 + 4] = sub == K_FINDER_DARK
        return m


def _draw_finder(kind: np.ndarray, r0: int, c0: int) -> None:
    """Draw a 7x7 finder with top-left corner (r0, c0) plus its separator."""
    size = kind.shape[0]
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = r0 + dr, c0 + dc
            if not (0 <= r < size and 0 <= c < size):
                continue
            if dr in (-1, 7) or dc in (-1, 7):
                kind[r, c] = K_SEPARATOR
            else:
                dist = max(abs(dr - 3), abs(dc - 3))
                kind[r, c] = K_FINDER_DARK if dist != 2 else K_FINDER_LIGHT


def _draw_alignment(kind: np.ndarray, r0: int, c0: int) -> None:
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            dist = max(abs(dr), abs(dc))
            kind[r0 + dr, c0 + dc] = K_ALIGN_DARK if dist != 1 else K_ALIGN_LIGHT


def format_bit_positions(size: int) -> List[List[Tuple[int, int]]]:
    """Return the two copies of the 15 format-information module positions.

    Element i of each list holds the (row, col) of bit i, where bit 0 is the
    least significant bit of the 15-bit (masked) format value, exactly as in
    ISO/IEC 18004 Figure 25 / Project Nayuki's reference implementation."""
    copy1 = []
    for i in range(6):
        copy1.append((i, 8))             # bits 0..5: column 8, rows 0..5
    copy1.append((7, 8))                 # bit 6
    copy1.append((8, 8))                 # bit 7
    copy1.append((8, 7))                 # bit 8
    for i in range(9, 15):
        copy1.append((8, 14 - i))        # bits 9..14: row 8, columns 5..0
    copy2 = []
    for i in range(8):
        copy2.append((8, size - 1 - i))  # bits 0..7: row 8, columns size-1 .. size-8
    for i in range(8, 15):
        copy2.append((size - 15 + i, 8))  # bits 8..14: column 8, rows size-7 .. size-1
    return [copy1, copy2]


def version_bit_positions(size: int) -> List[List[Tuple[int, int]]]:
    """Two copies of the 18 version-information module positions (bit 0 = LSB)."""
    copy1, copy2 = [], []
    for i in range(18):
        a = size - 11 + i % 3
        b = i // 3
        copy1.append((b, a))   # 6x3 block left of the top-right finder (rows 0..5, cols size-11..size-9)
        copy2.append((a, b))   # 3x6 block above the bottom-left finder (rows size-11..size-9, cols 0..5)
    return [copy1, copy2]


@lru_cache(maxsize=None)
def get_layout(version: int) -> Layout:
    size = size_for_version(version)
    kind = np.zeros((size, size), dtype=np.int8)

    # Finder patterns + separators
    _draw_finder(kind, 0, 0)
    _draw_finder(kind, 0, size - 7)
    _draw_finder(kind, size - 7, 0)
    finder_centres = ((3, 3), (3, size - 4), (size - 4, 3))

    # Timing patterns (row 6 and column 6 between the finders)
    for i in range(8, size - 8):
        k = K_TIMING_DARK if i % 2 == 0 else K_TIMING_LIGHT
        kind[6, i] = k
        kind[i, 6] = k

    # Alignment patterns (skip the three that would overlap the finders)
    pos = alignment_positions(version)
    align_centres = []
    for r in pos:
        for c in pos:
            if (r == 6 and c == 6) or (r == 6 and c == pos[-1]) or (r == pos[-1] and c == 6):
                continue
            _draw_alignment(kind, r, c)
            align_centres.append((r, c))

    # Format information (both copies) and the dark module
    for copy in format_bit_positions(size):
        for (r, c) in copy:
            kind[r, c] = K_FORMAT
    kind[size - 8, 8] = K_DARK_MODULE

    # Version information (V >= 7)
    if version >= 7:
        for copy in version_bit_positions(size):
            for (r, c) in copy:
                kind[r, c] = K_VERSION

    # Data placement order: 2-module-wide columns, right to left, snaking
    # upward then downward, skipping the vertical timing column 6.
    order = []
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            row = size - 1 - vert if upward else vert
            for j in range(2):
                col = right - j
                if kind[row, col] == K_DATA:
                    order.append((row, col))
        right -= 2
    data_order = np.array(order, dtype=np.int32)

    return Layout(version=version, size=size, kind=kind, data_order=data_order,
                  finder_centres=finder_centres, align_centres=tuple(align_centres))


def smallest_version_for_bits(required_bits: int, bits_per_module: int) -> int:
    for v in range(MIN_VERSION, MAX_VERSION + 1):
        if get_layout(v).n_data_modules * bits_per_module >= required_bits:
            return v
    raise ValueError("payload too large for any version")
