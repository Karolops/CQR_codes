"""Decode a photo of a printed test symbol and compare with print_test/manifest.json.

Usage:
  python tests/decode_photo.py photo.jpg                 # whole photo contains one symbol
  python tests/decode_photo.py photo.jpg --crop x0 y0 x1 y1
  python tests/decode_photo.py photo.jpg --id B2         # compare with manifest entry B2
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from PIL import Image, ImageOps
from cqr.decoder import decode_image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--id", help="manifest id to compare against")
    ap.add_argument("--page", action="store_true", help="input is the full 300 dpi page: crop the symbol by manifest bbox")
    ap.add_argument("--max-side", type=int, default=2500, help="downscale long side to this many pixels")
    a = ap.parse_args()
    img = ImageOps.exif_transpose(Image.open(a.photo)).convert("RGB")
    man = None
    if a.id:
        with open(os.path.join(os.path.dirname(__file__), "..", "print_test", "manifest.json"), encoding="utf-8") as fh:
            man = json.load(fh)[a.id]
    if a.crop:
        img = img.crop(tuple(a.crop))
    elif a.page and man:
        x0, y0, x1, y1 = man["bbox_px"]
        pad = (x1 - x0) // 4
        img = img.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    if max(img.size) > a.max_side:
        s = a.max_side / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    rep = decode_image(np.asarray(img), return_report=True)
    g, res = rep.geometry, rep.result
    print(f"version {g.version}, timing score {g.timing_score:.3f}, alignment patterns {g.n_alignment}, "
          f"profile {res.profile.name}, EC {res.ec_level}")
    print(f"RS corrected {res.corrected_codewords}, failed blocks {res.failed_blocks}, mean confidence {rep.mean_confidence:.3f}, "
          f"leak {np.round(rep.leak, 3)}")
    for name, v in rep.calibration.refs_measured.items():
        print(f"  measured {name:5s}: {np.round(v * 255).astype(int)}")
    print("decoded:", res.data if isinstance(res.data, str) else res.data.hex())
    if man:
        print("MATCH" if res.ok and res.data == man["payload"] else "MISMATCH", "with manifest", a.id)


if __name__ == "__main__":
    main()
