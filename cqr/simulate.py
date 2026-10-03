"""Camera / print simulation used to evaluate decoder robustness.

The distortions are applied in a physically plausible order:
  symbol image -> perspective/rotation/scale (printing + camera pose)
  -> colour cast + gamma + contrast loss (illumination, paper, ink, sensor)
  -> channel cross-talk (ink/filter overlap) -> blur (focus) -> noise (sensor)
  -> JPEG compression (phone pipeline)
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image


@dataclass
class CameraParams:
    module_px: float = 6.0          # module size in the *captured* image (pixels)
    rotation_deg: float = 0.0
    tilt: float = 0.0               # perspective strength (0 = none, 0.3 = strong)
    blur_sigma: float = 0.6         # gaussian blur in pixels
    noise_sigma: float = 0.02       # additive gaussian noise (fraction of full scale)
    color_cast: Tuple[float, float, float] = (1.0, 1.0, 1.0)   # per-channel gain (illuminant)
    gamma: float = 1.0
    black_level: float = 0.0        # lifted blacks (fraction)
    white_level: float = 1.0        # crushed whites (fraction)
    crosstalk: float = 0.0          # fraction of each channel leaking into the other two
    jpeg_quality: Optional[int] = None
    background: float = 0.85        # grey level of the canvas around the symbol
    margin_px: int = 30
    seed: int = 0


def simulate(symbol_img: np.ndarray, p: CameraParams) -> np.ndarray:
    """symbol_img: (H, W, 3) uint8 at any module size (should include a quiet zone)."""
    rng = np.random.default_rng(p.seed)
    src = symbol_img.astype(np.float32) / 255.0
    h, w = src.shape[:2]

    # --- geometry: scale so that one module ~ module_px pixels (we assume the
    # input was rendered at an integer module size, inferred from the caller)
    scale = p.module_px / _infer_module_px(symbol_img)
    out_w, out_h = int(round(w * scale)), int(round(h * scale))
    canvas_w, canvas_h = out_w + 2 * p.margin_px, out_h + 2 * p.margin_px
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]], dtype=np.float32)
    # perspective tilt: move corners inward/outward asymmetrically
    t = p.tilt
    dst = dst + np.array([[t * out_w * 0.5, t * out_h * 0.3], [-t * out_w * 0.2, t * out_h * 0.1],
                          [0, -t * out_h * 0.2], [t * out_w * 0.3, 0]], dtype=np.float32)
    # rotation about centre
    th = np.deg2rad(p.rotation_deg)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]], dtype=np.float32)
    c = dst.mean(axis=0)
    dst = (dst - c) @ R.T + c
    dst -= dst.min(axis=0)
    span = dst.max(axis=0)
    canvas_w, canvas_h = int(np.ceil(span[0])) + 2 * p.margin_px, int(np.ceil(span[1])) + 2 * p.margin_px
    dst += p.margin_px
    H = cv2.getPerspectiveTransform(corners, dst)
    bg = np.full((canvas_h, canvas_w, 3), p.background, dtype=np.float32)
    warped = cv2.warpPerspective(src, H, (canvas_w, canvas_h), flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=(-1, -1, -1))
    mask = warped[..., 0] >= 0
    img = np.where(mask[..., None], warped, bg)

    # --- photometry
    img = np.clip(img, 0, 1) ** p.gamma
    img = img * np.array(p.color_cast, dtype=np.float32)
    img = p.black_level + img * (p.white_level - p.black_level)
    if p.crosstalk > 0:
        k = p.crosstalk
        X = np.array([[1 - 2 * k, k, k], [k, 1 - 2 * k, k], [k, k, 1 - 2 * k]], dtype=np.float32)
        img = img @ X.T
    if p.blur_sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), p.blur_sigma)
    if p.noise_sigma > 0:
        img = img + rng.normal(0, p.noise_sigma, img.shape).astype(np.float32)
    img = np.clip(img, 0, 1)
    out = (img * 255 + 0.5).astype(np.uint8)
    if p.jpeg_quality is not None:
        buf = io.BytesIO()
        Image.fromarray(out).save(buf, format="JPEG", quality=int(p.jpeg_quality))  # default 4:2:0 chroma subsampling
        out = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    return out


def _infer_module_px(symbol_img: np.ndarray) -> float:
    """Infer the module size of a cleanly rendered symbol image from the
    top-left finder: first non-white pixel to the end of the first run."""
    g = symbol_img.min(axis=2)
    h, w = g.shape
    # find the first non-white pixel along the diagonal
    for i in range(min(h, w)):
        if g[i, i] < 128:
            start = i
            break
    else:
        raise ValueError("no symbol found")
    # the top row of the finder is a single dark run exactly 7 modules wide
    row = g[start, :]
    j = start
    while j < w and row[j] < 128:
        j += 1
    return (j - start) / 7.0
