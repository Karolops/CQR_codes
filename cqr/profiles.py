"""Colour profiles and error-correction levels.

A CQR symbol's 5-bit format payload (protected by the standard QR BCH(15,5)
code and stored, in black and white, at the standard format-information
positions) is::

    bit 4..3 : error-correction level  (QR encoding: L=01, M=00, Q=11, H=10)
    bit 2..0 : colour profile index    (table below)

The colour profile fixes how many bits each module carries.  A module colour is
an (R, G, B) triple where channel c takes one of 2**k_c equally spaced sRGB
levels.  Levels are Gray-coded so that a misread into a *neighbouring* level
flips a single bit.  Profile 6/7 are achromatic (grey-level) profiles that are
useful as a baseline and for the harshest print conditions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np


@dataclass(frozen=True)
class ColorProfile:
    index: int
    name: str
    bits: Tuple[int, int, int]   # bits per channel (R, G, B); for grey profiles all three are equal and `gray` is True
    gray: bool = False

    @property
    def bits_per_module(self) -> int:
        return self.bits[0] if self.gray else sum(self.bits)

    @property
    def levels(self) -> Tuple[int, int, int]:
        return tuple(1 << b for b in self.bits)

    @property
    def n_colors(self) -> int:
        return 1 << self.bits_per_module

    def channel_values(self, c: int) -> np.ndarray:
        """sRGB 0..255 value of each level of channel c."""
        L = self.levels[c]
        return np.round(np.linspace(0, 255, L)).astype(np.uint8)

    # ---- symbol <-> module levels ----------------------------------------
    def symbols_to_levels(self, symbols: np.ndarray) -> np.ndarray:
        """symbols: (n,) ints in [0, 2**bpm). Returns (n, 3) channel levels."""
        symbols = np.asarray(symbols, dtype=np.int64)
        if self.gray:
            lv = gray_to_binary_inverse(symbols)  # Gray-decode: bits -> level
            return np.stack([lv, lv, lv], axis=1)
        kr, kg, kb = self.bits
        r = (symbols >> (kg + kb)) & ((1 << kr) - 1)
        g = (symbols >> kb) & ((1 << kg) - 1)
        b = symbols & ((1 << kb) - 1)
        return np.stack([gray_to_binary_inverse(r), gray_to_binary_inverse(g), gray_to_binary_inverse(b)], axis=1)

    def levels_to_symbols(self, levels: np.ndarray) -> np.ndarray:
        """levels: (n, 3) channel levels -> (n,) symbols."""
        levels = np.asarray(levels, dtype=np.int64)
        if self.gray:
            return binary_to_gray(levels[:, 0])
        kr, kg, kb = self.bits
        r = binary_to_gray(levels[:, 0]) & ((1 << kr) - 1)
        g = binary_to_gray(levels[:, 1]) & ((1 << kg) - 1)
        b = binary_to_gray(levels[:, 2]) & ((1 << kb) - 1)
        return (r << (kg + kb)) | (g << kb) | b

    def levels_to_rgb(self, levels: np.ndarray) -> np.ndarray:
        """(n, 3) levels -> (n, 3) uint8 sRGB."""
        levels = np.asarray(levels, dtype=np.int64)
        out = np.empty(levels.shape, dtype=np.uint8)
        for c in range(3):
            out[:, c] = self.channel_values(c)[levels[:, c]]
        return out

    def rgb_to_levels_exact(self, rgb: np.ndarray) -> np.ndarray:
        """Nearest level per channel for ideal (undistorted) sRGB input."""
        rgb = np.asarray(rgb, dtype=np.float64)
        out = np.empty(rgb.shape, dtype=np.int64)
        for c in range(3):
            L = self.levels[c]
            out[:, c] = np.clip(np.round(rgb[:, c] / 255.0 * (L - 1)), 0, L - 1)
        return out


def binary_to_gray(n: np.ndarray) -> np.ndarray:
    n = np.asarray(n, dtype=np.int64)
    return n ^ (n >> 1)


def gray_to_binary_inverse(g: np.ndarray) -> np.ndarray:
    """Inverse Gray code (works for values < 2**16)."""
    g = np.asarray(g, dtype=np.int64).copy()
    for shift in (8, 4, 2, 1):
        g ^= g >> shift
    return g


# index -> profile. Indices 0..5 chromatic, 6..7 achromatic.
PROFILES: Dict[int, ColorProfile] = {
    0: ColorProfile(0, "rgb111", (1, 1, 1)),          # 8 colours,   3 bits/module
    1: ColorProfile(1, "rgb221", (2, 2, 1)),          # 32 colours,  5 bits/module
    2: ColorProfile(2, "rgb222", (2, 2, 2)),          # 64 colours,  6 bits/module
    3: ColorProfile(3, "rgb332", (3, 3, 2)),          # 256 colours, 8 bits/module
    4: ColorProfile(4, "rgb333", (3, 3, 3)),          # 512 colours, 9 bits/module
    5: ColorProfile(5, "rgb444", (4, 4, 4)),          # 4096 colours, 12 bits/module
    6: ColorProfile(6, "mono", (1, 1, 1), gray=True),  # black/white, 1 bit/module (QR-like baseline)
    7: ColorProfile(7, "gray4", (2, 2, 2), gray=True),  # 4 grey levels, 2 bits/module
}
PROFILES_BY_NAME: Dict[str, ColorProfile] = {p.name: p for p in PROFILES.values()}


def get_profile(spec) -> ColorProfile:
    """Accept a ColorProfile, an index, a name ('rgb222'), or a (kr,kg,kb) tuple."""
    if isinstance(spec, ColorProfile):
        return spec
    if isinstance(spec, int):
        return PROFILES[spec]
    if isinstance(spec, str):
        if spec in PROFILES_BY_NAME:
            return PROFILES_BY_NAME[spec]
        raise ValueError(f"unknown colour profile {spec!r}; known: {sorted(PROFILES_BY_NAME)}")
    if isinstance(spec, (tuple, list)) and len(spec) == 3:
        for p in PROFILES.values():
            if not p.gray and tuple(p.bits) == tuple(spec):
                return p
        raise ValueError(f"no profile with per-channel bits {tuple(spec)}")
    raise TypeError(f"cannot interpret colour profile {spec!r}")


# ---- error correction levels ---------------------------------------------
# name -> (2-bit QR encoding, nominal fraction of codewords recoverable)
EC_LEVELS = {"L": (0b01, 0.07), "M": (0b00, 0.15), "Q": (0b11, 0.25), "H": (0b10, 0.30)}
EC_BY_BITS = {bits: name for name, (bits, _) in EC_LEVELS.items()}


def pack_format_payload(ec_level: str, profile: ColorProfile) -> int:
    return (EC_LEVELS[ec_level][0] << 3) | profile.index


def unpack_format_payload(data5: int) -> Tuple[str, ColorProfile]:
    return EC_BY_BITS[(data5 >> 3) & 3], PROFILES[data5 & 7]
