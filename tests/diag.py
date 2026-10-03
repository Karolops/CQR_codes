"""Diagnostics helper: encode -> simulate -> decode with ground-truth comparison."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from cqr import codec, render, layout
from cqr.decoder import (load_image, detect_finders, estimate_geometry, sample_grid, calibrate,
                         classify_matrix, cancel_interference)
from cqr.simulate import CameraParams, simulate


def diagnose(sym, p: CameraParams, verbose=True):
    img8 = render.to_array(sym, module_px=8)
    cam = simulate(img8, p)
    img = load_image(cam)
    out = {"ok": False, "stage": "finders"}
    try:
        finders = detect_finders(img)
    except Exception as e:
        if verbose: print("  finder detection failed:", e)
        return out
    if verbose:
        for f, n in zip(finders, "RGB"):
            print(f"  finder {n}: x={f.x:.1f} y={f.y:.1f} m={f.module:.2f} votes={f.votes} score={f.score:.2f} purity={np.round(f.purity,2)}")
    out["stage"] = "geometry"
    try:
        geo = estimate_geometry(img, finders)
    except Exception as e:
        if verbose: print("  geometry failed:", e)
        return out
    if verbose:
        print(f"  version est {geo.version} (true {sym.version}), timing {geo.timing_score:.3f}, "
              f"align found {geo.n_alignment}/{len(sym.layout.align_centres)}, cands {{{', '.join(f'{k}: {v:.2f}' for k, v in geo.candidates.items())}}}")
    if geo.version != sym.version:
        return out
    L = layout.get_layout(geo.version)
    samples = sample_grid(img, geo)
    cal = calibrate(samples, L)
    corr = cal.apply(samples).reshape(samples.shape)
    if verbose:
        print("  raw refs:", {k: np.round(v * 255).astype(int).tolist() for k, v in cal.refs_measured.items()})
    prof = sym.profile
    levels, confs, cens = classify_matrix(corr, prof, L)
    err = (levels != sym.levels).any(axis=1)
    out["module_error_rate_raw"] = float(err.mean())
    cleaned, alpha = cancel_interference(corr, levels, prof, L)
    levels, confs, cens = classify_matrix(cleaned, prof, L)
    err2 = (levels != sym.levels).any(axis=1)
    out["module_error_rate"] = float(err2.mean())
    if verbose:
        for c, cen in enumerate(cens):
            print(f"  ch{c} centroids {np.round(cen, 3)}")
        print(f"  interference cancellation: leak {np.round(alpha, 3)}, module error rate {err.mean():.4f} -> {err2.mean():.4f}")
        print(f"  mean conf {confs.mean():.3f}; conf of wrong modules {confs[err2].mean() if err2.any() else float('nan'):.3f}")
        per_ch = [(levels[:, c] != sym.levels[:, c]).mean() for c in range(3)]
        print(f"  per-channel error rates {np.round(per_ch, 4)}")
    is_dark = corr.mean(axis=2) < 0.5
    ec, pr, fe = codec.read_format(is_dark)
    out["stage"] = "decode"
    try:
        res = codec.decode_levels(geo.version, ec, pr, levels, confs)
        out["ok"] = res.ok and res.data == getattr(sym, "_payload", None)
        if verbose:
            print(f"  format: ec {ec} profile {pr.name} ({fe} bit errors); RS corrected {res.corrected_codewords}, "
                  f"failed blocks {res.failed_blocks}; blocks {sym.blocks.n_blocks} x (data {sym.blocks.data_lengths[0]} + ec {sym.blocks.ec_per_block})")
    except Exception as e:
        if verbose: print("  decode failed:", e)
    if verbose:
        print("  RESULT:", "OK" if out["ok"] else "WRONG")
    return out


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    payload = bytes(rng.integers(0, 256, 120, dtype=np.uint8))
    sym = codec.encode(payload, ec_level="H", profile="rgb111")
    sym._payload = payload
    print("harsh rgb111 H")
    diagnose(sym, CameraParams(module_px=4.5, rotation_deg=-20, tilt=0.25, blur_sigma=1.0, noise_sigma=0.05,
                               color_cast=(1.1, 0.95, 0.75), gamma=1.3, black_level=0.15, white_level=0.85,
                               crosstalk=0.12, jpeg_quality=60, seed=7))
