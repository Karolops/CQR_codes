"""Decode a photo of a printed test symbol and compare with print_test/manifest.json.

Usage:
  python tests/decode_photo.py photo.jpg                 # whole photo contains one symbol
  python tests/decode_photo.py photo.jpg --crop x0 y0 x1 y1
  python tests/decode_photo.py photo.jpg --id B2         # compare with manifest entry B2
  python tests/decode_photo.py page.jpg --all            # every symbol in a photo of the whole page
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from PIL import Image, ImageOps
from cqr.decoder import decode_image, decode_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--id", help="manifest id to compare against")
    ap.add_argument("--page", action="store_true", help="input is the full 300 dpi page: crop the symbol by manifest bbox")
    ap.add_argument("--max-side", type=int, default=None,
                    help="downscale long side to this many pixels (default 2500 for one symbol, no downscaling with --all)")
    ap.add_argument("--all", action="store_true", help="detect and decode every symbol in the photo")
    ap.add_argument("--manifest", default=os.path.join(os.path.dirname(__file__), "..", "print_test", "manifest.json"),
                    help="manifest to compare against (print_test/cmy_cores/manifest.json for the C/M/Y-core page)")
    a = ap.parse_args()
    img = ImageOps.exif_transpose(Image.open(a.photo)).convert("RGB")
    man = None
    if a.id:
        with open(a.manifest, encoding="utf-8") as fh:
            man = json.load(fh)[a.id]
    if a.crop:
        img = img.crop(tuple(a.crop))
    elif a.page and man:
        x0, y0, x1, y1 = man["bbox_px"]
        pad = (x1 - x0) // 4
        img = img.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    max_side = a.max_side or (10 ** 9 if a.all else 2500)
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    if a.all:
        return decode_page(np.asarray(img), a.manifest)
    try:
        rep = decode_image(np.asarray(img), return_report=True)
    except ValueError as exc:
        print(f"decode failed: {exc}")
        return
    g, res = rep.geometry, rep.result
    print(f"version {g.version}, timing score {g.timing_score:.3f}, alignment patterns {g.n_alignment}, "
          f"profile {res.profile.name}, EC {res.ec_level}, finder cores {'C/M/Y' if rep.core_complement else 'plain'}")
    print(f"RS corrected {res.corrected_codewords}, failed blocks {res.failed_blocks}, mean confidence {rep.mean_confidence:.3f}, "
          f"leak {np.round(rep.leak, 3)}")
    for name, v in rep.calibration.refs_measured.items():
        print(f"  measured {name:5s}: {np.round(v * 255).astype(int)}")
    print("decoded:", res.data if isinstance(res.data, str) else res.data.hex())
    if man:
        print("MATCH" if res.ok and res.data == man["payload"] else "MISMATCH", "with manifest", a.id)


def decode_page(arr, manifest_path):
    with open(manifest_path, encoding="utf-8") as fh:
        man = json.load(fh)
    by_payload = {v["payload"]: k for k, v in man.items()}
    results = decode_all(arr, return_report=True)
    print(f"{len(results)} symbol(s) detected")
    ok = 0
    for finders, rep in sorted(results, key=lambda t: (round(t[0][0].y / 200), t[0][0].x)):
        r = finders[0]
        where = f"red finder at ({r.x:5.0f},{r.y:5.0f}) module {r.module:4.1f} px"
        if isinstance(rep, Exception):
            print(f"  {where}: FAILED - {rep}")
            continue
        d = rep.result
        if not d.ok:
            print(f"  {where}: FAILED - V{rep.geometry.version} {d.profile.name}/{d.ec_level}: {d.failed_blocks} RS block(s) uncorrectable")
            continue
        sid = by_payload.get(d.data)
        ok += sid is not None
        tag = f"MATCH {sid}" if sid else f"decoded but not in manifest: {d.data!r}"[:80]
        print(f"  {where}: V{rep.geometry.version} {d.profile.name}/{d.ec_level} {'cmy' if rep.core_complement else 'rgb'} "
              f"RS corrected {d.corrected_codewords:3d} conf {rep.mean_confidence:.2f} -> {tag}")
    print(f"{ok}/{len(results)} decoded and matched the manifest")


if __name__ == "__main__":
    main()
