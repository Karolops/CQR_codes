"""Rendering of a CQR Symbol to a raster image."""
from __future__ import annotations

import numpy as np
from PIL import Image

from .codec import Symbol

QUIET_ZONE = 4  # modules, as required by ISO/IEC 18004


def to_array(symbol: Symbol, module_px: int = 10, quiet: int = QUIET_ZONE) -> np.ndarray:
    """Return an (H, W, 3) uint8 RGB array with a white quiet zone."""
    rgb = symbol.rgb
    size = rgb.shape[0]
    canvas = np.full((size + 2 * quiet, size + 2 * quiet, 3), 255, dtype=np.uint8)
    canvas[quiet:quiet + size, quiet:quiet + size] = rgb
    if module_px != 1:
        canvas = np.repeat(np.repeat(canvas, module_px, axis=0), module_px, axis=1)
    return canvas


def to_image(symbol: Symbol, module_px: int = 10, quiet: int = QUIET_ZONE) -> Image.Image:
    return Image.fromarray(to_array(symbol, module_px, quiet), "RGB")


def save(symbol: Symbol, path: str, module_px: int = 10, quiet: int = QUIET_ZONE) -> None:
    img = to_image(symbol, module_px, quiet)
    if path.lower().endswith((".jpg", ".jpeg")):
        img.save(path, quality=95, subsampling=0)  # avoid chroma subsampling: colour IS the data
    else:
        img.save(path)
