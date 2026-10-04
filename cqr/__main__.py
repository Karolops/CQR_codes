"""Command line interface: python -m cqr encode|decode|capacity ..."""
from __future__ import annotations

import argparse
import sys

import numpy as np

from . import codec, layout, render
from .profiles import EC_LEVELS, PROFILES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cqr", description="CQR - coloured QR codes")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help="encode text or a file into a CQR image")
    e.add_argument("data", nargs="?", help="text to encode (omit when using --file)")
    e.add_argument("-f", "--file", help="binary file to encode")
    e.add_argument("-o", "--out", default="cqr.png", help="output image (PNG recommended)")
    e.add_argument("-p", "--profile", default="rgb222", help="colour profile: " + ", ".join(p.name for p in PROFILES.values()))
    e.add_argument("-e", "--ec", default="M", choices=list(EC_LEVELS), help="error correction level")
    e.add_argument("-v", "--version", type=int, default=None, help="force symbol version 1..40 (default: smallest that fits)")
    e.add_argument("-s", "--scale", type=int, default=10, help="pixels per module")
    e.add_argument("-z", "--compress", action="store_true", help="zlib-compress the payload if that helps")
    e.add_argument("-q", "--quiet", type=int, default=4, help="quiet zone in modules (QR standard 4; 1 works with this decoder)")
    e.add_argument("--plain-finders", action="store_true",
                   help="plain R/G/B finders (default: cyan / magenta / yellow finder cores as extra colour references)")

    d = sub.add_parser("decode", help="decode a CQR image")
    d.add_argument("image")
    d.add_argument("--report", action="store_true", help="print decoding diagnostics")
    d.add_argument("--raw", action="store_true", help="write binary payload to stdout")

    c = sub.add_parser("capacity", help="print payload capacity table")
    c.add_argument("-p", "--profile", default=None, help="limit to one profile")
    c.add_argument("-e", "--ec", default=None, choices=list(EC_LEVELS))

    a = ap.parse_args(argv)
    if a.cmd == "encode":
        if a.file:
            with open(a.file, "rb") as fh:
                payload = fh.read()
        elif a.data is not None:
            payload = a.data
        else:
            ap.error("provide text or --file")
        sym = codec.encode(payload, ec_level=a.ec, profile=a.profile, version=a.version, compress=a.compress,
                           core_complement=not a.plain_finders)
        render.save(sym, a.out, module_px=a.scale, quiet=a.quiet)
        print(f"wrote {a.out}: version {sym.version} ({sym.size}x{sym.size} modules), profile {sym.profile.name} "
              f"({sym.profile.bits_per_module} bits/module), EC {sym.ec_level}, payload {sym.payload_bytes} B "
              f"of {sym.capacity_bytes} B capacity")
        return 0
    if a.cmd == "decode":
        from .decoder import decode_image
        try:
            rep = decode_image(a.image, return_report=True)
        except ValueError as exc:
            print(f"decode failed: {exc}", file=sys.stderr)
            return 2
        res = rep.result
        if a.report:
            g = rep.geometry
            print(f"version {g.version} ({g.size}x{g.size}), timing score {g.timing_score:.3f}, "
                  f"alignment patterns used: {g.n_alignment}", file=sys.stderr)
            print(f"profile {res.profile.name}, EC {res.ec_level}, format bit errors {rep.format_errors}, "
                  f"finder cores {'C/M/Y' if rep.core_complement else 'plain'}", file=sys.stderr)
            print(f"RS corrected codewords: {res.corrected_codewords}, failed blocks: {res.failed_blocks}, "
                  f"mean module confidence {rep.mean_confidence:.3f}", file=sys.stderr)
            for name, v in rep.calibration.refs_measured.items():
                print(f"  measured {name:5s}: {np.round(v * 255).astype(int)}", file=sys.stderr)
        if a.raw and isinstance(res.data, (bytes, bytearray)):
            sys.stdout.buffer.write(res.data)
        else:
            print(res.data if isinstance(res.data, str) else res.data.hex())
        return 0 if res.ok else 2
    if a.cmd == "capacity":
        profs = [p for p in PROFILES.values() if a.profile is None or p.name == a.profile]
        ecs = [a.ec] if a.ec else list(EC_LEVELS)
        print("payload capacity in bytes (version: " + ", ".join(f"{p.name}/{ec}" for p in profs for ec in ecs) + ")")
        for v in range(layout.MIN_VERSION, layout.MAX_VERSION + 1):
            cells = []
            for p in profs:
                for ec in ecs:
                    try:
                        cells.append(str(codec.capacity(v, ec, p)))
                    except ValueError:
                        cells.append("-")
            print(f"V{v:2d} ({layout.size_for_version(v):3d}): " + " ".join(f"{x:>6s}" for x in cells))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
