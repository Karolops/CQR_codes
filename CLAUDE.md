# CQR project context (read first)

Last session: 2026-10-04. Private repo: https://github.com/Karolops/CQR_codes (branch `main`,
pushed over HTTPS with the GitHub login stored in Git Credential Manager, user `Karolops`;
GitHub CLI `gh` is NOT installed - the repo was created with the REST API).

## What the project is

CQR = coloured QR code. Exact ISO/IEC 18004 QR geometry (versions 1-40, same finder /
timing / alignment / format / version positions, same zig-zag placement), but each data
module carries several bits in its colour. The three finders are coloured red (top-left),
green (top-right), blue (bottom-left); together with the black/white function modules they
are the colour calibration references and resolve orientation/mirroring. Colour resolution
is a "profile" stored in the 5-bit format payload (2 bits EC level L/M/Q/H in QR encoding +
3 bits profile index):

| idx | profile | bits/module | colours | use |
|---|---|---|---|---|
| 0 | rgb111 | 3 | 8 | default, print + phone |
| 1 | rgb221 | 5 | 32 | good print / scanner |
| 2 | rgb222 | 6 | 64 | scanner / screen |
| 3 | rgb332 | 8 | 256 | screen, good phone capture |
| 4 | rgb333 | 9 | 512 | screen / scanner (RS over GF(2^9)) |
| 5 | rgb444 | 12 | 4096 | digital transfer (RS over GF(2^12)) |
| 6 | mono | 1 | 2 | QR-like baseline |
| 7 | gray4 | 2 | 4 | grey levels |

Channel levels are equally spaced in sRGB and Gray coded. RS symbol size = 9 or 12 bits
for rgb333/rgb444 (one module = one RS symbol), 8 bits (GF(256), prim 0x11D) otherwise.
Blocks: N symbols, B = ceil(N/(2^s-1)), E = 2*ceil(r*N/B) parity per block (r =
7/15/25/30 %), QR-style interleave, xorshift32 whitening (seed 0xC0DEC0DE) instead of masks.
Payload container: byte0 = type<<4 | 0xC (0 bytes, 1 utf-8 text, 2/3 zlib), 2-byte length.
Capacity V40/L: rgb111 9.5 KB, rgb222 19 KB, rgb333 28.6 KB, rgb444 38 KB (QR: 2.95 KB).

## Repository layout

```
cqr/layout.py    geometry (verified module-by-module against segno, tests/check_layout_vs_segno.py)
cqr/bch.py       BCH(15,5) format + BCH(18,6) version codes
cqr/profiles.py  profiles, Gray coding, format payload packing
cqr/ecc.py       RS block structure, interleave, whitening (reedsolo; symbol_bits 8/9/12)
cqr/codec.py     container, encode() -> Symbol(rgb matrix), decode_levels(), read_format()
cqr/render.py    Symbol -> image (quiet zone param; JPEG saved without chroma subsampling)
cqr/decoder.py   image -> payload (see pipeline below)
cqr/simulate.py  camera/print simulator (tilt, rotation, blur, noise, cast, gamma, cross-talk, JPEG)
cqr/__main__.py  CLI: python -m cqr encode|decode|capacity  (encode -p profile -e L/M/Q/H -s px -q quiet -z)
tests/           pytest suite (43 tests, ~2 min), diag.py, evaluate.py, make_print_page.py, decode_photo.py
research/        01 prior art, 02 QR structure, 03 design decisions (+ density experiments), 04 evaluation
examples/        sample PNGs; print_test/ A4 page (pdf/png) + manifest.json with payloads and bboxes
```

Decoder pipeline (cqr/decoder.py): finder detection by 1:1:3:1:1 run scanning on the
min-channel image + purity maps, colour keying of candidates -> version estimate from finder
spacing with module size corrected by cos(rotation), candidates scored by timing-pattern
agreement (widened window if poor) -> grid = affine from finders, then alignment patterns
chained nearest-first with 5x5 template search and homography refit -> module sampling
(3x3 sub-grid, 50 % spread) -> polynomial white/black shading fields -> 3x3 affine colour
calibration from R/G/B/white/black -> per-channel k-means seeded at data quantiles (whitened
stream => uniform level usage) -> neighbour interference cancellation -> confidence per
module -> RS decoding with erasures on least confident symbols.

## Status / results

- All 43 tests pass (`python -m pytest tests -q`). Evaluation (`python tests/evaluate.py`,
  simulated capture, V6 symbols): screen -> rgb444/L 8.47 net bits/module (12.5x mono);
  scanner -> rgb444/M 6.89; phone-good -> rgb332/L 5.60 (8.2x); phone-poor -> rgb111/Q 1.19.
  rgb111 decodes all phone-good cases and phone-poor at Q/H; 8 colours is the realistic phone
  ceiling (matches literature). JPEG chroma subsampling at < 5 px/module is the main killer
  (blue channel first).
- Density experiments done (research/03 section 7): module-aligned RS implemented (doubles
  tolerable error rate for 9/12-bit profiles); mixed-radix palettes judged marginal; quiet
  zone 0-2 modules works (encode -q 1); per-channel level tolerance G > R > B.
- NOT yet done: any real-world test. The user will provide photos of the printed
  print_test/cqr_print_test_A4.pdf page (symbols A1..F3; rows mono, rgb111, rgb221, rgb222,
  rgb332, rgb333; columns 1.02 / 0.68 / 0.51 mm modules; all V3, EC M).

## Next steps

1. Decode the user's photos: `python tests/decode_photo.py photo.jpg --id B2` (use `--crop`
   for one symbol out of a page photo). The decoder expects ONE symbol per image; if the
   photo shows the whole page, add multi-symbol detection (group finder candidates into
   consistent R/G/B triples by distance ~ (size-7)*module) or crop by hand.
2. Expect real-print issues: printer gamut (red vs magenta), yellow/blue weakness, uneven
   light. Possible fixes: 3-D nearest-centroid classifier, per-region calibration, a
   print-optimised palette profile (would need a profile slot; gray4 is the least useful).
3. Open ideas in TODO.md: structured append, legacy-QR-readable luminance layer,
   local grid refinement for lens distortion, unequal profile 4x8x4 colours (7 bits).

## Gotchas learned

- reedsolo keeps Galois-field tables in module globals, reset by every RSCodec constructor:
  never cache codec objects across different symbol sizes (ecc._codec builds fresh ones).
- cv2.remap maps must be < 32767 per side (decoder._sample_points reshapes to a square).
- Module size from axis-aligned run scanning is inflated by 1/cos(rotation); corrected in
  estimate_geometry. The finder-centre line is on module row 3.5, NOT the timing row.
- Byte-sized RS symbols straddle 9/12-bit modules -> that is why GF(2^9)/GF(2^12) are used.
- This machine: Windows 10, Python 3.12 (Microsoft Store), numpy/pillow/opencv/reedsolo/
  segno/pytest installed. In the Bash tool, long heredocs containing triple quotes fail
  with "unexpected EOF" - write patch scripts to a file with the Write tool and run them.
  Scratchpad scripts from the last session are not in the repo (exp_rs_field.py,
  exp_density.py, create_repo.py); their results are recorded in research/03.
- Git: identity Karol_Niedbało <KarolNI@o2.pl>; commits end with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Line endings: repo files are
  LF, git warns about CRLF conversion - harmless.
