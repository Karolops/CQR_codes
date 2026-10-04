"""3-D palette model for colour classification of printed / photographed symbols.

Printing is subtractive: the camera colour of a secondary (cyan, magenta,
yellow) is *not* the sum of the printed primaries, and halftone dot gain bends
every tone curve.  A per-channel affine calibration from the R/G/B/white/black
references therefore misplaces a large part of the palette (on a laser print,
cyan lands half-way between blue and cyan, magenta between red and magenta).

This module models the forward map directly::

    expected camera colour (shading-normalised) = P(u),   u in [0,1]^k

where u are the ideal palette coordinates (k = 3 channels, or k = 1 for the
grey profiles) and P is a tensor-product polynomial.  The multilinear part is
the Neugebauer / Demichel interpolation between the 8 corner colours
(K, R, G, B, C, M, Y, W); optional quadratic terms per axis absorb tone-curve
and dot-gain effects.  The model is fitted by hard expectation-maximisation on
the data modules themselves - the whitened codeword stream uses every palette
colour equally often - anchored by the labelled function-pattern modules.
Classification is nearest palette colour in the camera space, with a
per-channel noise weighting estimated from the residuals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import List, Optional, Tuple

import numpy as np

from . import codec, layout


class PaletteModel:
    """Tensor-product polynomial from palette coordinates u (n, k) to camera RGB (n, 3)."""

    def __init__(self, prof, max_degree: int = 2):
        self.prof = prof
        self.n_levels = [prof.levels[0]] if prof.gray else list(prof.levels)
        self.k = len(self.n_levels)
        self.degrees = [min(n - 1, max_degree) for n in self.n_levels]
        self.coef: Optional[np.ndarray] = None
        # the full palette in u-space and in level units (n_colors, 3)
        grids = [np.arange(n) for n in self.n_levels]
        combos = np.array(list(product(*grids)), dtype=np.int64)          # (n_colors, k)
        self.palette_u = combos / np.maximum(1, np.array(self.n_levels) - 1)[None, :]
        self.palette_levels = np.repeat(combos, 3, axis=1) if prof.gray else combos
        self.palette_rgb: Optional[np.ndarray] = None

    # ---- design matrix --------------------------------------------------
    @property
    def n_terms(self) -> int:
        return int(np.prod([d + 1 for d in self.degrees]))

    def design(self, U: np.ndarray, degrees: Optional[List[int]] = None) -> np.ndarray:
        U = np.asarray(U, dtype=np.float64).reshape(-1, self.k)
        degrees = self.degrees if degrees is None else degrees
        X = np.ones((len(U), 1))
        for c in range(self.k):
            x = U[:, c] - 0.5
            basis = np.stack([x ** p for p in range(degrees[c] + 1)], axis=1)
            X = (X[:, :, None] * basis[:, None, :]).reshape(len(U), -1)
        return X

    def fit(self, U: np.ndarray, Y: np.ndarray, w: Optional[np.ndarray] = None,
            degrees: Optional[List[int]] = None) -> None:
        degrees = self.degrees if degrees is None else degrees
        X = self.design(U, degrees)
        Y = np.asarray(Y, dtype=np.float64).reshape(-1, 3)
        if w is not None:
            sw = np.sqrt(np.asarray(w, dtype=np.float64))[:, None]
            X, Y = X * sw, Y * sw
        coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
        if degrees != self.degrees:
            # embed the lower-degree solution into the full coefficient vector
            full = np.zeros((self.n_terms, 3))
            idx_full = np.array(list(product(*[range(d + 1) for d in self.degrees])))
            idx_low = np.array(list(product(*[range(d + 1) for d in degrees])))
            lookup = {tuple(r): i for i, r in enumerate(idx_full)}
            for i, r in enumerate(idx_low):
                full[lookup[tuple(r)]] = coef[i]
            coef = full
        self.coef = coef
        self.palette_rgb = self.design(self.palette_u) @ self.coef

    def predict(self, U: np.ndarray) -> np.ndarray:
        return self.design(U) @ self.coef

    def rgb_to_u(self, rgb01: np.ndarray) -> np.ndarray:
        """Ideal sRGB colour in [0,1] -> palette coordinates."""
        rgb01 = np.asarray(rgb01, dtype=np.float64).reshape(-1, 3)
        return rgb01.mean(axis=1, keepdims=True) if self.prof.gray else rgb01

    # ---- classification -------------------------------------------------
    def classify(self, Y: np.ndarray, W: Optional[np.ndarray] = None, chunk: int = 4096
                 ) -> Tuple[np.ndarray, np.ndarray]:
        """Nearest palette colour.  W is an optional (3,3) whitening matrix (or a
        per-channel weight vector) applied to colours before the Euclidean distance,
        i.e. a Mahalanobis metric for correlated capture noise.
        Returns (palette index, confidence in [0,1])."""
        if W is None:
            W = np.eye(3)
        W = np.asarray(W, dtype=np.float64)
        if W.ndim == 1:
            W = np.diag(W)
        P = self.palette_rgb @ W.T
        Yw = np.asarray(Y, dtype=np.float64).reshape(-1, 3) @ W.T
        pp = (P * P).sum(1)
        idx = np.empty(len(Yw), dtype=np.int64)
        conf = np.empty(len(Yw))
        for i in range(0, len(Yw), chunk):
            y = Yw[i:i + chunk]
            d = np.maximum((y * y).sum(1)[:, None] + pp[None, :] - 2.0 * (y @ P.T), 0.0)
            if d.shape[1] == 1:
                idx[i:i + chunk] = 0
                conf[i:i + chunk] = 1.0
                continue
            part = np.argpartition(d, 1, axis=1)[:, :2]
            dd = np.take_along_axis(d, part, axis=1)
            order = dd.argmin(axis=1)
            best = part[np.arange(len(y)), order]
            d1 = np.sqrt(dd[np.arange(len(y)), order])
            d2 = np.sqrt(dd[np.arange(len(y)), 1 - order])
            idx[i:i + chunk] = best
            conf[i:i + chunk] = np.clip((d2 - d1) / np.maximum(d2 + d1, 1e-9), 0.0, 1.0)
        return idx, conf


def whitening_matrix(resid: np.ndarray, ridge: float = 1e-4) -> Tuple[np.ndarray, np.ndarray]:
    """(W, std) with W = Sigma^-1/2 of the residual covariance (scaled to unit mean
    variance so that confidences stay comparable), std = per-channel residual std."""
    resid = np.asarray(resid, dtype=np.float64).reshape(-1, 3)
    std = np.maximum(resid.std(axis=0), 1e-3)
    if len(resid) < 12:
        return np.eye(3), std
    cov = np.cov(resid.T) + ridge * np.eye(3)
    cov *= 3.0 / np.trace(cov)                      # unit mean variance
    Lc = np.linalg.cholesky(cov)
    return np.linalg.inv(Lc), std


def _axis_centroids(values: np.ndarray, n_levels: int, iters: int = 8) -> np.ndarray:
    """1-D level centroids of one channel: quantile seeding (the whitened stream uses
    every level equally often) followed by k-means with a monotonicity guard."""
    v = np.asarray(values, dtype=np.float64)
    cen = np.linspace(0.0, 1.0, n_levels)
    if v.size < 8 * n_levels:
        return cen
    q = np.quantile(v, (np.arange(n_levels) + 0.5) / n_levels)
    if not np.all(np.diff(q) > 0.25 / max(1, n_levels - 1)):
        return cen
    cen = q
    for _ in range(iters):
        lab = np.abs(v[:, None] - cen[None, :]).argmin(axis=1)
        new = cen.copy()
        for i in range(n_levels):
            sel = v[lab == i]
            if sel.size >= max(3, v.size // (20 * n_levels)):
                new[i] = sel.mean()
        new = np.sort(new)
        if not np.all(np.diff(new) > 0.25 / max(1, n_levels - 1)):
            break
        cen = new
    return cen


def _tone_mapped_palette(model: PaletteModel, corrected_d: np.ndarray) -> np.ndarray:
    """Palette coordinates with each axis tone-mapped by the 1-D centroids measured in
    the affine-corrected space (so that gamma / dot gain is absorbed before the EM starts;
    the multilinear model then only has to learn the colour mixing)."""
    tables = []
    for c, n in enumerate(model.n_levels):
        if n <= 2:
            tables.append(np.linspace(0.0, 1.0, n))
            continue
        vals = corrected_d.mean(axis=1) if model.prof.gray else corrected_d[:, c]
        cen = _axis_centroids(vals, n)
        u = (cen - cen[0]) / max(cen[-1] - cen[0], 1e-6)
        tables.append(np.clip(np.maximum.accumulate(u), 0.0, 1.0))
    combos = np.rint(model.palette_u * (np.array(model.n_levels) - 1)[None, :]).astype(int)
    return np.stack([tables[c][combos[:, c]] for c in range(model.k)], axis=1)


@dataclass
class PaletteFit:
    model: PaletteModel
    levels: np.ndarray          # (n_data, 3) classified channel levels in placement order
    confidence: np.ndarray      # (n_data,)
    leak: np.ndarray            # per-channel neighbour interference coefficient
    channel_std: np.ndarray     # residual std per channel (shading-normalised units)
    whitening: np.ndarray       # (3,3) Mahalanobis whitening used for classification
    iterations: int
    changed_last: int           # modules whose label changed in the last iteration
    mean_residual: float = 0.0
    history: List[int] = field(default_factory=list)


def _function_module_training(L: layout.Layout, prof, model: PaletteModel, core_complement: bool = False):
    """Masks and ideal palette coordinates of the labelled function-pattern modules."""
    kind = L.kind
    known = ~np.isin(kind, (layout.K_DATA, layout.K_FORMAT, layout.K_VERSION))
    ideal = codec.function_pattern_colors(L.version, "L", prof, core_complement).astype(np.float64) / 255.0
    return known, model.rgb_to_u(ideal[known]), ideal


def _corner_training(corrected_d: np.ndarray, norm_d: np.ndarray, model: PaletteModel):
    """Initial estimates of the 8 corner colours from directional extremes of the data
    cloud in the affine-corrected space (where the secondaries, if non-additive, still
    lie farthest along their own (+-1,+-1,+-1) direction)."""
    n = len(norm_d)
    m = max(3, int(round(n / model.prof.n_colors)))
    U, Y = [], []
    for s in product((0.0, 1.0), repeat=3):
        s = np.array(s)
        proj = corrected_d @ (2 * s - 1)
        top = np.argsort(proj)[-m:]
        U.append(np.repeat(s[None, :], m, axis=0))
        Y.append(norm_d[top])
    return np.concatenate(U), np.concatenate(Y)


def invert_model(model: PaletteModel, Y: np.ndarray, iters: int = 8, damping: float = 1e-3) -> np.ndarray:
    """Continuous palette coordinates u (n, k) such that model.predict(u) ~ Y, by batched
    Gauss-Newton from the centre of the cube.  Used to undo the (measured) colour mixing
    before the per-axis level estimation: in u-space the axes are separable again."""
    Y = np.asarray(Y, dtype=np.float64).reshape(-1, 3)
    n, k = len(Y), model.k
    u = np.full((n, k), 0.5)
    eps = 1e-3
    for _ in range(iters):
        r = Y - model.predict(u)                                         # (n, 3)
        J = np.empty((n, 3, k))
        for c in range(k):
            du = u.copy()
            du[:, c] += eps
            J[:, :, c] = (model.predict(du) - (Y - r)) / eps
        JtJ = np.einsum("nic,nid->ncd", J, J) + damping * np.eye(k)[None]
        Jtr = np.einsum("nic,ni->nc", J, r)
        step = np.linalg.solve(JtJ, Jtr[..., None])[..., 0]
        u = np.clip(u + np.clip(step, -0.5, 0.5), -0.25, 1.25)
    return u


def fit_palette(norm: np.ndarray, corrected: np.ndarray, prof, L: layout.Layout,
                max_iter: int = 12, interference: bool = True, anchor_weight: float = 0.5,
                max_degree: int = 2, core_complement: bool = False) -> PaletteFit:
    """Fit the palette model to one symbol and classify its data modules.

    norm:      (size, size, 3) shading-normalised samples (white field -> 1, black field -> 0)
    corrected: (size, size, 3) affine-calibrated samples (only used to seed the corners)
    core_complement: the finder cores are cyan / magenta / yellow (measured secondaries)

    Stages: (1) multilinear (Neugebauer) model of the 8 cube corners - from the labelled
    function modules alone when the finder cores provide C/M/Y, otherwise completed with
    the directional extremes of the data cloud; (2) invert it to get continuous palette
    coordinates of every data module and estimate the per-axis level positions (tone
    curves) and initial labels with 1-D quantile k-means, axis by axis; (3) hard EM with
    the full tensor-product model, neighbour interference cancellation and a Mahalanobis
    metric from the residual covariance.
    """
    size = L.size
    rows, cols = L.data_order[:, 0], L.data_order[:, 1]
    n_data = len(rows)
    model = PaletteModel(prof, max_degree=max_degree)
    # keep the number of free parameters small relative to the number of modules
    while model.n_terms * 12 > n_data and max(model.degrees) > 1:
        max_degree -= 1
        model = PaletteModel(prof, max_degree=max_degree)
    known, U_fn, ideal = _function_module_training(L, prof, model, core_complement)
    norm_d = norm[rows, cols]
    combos = np.rint(model.palette_u * (np.array(model.n_levels) - 1)[None, :]).astype(int)

    # ---- (1) multilinear corner model
    U0 = [U_fn]
    Y0 = [norm[known]]
    W0 = [np.full(int(known.sum()), 1.0 if core_complement else anchor_weight)]
    if not prof.gray and not core_complement:
        Uc, Yc = _corner_training(corrected[rows, cols], norm_d, model)
        U0.append(Uc); Y0.append(Yc); W0.append(np.ones(len(Uc)))
    model.fit(np.concatenate(U0), np.concatenate(Y0), np.concatenate(W0), degrees=[1] * model.k)

    # ---- (2) per-axis tone tables and initial labels in the un-mixed coordinates
    u_hat = invert_model(model, norm_d)
    tables = []
    labels = np.zeros((n_data, model.k), dtype=np.int64)
    for c, n in enumerate(model.n_levels):
        cen = _axis_centroids(u_hat[:, c], n)
        labels[:, c] = np.abs(u_hat[:, c][:, None] - cen[None, :]).argmin(axis=1)
        t = (cen - cen[0]) / max(cen[-1] - cen[0], 1e-6)
        tables.append(np.clip(np.maximum.accumulate(t), 0.0, 1.0))
    model.palette_u = np.stack([tables[c][combos[:, c]] for c in range(model.k)], axis=1)
    idx = np.zeros(n_data, dtype=np.int64)
    for c, n in enumerate(model.n_levels):
        idx = idx * n + labels[:, c]

    # ---- (3) EM
    cleaned = norm.copy()
    alpha = np.zeros(3)
    W = np.eye(3)
    std = np.full(3, 0.05)
    history = []
    changed = n_data
    it = 0
    for it in range(1, max_iter + 1):
        U_d = model.palette_u[idx]
        # M-step: refit the full model on the (cleaned) data modules + anchors
        U = np.concatenate([U_d, U_fn])
        Yfit = np.concatenate([cleaned[rows, cols], cleaned[known]])
        Wfit = np.concatenate([np.ones(n_data), np.full(int(known.sum()), anchor_weight)])
        model.fit(U, Yfit, Wfit)
        # neighbour interference cancellation in camera space using the model prediction
        if interference:
            pred = np.empty_like(norm)
            pred[known] = model.predict(U_fn)
            pred[rows, cols] = model.predict(U_d)
            unknown = ~known
            unknown[rows, cols] = False
            pred[unknown] = norm[unknown]
            pad = np.pad(pred, ((1, 1), (1, 1), (0, 0)), mode="edge")
            nsum = pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:] - 4 * pred
            x = nsum[rows, cols]
            y = norm[rows, cols] - pred[rows, cols]
            for c in range(3):
                xx = float((x[:, c] * x[:, c]).sum())
                alpha[c] = float((x[:, c] * y[:, c]).sum() / xx) if xx > 1e-9 else 0.0
            alpha = np.clip(alpha, 0.0, 0.3)
            cleaned = norm - nsum * alpha[None, None, :]
        resid = cleaned[rows, cols] - model.predict(U_d)
        W, std = whitening_matrix(resid)
        # E-step
        new_idx, conf = model.classify(cleaned[rows, cols], W)
        changed = int((new_idx != idx).sum())
        history.append(changed)
        idx = new_idx
        if changed <= max(0, n_data // 1000):
            break
    levels = model.palette_levels[idx]
    resid = cleaned[rows, cols] - model.palette_rgb[idx]
    return PaletteFit(model, levels, conf, alpha, std, W, it, changed,
                      float(np.sqrt((resid ** 2).sum(1)).mean()), history)
