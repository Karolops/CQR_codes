"""Image decoder: photo / scan -> payload.

Pipeline
--------
1. Finder detection.  The three finders are dark in the *min-channel* image
   (red, green and blue all have at least one zero channel), so the classic
   zxing 1:1:3:1:1 run-length scan on that image finds them with the same
   robustness as a monochrome QR reader.  Each candidate is then colour keyed
   by the purity of its 3x3 core: red = top-left, green = top-right,
   blue = bottom-left.  This resolves orientation (any rotation, even a
   mirrored capture) without geometric reasoning.  The purity maps themselves
   are scanned as a second candidate source.
2. Version estimation.  The finder-to-finder distance divided by the module
   size (measured from the finder run lengths and corrected for the symbol's
   rotation angle) gives a first estimate; a window of candidate versions
   around it is scored by how well the timing patterns alternate when sampled
   through each candidate's fitted grid, and the window is widened if no
   candidate scores well.  For V >= 7 the version information bits are read
   as a confirmation.
3. Grid fitting.  Three finder centres give an affine start.  Alignment
   patterns are then located one by one, nearest-to-finders first, with a
   5x5 template search around their predicted position, and the homography is
   refitted (least squares) after each hit so that predictions stay accurate
   even for strong perspective on large symbols (V1 has no alignment pattern
   and stays affine).
4. Sampling.  Each module is averaged over a small sub-grid around its centre
   (bilinear remap) to suppress noise / JPEG ringing while avoiding edges.
5. Shading correction.  Known-white modules (separators, finder/alignment
   light rings, timing light) and known-black modules (timing dark, alignment
   dark, dark module) are fitted with low-order polynomial fields per channel;
   every module is normalised by its local white/black -> compensates
   non-uniform illumination, vignetting and paper tint.
6. Colour calibration.  A 3x3 affine map (matrix + offset) is fitted by least
   squares from the measured red/green/blue finder colours plus white and
   black onto the ideal palette axes -> compensates printer/camera cross-talk
   and colour casts.
7. Level classification.  Per channel, the corrected values of all data
   modules are clustered with 1-D k-means seeded at the ideal level positions
   (absorbs gamma for multi-level profiles).  Each module gets a confidence.
8. Format information (black/white BCH(15,5)) gives EC level and colour
   profile; symbols -> bits -> RS decoding, with the least confident bytes
   used as erasures when plain decoding fails (codec.py / ecc.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # e.g. Pyodide in the browser: numpy fallbacks below are used
    cv2 = None

from . import codec, layout, palette


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------
def load_image(src) -> np.ndarray:
    """Accept a path, PIL image or numpy array -> float32 RGB array in [0,1]."""
    if isinstance(src, str):
        img = np.asarray(Image.open(src).convert("RGB"))
    elif isinstance(src, Image.Image):
        img = np.asarray(src.convert("RGB"))
    else:
        img = np.asarray(src)
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        if img.shape[2] == 4:
            img = img[..., :3]
    if img.dtype == np.uint8:
        return np.ascontiguousarray(img.astype(np.float32) / 255.0)
    if np.issubdtype(img.dtype, np.floating) and img.max() <= 1.0:
        return np.ascontiguousarray(np.clip(img, 0, 1).astype(np.float32))   # already normalised
    return np.ascontiguousarray(np.clip(img, 0, 255).astype(np.float32) / 255.0)


@dataclass
class FinderCandidate:
    x: float
    y: float
    module: float
    votes: int = 1
    score: float = 0.0
    purity: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # ring purity per channel
    core: Tuple[float, float, float] = (0.0, 0.0, 0.0)     # mean RGB of the 3x3 core


# ---------------------------------------------------------------------------
# 1. finder detection
# ---------------------------------------------------------------------------
def purity_maps(img: np.ndarray) -> List[np.ndarray]:
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return [r - np.maximum(g, b), g - np.maximum(r, b), b - np.maximum(r, g)]


def darkness_map(img: np.ndarray) -> np.ndarray:
    return 1.0 - img.min(axis=2)


def _runs(line: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    n = len(line)
    change = np.flatnonzero(line[1:] != line[:-1]) + 1
    starts = np.concatenate(([0], change))
    lengths = np.diff(np.concatenate((starts, [n])))
    return starts, lengths


def _check_ratio(lengths: np.ndarray) -> Optional[float]:
    total = lengths.sum()
    if total < 7:
        return None
    m = total / 7.0
    tol = max(m * 0.5, 1.0)
    if (abs(lengths[0] - m) < tol and abs(lengths[1] - m) < tol and abs(lengths[2] - 3 * m) < 3 * tol
            and abs(lengths[3] - m) < tol and abs(lengths[4] - m) < tol):
        return m
    return None


def _scan_line(binary_line: np.ndarray) -> List[Tuple[float, float]]:
    out = []
    starts, lengths = _runs(binary_line)
    if len(lengths) < 5:
        return out
    first_dark = 0 if binary_line[starts[0]] else 1
    for i in range(first_dark, len(lengths) - 4, 2):
        m = _check_ratio(lengths[i:i + 5])
        if m is not None:
            out.append((starts[i + 2] + lengths[i + 2] / 2.0, m))
    return out


def _cross_check(binary: np.ndarray, x: float, y: float, m: float) -> Optional[Tuple[float, float, float]]:
    h, w = binary.shape
    xi = int(round(x))
    if not 0 <= xi < w:
        return None
    best = None
    for (cy, my) in _scan_line(binary[:, xi]):
        if abs(cy - y) < 2.5 * m and (best is None or abs(cy - y) < abs(best[0] - y)):
            best = (cy, my)
    if best is None:
        return None
    cy, my = best
    yi = int(round(cy))
    best2 = None
    for (cx, mx) in _scan_line(binary[yi, :]):
        if abs(cx - x) < 2.5 * m and (best2 is None or abs(cx - x) < abs(best2[0] - x)):
            best2 = (cx, mx)
    if best2 is None:
        return None
    cx, mx = best2
    if not (0.6 < mx / my < 1.6):
        return None
    # diagonal check (zxing style): the pattern must also hold along a 45 degree line
    for sx, sy in ((1, 1), (1, -1)):
        n = int(4 * (mx + my))
        xs = np.clip(np.round(cx + sx * np.arange(-n, n + 1)).astype(int), 0, w - 1)
        ys = np.clip(np.round(cy + sy * np.arange(-n, n + 1)).astype(int), 0, h - 1)
        diag = binary[ys, xs]
        if not any(abs(c - n) < 1.5 * (mx + my) / 2 for (c, _) in _scan_line(diag)):
            return None
    return cx, cy, (mx + my) / 2.0


def _scan_candidates(binary: np.ndarray, step: int) -> List[FinderCandidate]:
    h, w = binary.shape
    cands: List[FinderCandidate] = []
    for y in range(0, h, step):
        for (cx, m) in _scan_line(binary[y, :]):
            res = _cross_check(binary, cx, y, m)
            if res is None:
                continue
            rx, ry, rm = res
            for c in cands:
                if abs(c.x - rx) < rm * 1.5 and abs(c.y - ry) < rm * 1.5:
                    n = c.votes
                    c.x = (c.x * n + rx) / (n + 1)
                    c.y = (c.y * n + ry) / (n + 1)
                    c.module = (c.module * n + rm) / (n + 1)
                    c.votes += 1
                    break
            else:
                cands.append(FinderCandidate(rx, ry, rm))
    for c in cands:
        expected = max(1.0, 3.0 * c.module / step)
        c.score = min(c.votes / expected, 1.5)
    return cands


def _merge(cands: List[FinderCandidate], new: List[FinderCandidate]) -> None:
    for n in new:
        for c in cands:
            if abs(c.x - n.x) < 1.5 * c.module and abs(c.y - n.y) < 1.5 * c.module:
                if n.score > c.score:
                    c.x, c.y, c.module, c.votes, c.score = n.x, n.y, n.module, n.votes, n.score
                break
        else:
            cands.append(n)


def _finder_colours(img: np.ndarray, c: FinderCandidate) -> Tuple[np.ndarray, np.ndarray]:
    """(mean purity (R-max(G,B), ...) of the finder's outer ring, mean RGB of its 3x3 core).
    The ring identifies the finder colour; the core may carry the complementary colour."""
    h, w = img.shape[:2]
    R = int(round(c.module * 3.6)) + 1
    x0, x1 = max(0, int(round(c.x)) - R), min(w, int(round(c.x)) + R + 1)
    y0, y1 = max(0, int(round(c.y)) - R), min(h, int(round(c.y)) + R + 1)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(xs - c.x, ys - c.y) / max(c.module, 1e-6)
    patch = img[y0:y1, x0:x1]
    ring = patch[(d > 2.6) & (d < 3.4)]
    core = patch[d < 1.2]
    if len(ring) == 0:
        ring = patch.reshape(-1, 3)
    if len(core) == 0:
        core = patch.reshape(-1, 3)
    rm, cm = ring.mean(axis=0), core.mean(axis=0)
    purity = np.array([rm[0] - max(rm[1], rm[2]), rm[1] - max(rm[0], rm[2]), rm[2] - max(rm[0], rm[1])])
    return purity, cm


def _refine_centre(dark: np.ndarray, c: FinderCandidate) -> None:
    """Refine the finder centre as the darkness-weighted centroid of the 3x3 core."""
    h, w = dark.shape
    r = max(1, int(round(c.module * 1.5)))
    x0, x1 = max(0, int(round(c.x)) - r), min(w, int(round(c.x)) + r + 1)
    y0, y1 = max(0, int(round(c.y)) - r), min(h, int(round(c.y)) + r + 1)
    patch = dark[y0:y1, x0:x1]
    wgt = np.clip(patch - np.median(patch) * 0.5, 0, None)
    if wgt.sum() > 0:
        ys, xs = np.mgrid[y0:y1, x0:x1]
        nx, ny = float((xs * wgt).sum() / wgt.sum()), float((ys * wgt).sum() / wgt.sum())
        if abs(nx - c.x) < c.module and abs(ny - c.y) < c.module:
            c.x, c.y = nx, ny


def finder_candidates(img: np.ndarray, step: Optional[int] = None) -> List[FinderCandidate]:
    """All finder-pattern candidates of an image, centre-refined, with colour purity.
    step: row stride of the run scan (default: ~500 scan lines per image)."""
    h, w = img.shape[:2]
    if step is None:
        step = max(1, min(h, w) // 500)
    dark = darkness_map(img)
    cands: List[FinderCandidate] = []
    # darkness map at several thresholds (robust to blur / contrast loss)
    lo, hi = np.percentile(dark, 5), np.percentile(dark, 95)
    # small coloured finders (chroma-blurred by JPEG) are only a little darker
    # than the mid threshold, hence the intermediate steps
    for f in (0.5, 0.35, 0.65, 0.42, 0.58):
        binary = dark > lo + f * (hi - lo)
        _merge(cands, _scan_candidates(binary, step))
    # purity maps as a second source (absolute value: a finder ring and its
    # complementary core are both strongly "pure" in the same channel)
    for pm in purity_maps(img):
        pm = np.abs(pm)
        pos = pm[pm > 0]
        if pos.size < 50:
            continue
        top = np.percentile(pos, 99.5)
        if top < 0.1:
            continue
        for f in (0.45, 0.3):
            _merge(cands, _scan_candidates(pm > f * top, step))
    for c in cands:
        _refine_centre(dark, c)
        purity, core = _finder_colours(img, c)
        c.purity = tuple(float(v) for v in purity)
        c.core = tuple(float(v) for v in core)
    return cands


def detect_finders(img: np.ndarray) -> Tuple[FinderCandidate, FinderCandidate, FinderCandidate]:
    """The red / green / blue finder of the (single) symbol in the image."""
    cands = finder_candidates(img)
    if len(cands) < 3:
        raise ValueError(f"could not locate three finder patterns (found {len(cands)})")
    # assign the best candidate to each colour
    chosen: List[Optional[FinderCandidate]] = [None, None, None]
    pool = sorted(cands, key=lambda c: c.score, reverse=True)
    for colour in range(3):
        best, best_val = None, -np.inf
        for c in pool:
            if any(c is ch for ch in chosen):
                continue
            p = c.purity[colour]
            val = p * (0.5 + c.score)
            if p > 0.05 and val > best_val:
                best, best_val = c, val
        chosen[colour] = best
    names = ["red (top-left)", "green (top-right)", "blue (bottom-left)"]
    missing = [n for n, f in zip(names, chosen) if f is None]
    if missing:
        raise ValueError("could not identify finder pattern(s): " + ", ".join(missing))
    return chosen[0], chosen[1], chosen[2]  # type: ignore[return-value]


def detect_symbols(img: np.ndarray, min_purity: float = 0.05, step: Optional[int] = None
                   ) -> List[Tuple[FinderCandidate, FinderCandidate, FinderCandidate]]:
    """Group finder candidates into (red, green, blue) triples, one per symbol.

    A valid triple has similar module sizes, |RG| ~ |RB| (the two symbol edges),
    RG roughly perpendicular to RB, and an edge length of 10..200 modules.
    Triples are accepted greedily by score so that no finder is used twice."""
    cands = finder_candidates(img, step)
    reds = [c for c in cands if c.purity[0] > min_purity]
    greens = [c for c in cands if c.purity[1] > min_purity]
    blues = [c for c in cands if c.purity[2] > min_purity]
    triples = []
    for r in reds:
        pr = np.array([r.x, r.y])
        for g in greens:
            if g is r:
                continue
            pg = np.array([g.x, g.y])
            v1 = pg - pr
            d1 = float(np.linalg.norm(v1))
            m_rg = 0.5 * (r.module + g.module)
            if not (10 * m_rg < d1 < 200 * m_rg) or max(r.module, g.module) > 1.5 * min(r.module, g.module):
                continue
            for b in blues:
                if b is r or b is g:
                    continue
                pb = np.array([b.x, b.y])
                v2 = pb - pr
                d2 = float(np.linalg.norm(v2))
                if not (0.85 < d2 / d1 < 1.18) or max(r.module, b.module) > 1.5 * min(r.module, b.module):
                    continue
                cosang = float(v1 @ v2) / (d1 * d2)
                if abs(cosang) > 0.25:
                    continue
                # module count implied by the finder spacing must be close to a valid version size
                m = (r.module + g.module + b.module) / 3.0
                n_mod = 0.5 * (d1 + d2) / m + 7.0
                v_est = (n_mod - 17) / 4.0
                if abs(v_est - round(v_est)) > 0.35 and n_mod > 30:
                    continue
                score = (r.purity[0] + g.purity[1] + b.purity[2]) * (1.5 + r.score + g.score + b.score) \
                    - 2.0 * abs(cosang) - 2.0 * abs(d2 / d1 - 1.0)
                triples.append((score, r, g, b))
    triples.sort(key=lambda t: t[0], reverse=True)
    used: List[FinderCandidate] = []
    out = []
    for score, r, g, b in triples:
        if any(f is u for f in (r, g, b) for u in used):
            continue
        used += [r, g, b]
        out.append((r, g, b))
    return out


# ---------------------------------------------------------------------------
# 2./3. geometry
# ---------------------------------------------------------------------------
def _module_points(size: int) -> Dict[str, np.ndarray]:
    return {"tl": np.array([3.5, 3.5]), "tr": np.array([size - 3.5, 3.5]), "bl": np.array([3.5, size - 3.5])}


def _apply_h(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    p = np.concatenate([pts, np.ones((len(pts), 1))], axis=1) @ H.T
    return p[:, :2] / p[:, 2:3]


def _fit_h(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if len(src) == 3:
        A = np.concatenate([src, np.ones((3, 1))], axis=1)
        M, *_ = np.linalg.lstsq(A, dst, rcond=None)          # exact affine through 3 points
        H = np.eye(3)
        H[:2, :] = M.T
        return H
    if cv2 is not None:
        H, _ = cv2.findHomography(src.astype(np.float64), dst.astype(np.float64), 0)
        return H
    return _dlt_homography(src, dst)


def _dlt_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares homography (normalised direct linear transform)."""
    def normalise(p):
        c = p.mean(axis=0)
        s = np.sqrt(2.0) / max(np.mean(np.linalg.norm(p - c, axis=1)), 1e-9)
        T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
        q = np.concatenate([p, np.ones((len(p), 1))], axis=1) @ T.T
        return q, T
    s_n, Ts = normalise(src)
    d_n, Td = normalise(dst)
    rows = []
    for (x, y, _), (u, v, _) in zip(s_n, d_n):
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
    _, _, vt = np.linalg.svd(np.array(rows))
    Hn = vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    return H / H[2, 2]


def _sample(img: np.ndarray, H: np.ndarray, module_xy: np.ndarray, sub: int = 3, spread: float = 0.5) -> np.ndarray:
    """Sample colours at module-space points (n,2) through H, averaging a sub x sub patch."""
    n = len(module_xy)
    if sub > 1:
        offs = (np.arange(sub) + 0.5) / sub - 0.5
        ox, oy = np.meshgrid(offs * spread, offs * spread)
        offsets = np.stack([ox.ravel(), oy.ravel()], axis=1)
    else:
        offsets = np.zeros((1, 2))
    pts = (module_xy[:, None, :] + offsets[None, :, :]).reshape(-1, 2)
    return _sample_points(img, _apply_h(H, pts)).reshape(n, len(offsets), 3).mean(axis=1)


def _sample_points(img: np.ndarray, ipts: np.ndarray) -> np.ndarray:
    """Bilinear samples of img at image coordinates (n,2) -> (n,3)."""
    ipts = np.asarray(ipts, dtype=np.float32)
    if cv2 is None:
        h, w = img.shape[:2]
        x = np.clip(ipts[:, 0], 0, w - 1)
        y = np.clip(ipts[:, 1], 0, h - 1)
        x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
        x1 = np.minimum(x0 + 1, w - 1); y1 = np.minimum(y0 + 1, h - 1)
        fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
        return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
                + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)
    total = len(ipts)
    cols = int(np.ceil(np.sqrt(total)))
    rows = int(np.ceil(total / cols))
    pad = rows * cols - total
    if pad:
        ipts = np.concatenate([ipts, np.repeat(ipts[-1:], pad, axis=0)], axis=0)
    mapx = np.ascontiguousarray(ipts[:, 0].reshape(rows, cols))
    mapy = np.ascontiguousarray(ipts[:, 1].reshape(rows, cols))
    vals = cv2.remap(img, mapx, mapy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return vals.reshape(-1, 3)[:total]


def _timing_score(img: np.ndarray, H: np.ndarray, size: int) -> float:
    idx = np.arange(8, size - 8)
    pts = np.concatenate([
        np.stack([idx + 0.5, np.full(len(idx), 6.5)], axis=1),
        np.stack([np.full(len(idx), 6.5), idx + 0.5], axis=1),
    ])
    expect_dark = np.concatenate([(idx % 2 == 0), (idx % 2 == 0)])
    lum = _sample(img, H, pts, sub=2, spread=0.4).min(axis=1)
    thr = 0.5 * (lum[expect_dark].mean() + lum[~expect_dark].mean())
    ok = (lum < thr) == expect_dark
    contrast = float(lum[~expect_dark].mean() - lum[expect_dark].mean())
    return float(ok.mean()) * min(1.0, max(0.0, contrast / 0.08))


_ALIGN_OFFS = np.arange(-2, 3)
_ALIGN_OX, _ALIGN_OY = np.meshgrid(_ALIGN_OFFS, _ALIGN_OFFS)
_ALIGN_TMPL = np.where(np.maximum(np.abs(_ALIGN_OX), np.abs(_ALIGN_OY)) == 1, 1.0, -1.0).ravel()
_ALIGN_TMPL -= _ALIGN_TMPL.mean()
_ALIGN_PTS = np.stack([_ALIGN_OX.ravel(), _ALIGN_OY.ravel()], axis=1).astype(np.float64)


def _find_alignment(img: np.ndarray, H: np.ndarray, centre_xy: np.ndarray, search: float = 1.5,
                    step: float = 0.25, min_score: float = 0.55) -> Optional[Tuple[np.ndarray, float]]:
    """Template-search an alignment pattern around its predicted module-space
    centre. Returns (image coordinates of the centre, correlation) or None."""
    shifts = np.arange(-search, search + 1e-9, step)
    sx, sy = np.meshgrid(shifts, shifts)
    shift_pts = np.stack([sx.ravel(), sy.ravel()], axis=1)            # (S, 2)
    pts = centre_xy[None, None, :] + shift_pts[:, None, :] + _ALIGN_PTS[None, :, :]   # (S, 25, 2)
    lum = _sample(img, H, pts.reshape(-1, 2), sub=2, spread=0.4).min(axis=1).reshape(len(shift_pts), 25)
    lum = lum - lum.mean(axis=1, keepdims=True)
    denom = np.linalg.norm(lum, axis=1) * np.linalg.norm(_ALIGN_TMPL)
    score = (lum @ _ALIGN_TMPL) / np.maximum(denom, 1e-6)
    i = int(score.argmax())
    if score[i] < min_score:
        return None
    best = shift_pts[i].copy()
    # parabolic refinement along x and y when neighbours are available
    S = len(shifts)
    iy, ix = divmod(i, S)
    sc = score.reshape(S, S)
    for axis, idx in ((0, ix), (1, iy)):
        if 0 < idx < S - 1:
            a, b, c = (sc[iy, idx - 1], sc[iy, idx], sc[iy, idx + 1]) if axis == 0 else (sc[idx - 1, ix], sc[idx, ix], sc[idx + 1, ix])
            den = a - 2 * b + c
            if den < 0:
                best[axis] += step * 0.5 * (a - c) / den
    return _apply_h(H, (centre_xy + best).reshape(1, 2))[0], float(score[i])


@dataclass
class Geometry:
    version: int
    size: int
    H: np.ndarray
    finders: Tuple[FinderCandidate, FinderCandidate, FinderCandidate]
    timing_score: float
    n_alignment: int
    candidates: Dict[int, float] = field(default_factory=dict)


def _fit_grid(img: np.ndarray, version: int, finders) -> Tuple[np.ndarray, int]:
    """Fit module->image homography for one version using finders + alignment chaining."""
    size = layout.size_for_version(version)
    L = layout.get_layout(version)
    mp = _module_points(size)
    src = [mp["tl"], mp["tr"], mp["bl"]]
    dst = [np.array([f.x, f.y]) for f in finders]
    H = _fit_h(np.stack(src), np.stack(dst))
    if version < 2:
        return H, 0
    # order alignment patterns by distance to the nearest finder centre
    centres = [np.array([c + 0.5, r + 0.5]) for (r, c) in L.align_centres]
    fin = np.stack(src)
    centres.sort(key=lambda p: np.min(np.linalg.norm(fin - p, axis=1)))
    found = 0
    for p in centres:
        res = _find_alignment(img, H, p)
        if res is None:
            continue
        src.append(p)
        dst.append(res[0])
        found += 1
        H = _fit_h(np.stack(src), np.stack(dst))
    return H, found


def estimate_geometry(img: np.ndarray, finders=None, version_hint: Optional[int] = None) -> Geometry:
    if finders is None:
        finders = detect_finders(img)
    tl, tr, bl = finders
    p_tl, p_tr, p_bl = (np.array([f.x, f.y]) for f in finders)
    m = float(np.mean([tl.module, tr.module, bl.module]))

    results: Dict[int, Tuple[float, np.ndarray, int]] = {}

    def evaluate(versions) -> None:
        for v in versions:
            if v in results or not layout.MIN_VERSION <= v <= layout.MAX_VERSION:
                continue
            H, n_align = _fit_grid(img, v, finders)
            results[v] = (_timing_score(img, H, layout.size_for_version(v)), H, n_align)

    if version_hint is not None:
        evaluate([version_hint])
        v_est = version_hint
    else:
        # The module size measured by axis-aligned run scanning is inflated by
        # 1/cos(angle) when the symbol is rotated: correct it with the angle of
        # the top-left -> top-right axis folded into [0, 45] degrees.
        ang = np.degrees(np.arctan2(p_tr[1] - p_tl[1], p_tr[0] - p_tl[0])) % 90.0
        m_corr = m * np.cos(np.radians(min(ang, 90.0 - ang)))
        d = 0.5 * (np.linalg.norm(p_tr - p_tl) + np.linalg.norm(p_bl - p_tl)) / m_corr + 7.0
        v_est = int(np.clip(round((d - 17) / 4.0), layout.MIN_VERSION, layout.MAX_VERSION))
        # the relative error of m grows with blur; the version error grows with symbol size
        spread = 1 + int(d // 60)
        evaluate(range(v_est - spread, v_est + spread + 1))
        if max(r[0] for r in results.values()) < 0.8:
            evaluate(range(v_est - 2 * spread - 2, v_est + 2 * spread + 3))

    best_v = max(results, key=lambda v: results[v][0])
    score, H, n_align = results[best_v]
    if score < 0.6:
        raise ValueError(f"could not establish the module grid (best timing score {score:.2f})")
    return Geometry(best_v, layout.size_for_version(best_v), H, finders, score, n_align,
                    {v: r[0] for v, r in results.items()})


# ---------------------------------------------------------------------------
# 4.-8. sampling, shading, calibration, classification, decoding
# ---------------------------------------------------------------------------
def sample_grid(img: np.ndarray, geo: Geometry, sub: int = 3, spread: float = 0.5) -> np.ndarray:
    size = geo.size
    rows, cols = np.mgrid[0:size, 0:size]
    pts = np.stack([cols.ravel() + 0.5, rows.ravel() + 0.5], axis=1).astype(np.float64)
    return _sample(img, geo.H, pts, sub=sub, spread=spread).reshape(size, size, 3)


def _poly_design(rows: np.ndarray, cols: np.ndarray, size: int, degree: int) -> np.ndarray:
    x = (cols + 0.5) / size * 2 - 1
    y = (rows + 0.5) / size * 2 - 1
    terms = [np.ones_like(x), x, y]
    if degree >= 2:
        terms += [x * x, y * y, x * y]
    return np.stack(terms, axis=1)


def shading_fields(samples: np.ndarray, L: layout.Layout) -> Tuple[np.ndarray, np.ndarray]:
    """Fit per-channel white and black fields (size,size,3) from known modules."""
    kind = L.kind
    size = L.size
    white_mask = (kind == layout.K_SEPARATOR) | (kind == layout.K_FINDER_LIGHT) | (kind == layout.K_TIMING_LIGHT) \
        | (kind == layout.K_ALIGN_LIGHT)
    black_mask = (kind == layout.K_TIMING_DARK) | (kind == layout.K_ALIGN_DARK) | (kind == layout.K_DARK_MODULE)
    rr, cc = np.mgrid[0:size, 0:size]
    out = []
    for mask, degree in ((white_mask, 2 if L.version >= 2 else 1), (black_mask, 1)):
        r, c = rr[mask], cc[mask]
        A = _poly_design(r, c, size, degree)
        Y = samples[mask]                                      # (n, 3)
        # robust-ish: two rounds, dropping outliers beyond 2.5 MAD on the first fit
        coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
        resid = np.linalg.norm(Y - A @ coef, axis=1)
        mad = np.median(np.abs(resid - np.median(resid))) + 1e-6
        keep = resid < np.median(resid) + 2.5 * 1.4826 * mad
        if keep.sum() >= A.shape[1] + 2:
            coef, *_ = np.linalg.lstsq(A[keep], Y[keep], rcond=None)
        full = _poly_design(rr.ravel(), cc.ravel(), size, degree) @ coef
        out.append(full.reshape(size, size, 3))
    return out[0], out[1]


@dataclass
class Calibration:
    M: np.ndarray
    offset: np.ndarray
    refs_measured: Dict[str, np.ndarray]
    white_field: np.ndarray
    black_field: np.ndarray

    def apply(self, samples: np.ndarray) -> np.ndarray:
        """samples (size,size,3) raw -> corrected (size,size,3) in ideal palette space."""
        span = np.maximum(self.white_field - self.black_field, 0.05)
        norm = (samples - self.black_field) / span
        return norm.reshape(-1, 3) @ self.M.T + self.offset


IDEAL_REFS = {
    "red": np.array([1.0, 0.0, 0.0]), "green": np.array([0.0, 1.0, 0.0]), "blue": np.array([0.0, 0.0, 1.0]),
    "white": np.array([1.0, 1.0, 1.0]), "black": np.array([0.0, 0.0, 0.0]),
}


def calibrate(samples: np.ndarray, L: layout.Layout) -> Calibration:
    white_f, black_f = shading_fields(samples, L)
    span = np.maximum(white_f - black_f, 0.05)
    norm = (samples - black_f) / span
    kind = L.kind
    meas = {}
    for name, which in (("red", 0), ("green", 1), ("blue", 2)):
        meas[name] = np.median(norm[L.finder_ring_mask(which)], axis=0)
    white_mask = (kind == layout.K_SEPARATOR) | (kind == layout.K_FINDER_LIGHT) | (kind == layout.K_TIMING_LIGHT) \
        | (kind == layout.K_ALIGN_LIGHT)
    black_mask = (kind == layout.K_TIMING_DARK) | (kind == layout.K_ALIGN_DARK) | (kind == layout.K_DARK_MODULE)
    meas["white"] = np.median(norm[white_mask], axis=0)
    meas["black"] = np.median(norm[black_mask], axis=0)
    names = list(IDEAL_REFS)
    X = np.stack([np.concatenate([meas[n], [1.0]]) for n in names])
    Y = np.stack([IDEAL_REFS[n] for n in names])
    w = np.array([1.0, 1.0, 1.0, 1.5, 1.5])
    coef, *_ = np.linalg.lstsq(X * w[:, None], Y * w[:, None], rcond=None)
    raw_refs = {}
    for name, which in (("red", 0), ("green", 1), ("blue", 2)):
        raw_refs[name] = np.median(samples[L.finder_ring_mask(which)], axis=0)
    raw_refs["white"] = np.median(samples[white_mask], axis=0)
    raw_refs["black"] = np.median(samples[black_mask], axis=0)
    if detect_core_complement(samples, L):
        for name, which in (("cyan", 0), ("magenta", 1), ("yellow", 2)):
            raw_refs[name] = np.median(samples[L.finder_core_mask(which)], axis=0)
    return Calibration(coef[:3, :].T, coef[3, :], raw_refs, white_f, black_f)


def detect_core_complement(samples: np.ndarray, L: layout.Layout) -> bool:
    """True when the finder cores carry the complementary colours (cyan in the red
    finder, ...) instead of the ring colour.  Decided by majority over the three
    finders from the core's saturation in the ring's own channel."""
    votes = 0
    for which in range(3):
        ring = np.median(samples[L.finder_ring_mask(which)], axis=0)
        core = np.median(samples[L.finder_core_mask(which)], axis=0)
        others = [i for i in range(3) if i != which]
        ring_sat = ring[which] - ring[others].mean()
        core_sat = core[which] - core[others].mean()
        votes += core_sat < 0.5 * ring_sat
    return votes >= 2


def classify_levels(values: np.ndarray, n_levels: int, refine: bool = True,
                    iters: int = 8) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """1-D classification of corrected channel values into n_levels levels.
    Returns (levels, confidence in [0,1], centroids)."""
    centroids = np.linspace(0.0, 1.0, n_levels)
    v = values.astype(np.float64)
    if refine and v.size >= 8 * n_levels:
        # The codeword stream is whitened, so every level is used equally often:
        # the quantiles of the observed values are a gamma-independent initial
        # estimate of the level centroids (robust for 4..16 levels per channel).
        q = np.quantile(v, (np.arange(n_levels) + 0.5) / n_levels)
        if np.all(np.diff(q) > 0.25 / max(1, n_levels - 1)):
            centroids = 0.5 * (centroids + q) if n_levels == 2 else q
        for _ in range(iters):
            d = np.abs(v[:, None] - centroids[None, :])
            lab = d.argmin(axis=1)
            new = centroids.copy()
            for i in range(n_levels):
                sel = v[lab == i]
                if sel.size >= max(3, v.size // (20 * n_levels)):
                    new[i] = sel.mean()
            new = np.sort(new)
            if np.all(np.diff(new) > 0.25 / max(1, n_levels - 1)):
                centroids = new
            else:
                break
    d = np.abs(v[:, None] - centroids[None, :])
    lab = d.argmin(axis=1)
    if n_levels == 1:
        return lab, np.ones_like(v), centroids
    srt = np.sort(d, axis=1)
    conf = np.clip((srt[:, 1] - srt[:, 0]) / np.maximum(srt[:, 1] + srt[:, 0], 1e-9), 0.0, 1.0)
    return lab, conf, centroids


def _ideal_matrix(corrected: np.ndarray, levels: np.ndarray, prof, L: layout.Layout,
                  core_complement: bool = False) -> np.ndarray:
    """Ideal corrected colour of every module given the current data classification."""
    ideal = codec.function_pattern_colors(L.version, "L", prof, core_complement).astype(np.float64) / 255.0
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    if prof.gray:
        lv = levels[:, 0] / max(1, prof.levels[0] - 1)
        ideal[rows, cols] = np.stack([lv, lv, lv], axis=1)
    else:
        ideal[rows, cols] = levels / np.maximum(1, np.array(prof.levels) - 1)[None, :]
    # format bits were drawn with a dummy EC level above: use the observed values instead
    fmt = L.kind == layout.K_FORMAT
    ideal[fmt] = np.clip(corrected[fmt], 0, 1)
    return ideal


def cancel_interference(corrected: np.ndarray, levels: np.ndarray, prof, L: layout.Layout,
                        iters: int = 2, core_complement: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Neighbour interference cancellation.

    Blur, chroma subsampling and ink spread mix each module with its 4
    neighbours.  Model per channel c:  observed = ideal + a_c * sum_n (ideal_n - ideal).
    a_c is estimated by least squares over all data modules from the current
    classification, the leak is subtracted and the modules are reclassified.
    Returns (cleaned corrected matrix, leak coefficients per channel)."""
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    cleaned = corrected.copy()
    alpha = np.zeros(3)
    for _ in range(iters):
        ideal = _ideal_matrix(corrected, levels, prof, L, core_complement)
        pad = np.pad(ideal, ((1, 1), (1, 1), (0, 0)), mode="edge")
        nsum = pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:] - 4 * ideal
        x = nsum[rows, cols]
        y = corrected[rows, cols] - ideal[rows, cols]
        for c in range(3):
            xx = float((x[:, c] * x[:, c]).sum())
            alpha[c] = float((x[:, c] * y[:, c]).sum() / xx) if xx > 1e-9 else 0.0
        alpha = np.clip(alpha, 0.0, 0.3)
        cleaned = corrected - nsum * alpha[None, None, :]
        vals = cleaned[rows, cols]
        if prof.gray:
            lab, _, _ = classify_levels(vals.mean(axis=1), prof.levels[0], refine=False)
            levels = np.repeat(lab[:, None], 3, axis=1)
        else:
            levels = np.stack([classify_levels(vals[:, c], prof.levels[c], refine=False)[0] for c in range(3)], axis=1)
    return cleaned, alpha


@dataclass
class DecodeReport:
    result: codec.Decoded
    geometry: Geometry
    calibration: Calibration
    centroids: List[np.ndarray]
    mean_confidence: float
    format_errors: int
    levels: np.ndarray
    confidence: np.ndarray
    leak: np.ndarray = field(default_factory=lambda: np.zeros(3))
    palette_fit: Optional["palette.PaletteFit"] = None   # None when the 1-D fallback was used
    core_complement: bool = False                        # finder cores detected as C/M/Y references


def classify_matrix(corrected: np.ndarray, prof, L: layout.Layout):
    """Classify all data modules of a corrected matrix -> (levels, confidence, centroids)."""
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    vals = corrected[rows, cols]
    lv = np.zeros((len(rows), 3), dtype=np.int64)
    cf = np.ones(len(rows))
    cens = []
    if prof.gray:
        lab, conf, cen = classify_levels(vals.mean(axis=1), prof.levels[0])
        lv[:, :] = lab[:, None]
        cf = conf
        cens.append(cen)
    else:
        for c in range(3):
            lab, conf, cen = classify_levels(vals[:, c], prof.levels[c])
            lv[:, c] = lab
            cf = np.minimum(cf, conf)
            cens.append(cen)
    return lv, cf, cens


def decode_image(src, version_hint: Optional[int] = None, return_report: bool = False,
                 interference_cancellation: bool = True, palette_model: bool = True):
    """Decode a CQR symbol from an image (path, PIL image or array)."""
    img = load_image(src)
    finders = detect_finders(img)
    return decode_with_finders(img, finders, version_hint, return_report, interference_cancellation, palette_model)


def decode_all(src, return_report: bool = False, step: Optional[int] = None, **kw
               ) -> List[Tuple[Tuple[FinderCandidate, ...], object]]:
    """Decode every symbol found in the image.  Returns a list of
    (finder triple, result-or-exception) in detection order."""
    img = load_image(src)
    out = []
    for finders in detect_symbols(img, step=step):
        try:
            res = decode_with_finders(img, finders, return_report=return_report, **kw)
        except Exception as exc:  # noqa: BLE001 - report per symbol
            res = exc
        out.append((finders, res))
    return out


def decode_with_finders(img: np.ndarray, finders, version_hint: Optional[int] = None,
                        return_report: bool = False, interference_cancellation: bool = True,
                        palette_model: bool = True):
    geo = estimate_geometry(img, finders, version_hint)
    L = layout.get_layout(geo.version)
    samples = sample_grid(img, geo)
    cal = calibrate(samples, L)
    corrected = cal.apply(samples).reshape(samples.shape)
    is_dark = corrected.mean(axis=2) < 0.5

    if geo.version >= 7 and version_hint is None:
        vi = codec.read_version_info(is_dark)
        if vi is not None and vi != geo.version:
            return decode_with_finders(img, finders, version_hint=vi, return_report=return_report,
                                       interference_cancellation=interference_cancellation,
                                       palette_model=palette_model)

    ec, prof, fmt_err = codec.read_format(is_dark)
    # Sampling window: a 3x3 sub-grid over the central 50 % of the module is
    # best against pixel noise; when that fails (small, blurred modules where
    # neighbour bleed dominates) retry with a tighter 2x2 window over 30 %.
    first_error: Optional[Exception] = None
    for attempt, (sub, spread) in enumerate(((3, 0.5), (2, 0.3))):
        if attempt:
            samples = sample_grid(img, geo, sub=sub, spread=spread)
            cal = calibrate(samples, L)
            corrected = cal.apply(samples).reshape(samples.shape)
        try:
            return _classify_and_decode(samples, corrected, cal, geo, L, ec, prof, fmt_err, return_report,
                                        interference_cancellation, palette_model)
        except Exception as exc:  # noqa: BLE001
            first_error = first_error or exc
    raise first_error  # type: ignore[misc]


def _classify_and_decode(samples, corrected, cal, geo, L, ec, prof, fmt_err, return_report,
                         interference_cancellation, palette_model):

    # Primary classifier: 3-D palette model fitted to this symbol (handles the
    # non-additive colour mixing of real printers).  Fallback: per-channel 1-D
    # classification in the affine-calibrated space.
    pfit = None
    result = None
    cc = "cyan" in cal.refs_measured          # complementary finder cores detected by calibrate()
    if palette_model:
        try:
            norm = (samples - cal.black_field) / np.maximum(cal.white_field - cal.black_field, 0.05)
            pfit = palette.fit_palette(norm, corrected, prof, L, interference=interference_cancellation,
                                       core_complement=cc)
            result = codec.decode_levels(geo.version, ec, prof, pfit.levels, pfit.confidence)
            if not result.ok:
                raise ValueError(f"RS decoding failed for {result.failed_blocks} block(s)")
        except Exception:
            pfit = None
            result = None
    if result is None:
        levels, confs, centroids = classify_matrix(corrected, prof, L)
        alpha = np.zeros(3)
        if interference_cancellation:
            cleaned, alpha = cancel_interference(corrected, levels, prof, L, core_complement=cc)
            levels, confs, centroids = classify_matrix(cleaned, prof, L)
        result = codec.decode_levels(geo.version, ec, prof, levels, confs)
        if not result.ok:
            raise ValueError(f"RS decoding failed for {result.failed_blocks} block(s)")
    else:
        levels, confs, alpha = pfit.levels, pfit.confidence, pfit.leak
        centroids = [pfit.model.palette_rgb]
    if not return_report:
        return result
    return DecodeReport(result, geo, cal, centroids, float(confs.mean()), fmt_err, levels, confs, alpha, pfit, cc)
