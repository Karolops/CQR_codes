"""Matrix-level CQR codec: payload <-> module colours.

Encoding pipeline
-----------------
payload bytes -> container (type, length, data, padding)
              -> RS blocks, interleave, whiten            (ecc.py)
              -> bit stream, chopped into bpm-bit symbols in QR placement order
              -> per-channel Gray-coded levels -> sRGB module colours
              -> function patterns coloured (finders R/G/B, rest black/white)

Decoding from an already sampled module grid is the exact inverse; the image
decoder (decoder.py) produces the module grid + per-module confidences.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

import numpy as np

from . import bch, layout
from .ecc import BlockStructure, block_structure, rs_decode, rs_encode, symbol_bits_for
from .profiles import ColorProfile, EC_LEVELS, get_profile, pack_format_payload, unpack_format_payload

# Colours of the function patterns
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
FINDER_COLORS = (RED, GREEN, BLUE)   # top-left, top-right, bottom-left
CYAN, MAGENTA, YELLOW = (0, 255, 255), (255, 0, 255), (255, 255, 0)
# Complementary finder cores (default since 2026-10-04): the 3x3 core of the red
# finder is cyan, of the green finder magenta, of the blue finder yellow.  With
# them all eight corners of the colour cube are measured references - printers
# mix subtractively, so the secondaries cannot be predicted from the primaries.
# The 1:1:3:1:1 finder profile is unchanged on the min-channel darkness image.
FINDER_CORE_COLORS = (CYAN, MAGENTA, YELLOW)

# Container header: 1 byte (type << 4 | MAGIC) + 2 bytes big-endian length
MAGIC = 0xC
TYPE_BYTES, TYPE_TEXT, TYPE_ZBYTES, TYPE_ZTEXT = 0, 1, 2, 3
HEADER_LEN = 3
PAD_BYTES = (0xEC, 0x11)


@dataclass
class Symbol:
    version: int
    ec_level: str
    profile: ColorProfile
    rgb: np.ndarray            # (size, size, 3) uint8 module colours
    levels: np.ndarray         # (n_data, 3) channel levels of data modules in placement order
    blocks: BlockStructure
    payload_bytes: int         # bytes of user payload actually stored
    core_complement: bool = True   # finder cores coloured C/M/Y (False: plain R/G/B finders)

    @property
    def size(self) -> int:
        return self.rgb.shape[0]

    @property
    def layout(self) -> layout.Layout:
        return layout.get_layout(self.version)

    @property
    def capacity_bytes(self) -> int:
        return data_bytes_for(self.blocks) - HEADER_LEN


@dataclass
class Decoded:
    data: Union[bytes, str]
    content_type: int
    version: int
    ec_level: str
    profile: ColorProfile
    corrected_codewords: int
    failed_blocks: int
    module_errors: Optional[int] = None  # filled by tests when ground truth is known

    @property
    def ok(self) -> bool:
        return self.failed_blocks == 0


# ---------------------------------------------------------------------------
def total_codewords(version: int, profile: ColorProfile) -> int:
    """Number of RS symbols (bytes, or 9/12-bit module-aligned symbols) in the symbol."""
    s = symbol_bits_for(profile.bits_per_module)
    return layout.get_layout(version).n_data_modules * profile.bits_per_module // s


def blocks_for(version: int, ec_level: str, profile: ColorProfile) -> BlockStructure:
    return block_structure(total_codewords(version, profile), ec_level, symbol_bits_for(profile.bits_per_module))


def data_bytes_for(bs: BlockStructure) -> int:
    """Payload container bytes that fit into the data symbols of a block structure."""
    return bs.data_codewords * bs.symbol_bits // 8


def capacity(version: int, ec_level: str, profile) -> int:
    """User payload capacity in bytes for the given parameters."""
    profile = get_profile(profile)
    return data_bytes_for(blocks_for(version, ec_level, profile)) - HEADER_LEN


def _bytes_to_symbols(data: bytes, n_symbols: int, symbol_bits: int) -> np.ndarray:
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    stream = np.zeros(n_symbols * symbol_bits, dtype=np.uint8)
    stream[:len(bits)] = bits[:len(stream)]
    weights = (1 << np.arange(symbol_bits - 1, -1, -1)).astype(np.int64)
    return stream.reshape(n_symbols, symbol_bits).astype(np.int64) @ weights


def _symbols_to_bytes(symbols: Sequence[int], symbol_bits: int) -> bytes:
    sym = np.asarray(symbols, dtype=np.int64)
    bits = ((sym[:, None] >> np.arange(symbol_bits - 1, -1, -1)) & 1).astype(np.uint8).reshape(-1)
    n_bytes = len(bits) // 8
    return np.packbits(bits[:n_bytes * 8]).tobytes()


def _build_container(data: Union[bytes, str], compress: bool) -> Tuple[bytes, int]:
    if isinstance(data, str):
        raw, ctype = data.encode("utf-8"), TYPE_TEXT
    else:
        raw, ctype = bytes(data), TYPE_BYTES
    if compress:
        z = zlib.compress(raw, 9)
        if len(z) < len(raw):
            raw, ctype = z, ctype + 2
    if len(raw) > 0xFFFF:
        raise ValueError("payload larger than 65535 bytes is not supported")
    header = bytes([(ctype << 4) | MAGIC, len(raw) >> 8, len(raw) & 0xFF])
    return header + raw, len(raw)


def _parse_container(buf: bytes) -> Tuple[Union[bytes, str], int]:
    if len(buf) < HEADER_LEN or (buf[0] & 0xF) != MAGIC:
        raise ValueError("bad container header (magic mismatch)")
    ctype = buf[0] >> 4
    n = (buf[1] << 8) | buf[2]
    body = buf[HEADER_LEN:HEADER_LEN + n]
    if len(body) != n:
        raise ValueError("container truncated")
    if ctype in (TYPE_ZBYTES, TYPE_ZTEXT):
        body = zlib.decompress(body)
    if ctype in (TYPE_TEXT, TYPE_ZTEXT):
        return body.decode("utf-8"), ctype
    if ctype in (TYPE_BYTES, TYPE_ZBYTES):
        return body, ctype
    raise ValueError(f"unknown content type {ctype}")


def encode(data: Union[bytes, str], ec_level: str = "M", profile="rgb222",
           version: Optional[int] = None, compress: bool = False, core_complement: bool = True) -> Symbol:
    """Encode a payload into a CQR Symbol (module colour matrix).
    core_complement: colour the finder cores cyan / magenta / yellow (see FINDER_CORE_COLORS)."""
    if ec_level not in EC_LEVELS:
        raise ValueError(f"ec_level must be one of {list(EC_LEVELS)}")
    profile = get_profile(profile)
    container, n_payload = _build_container(data, compress)

    if version is None:
        for v in range(layout.MIN_VERSION, layout.MAX_VERSION + 1):
            try:
                bs = blocks_for(v, ec_level, profile)
            except ValueError:
                continue
            if data_bytes_for(bs) >= len(container):
                version = v
                break
        if version is None:
            raise ValueError(f"payload of {n_payload} bytes does not fit in any version with "
                             f"profile {profile.name} and EC level {ec_level}")
    L = layout.get_layout(version)
    bs = blocks_for(version, ec_level, profile)
    if len(container) > data_bytes_for(bs):
        raise ValueError(f"payload needs {len(container)} bytes but version {version} "
                         f"({profile.name}, {ec_level}) holds only {data_bytes_for(bs)}")

    # pad to full data length (QR-style alternating pad bytes; whitened later)
    padded = bytearray(container)
    i = 0
    while len(padded) < data_bytes_for(bs):
        padded.append(PAD_BYTES[i & 1]); i += 1
    data_symbols = _bytes_to_symbols(bytes(padded), bs.data_codewords, bs.symbol_bits)
    message = rs_encode(list(data_symbols), bs)

    # RS symbol stream -> bit stream -> module symbols
    bpm = profile.bits_per_module
    msg = np.asarray(message, dtype=np.int64)
    bits = ((msg[:, None] >> np.arange(bs.symbol_bits - 1, -1, -1)) & 1).astype(np.uint8).reshape(-1)
    n_mod = L.n_data_modules
    stream = np.zeros(n_mod * bpm, dtype=np.uint8)
    stream[:len(bits)] = bits
    weights = (1 << np.arange(bpm - 1, -1, -1)).astype(np.int64)
    symbols = stream.reshape(n_mod, bpm).astype(np.int64) @ weights
    levels = profile.symbols_to_levels(symbols)

    rgb = function_pattern_colors(version, ec_level, profile, core_complement)
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    rgb[rows, cols] = profile.levels_to_rgb(levels)
    return Symbol(version, ec_level, profile, rgb, levels, bs, n_payload, core_complement)


def function_pattern_colors(version: int, ec_level: str, profile: ColorProfile,
                            core_complement: bool = True) -> np.ndarray:
    """RGB matrix with all function patterns drawn and data modules left white."""
    L = layout.get_layout(version)
    size = L.size
    rgb = np.full((size, size, 3), 255, dtype=np.uint8)
    kind = L.kind
    rgb[kind == layout.K_TIMING_DARK] = BLACK
    rgb[kind == layout.K_ALIGN_DARK] = BLACK
    rgb[kind == layout.K_DARK_MODULE] = BLACK
    for which, color in enumerate(FINDER_COLORS):
        rgb[L.finder_mask(which)] = color
    if core_complement:
        for which, color in enumerate(FINDER_CORE_COLORS):
            rgb[L.finder_core_mask(which)] = color

    fmt = bch.encode_format(pack_format_payload(ec_level, profile))
    for copy in layout.format_bit_positions(size):
        for bit, (r, c) in enumerate(copy):
            rgb[r, c] = BLACK if (fmt >> bit) & 1 else WHITE
    if version >= 7:
        ver = bch.encode_version(version)
        for copy in layout.version_bit_positions(size):
            for bit, (r, c) in enumerate(copy):
                rgb[r, c] = BLACK if (ver >> bit) & 1 else WHITE
    return rgb


# ---------------------------------------------------------------------------
def read_format(is_dark: np.ndarray) -> Tuple[str, ColorProfile, int]:
    """Read the format information from a boolean dark-module matrix.

    Both copies are tried individually and jointly (soft majority via sum of
    distances); returns (ec_level, profile, n_corrected_bits)."""
    size = is_dark.shape[0]
    words = []
    for copy in layout.format_bit_positions(size):
        w = 0
        for bit, (r, c) in enumerate(copy):
            if is_dark[r, c]:
                w |= 1 << bit
        words.append(w)
    best = None
    for w in words:
        res = bch.decode_format(w, max_errors=3)
        if res and (best is None or res[1] < best[1]):
            best = res
    if best is None:
        # joint decode: pick codeword minimising total Hamming distance to both copies
        from .bch import _format_table, _hamming
        cand = min(range(32), key=lambda d: _hamming(_format_table()[d], words[0]) + _hamming(_format_table()[d], words[1]))
        dist = _hamming(_format_table()[cand], words[0]) + _hamming(_format_table()[cand], words[1])
        if dist > 7:
            raise ValueError("format information unreadable")
        best = (cand, dist)
    ec, prof = unpack_format_payload(best[0])
    return ec, prof, best[1]


def read_version_info(is_dark: np.ndarray) -> Optional[int]:
    size = is_dark.shape[0]
    if size < layout.size_for_version(7):
        return None
    best = None
    for copy in layout.version_bit_positions(size):
        w = 0
        for bit, (r, c) in enumerate(copy):
            if is_dark[r, c]:
                w |= 1 << bit
        res = bch.decode_version(w)
        if res and (best is None or res[1] < best[1]):
            best = res
    return best[0] if best else None


def decode_levels(version: int, ec_level: str, profile: ColorProfile,
                  levels: np.ndarray, confidence: Optional[np.ndarray] = None) -> Decoded:
    """Decode from per-data-module channel levels (n_data, 3) in placement order.

    confidence: optional (n_data,) reliability per module (higher = better)."""
    bpm = profile.bits_per_module
    bs = blocks_for(version, ec_level, profile)
    sb = bs.symbol_bits
    symbols = profile.levels_to_symbols(levels)
    bits = ((symbols[:, None] >> np.arange(bpm - 1, -1, -1)) & 1).astype(np.uint8).reshape(-1)
    n_bits = bs.total_codewords * sb
    weights = (1 << np.arange(sb - 1, -1, -1)).astype(np.int64)
    msg = bits[:n_bits].reshape(-1, sb).astype(np.int64) @ weights
    rel = None
    if confidence is not None:
        conf_bits = np.repeat(np.asarray(confidence, dtype=np.float64), bpm)[:n_bits]
        rel = conf_bits.reshape(-1, sb).min(axis=1)   # a symbol is as reliable as its weakest module
    res = rs_decode(list(msg), bs, rel)
    try:
        data, ctype = _parse_container(_symbols_to_bytes(res.data, sb))
    except Exception as exc:  # noqa: BLE001
        if res.failed_blocks:
            raise ValueError(f"RS decoding failed for {res.failed_blocks} block(s)") from exc
        raise
    return Decoded(data, ctype, version, ec_level, profile, res.corrected, res.failed_blocks)


def decode_rgb_matrix(rgb: np.ndarray) -> Decoded:
    """Decode an ideal (noise-free) module colour matrix, e.g. Symbol.rgb."""
    rgb = np.asarray(rgb)
    size = rgb.shape[0]
    version = layout.version_for_size(size)
    lum = rgb.astype(np.float64).mean(axis=2)
    is_dark = lum < 128
    ec, prof, _ = read_format(is_dark)
    L = layout.get_layout(version)
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    levels = prof.rgb_to_levels_exact(rgb[rows, cols].reshape(-1, 3))
    return decode_levels(version, ec, prof, levels)
