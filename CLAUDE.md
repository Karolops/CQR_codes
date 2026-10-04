# CQR project context (read first)

Last session: 2026-10-04 (second session: first real-world print test, then complementary
C/M/Y finder cores + new palette initialisation; cmy_cores page printed and photographed once). Private repo:
https://github.com/Karolops/CQR_codes (branch `main`, pushed over HTTPS with the GitHub login
stored in Git Credential Manager, user `Karolops`; GitHub CLI `gh` is NOT installed - the
repo was created with the REST API). Web demo: https://karolops.github.io/CQR_codes/ (GitHub
Pages, deployed by .github/workflows/pages.yml on every push to main; web/ + cqr/ + 2 sample
photos run in Pyodide; the decoder has numpy fallbacks so opencv is not needed there).

## What the project is

CQR = coloured QR code. Exact ISO/IEC 18004 QR geometry (versions 1-40, same finder /
timing / alignment / format / version positions, same zig-zag placement), but each data
module carries several bits in its colour. The three finders are coloured red (top-left),
green (top-right), blue (bottom-left); together with the black/white function modules they
are the colour calibration references and resolve orientation/mirroring. Since 2026-10-04
the 3x3 core of each finder carries the complementary colour (cyan in red, magenta in
green, yellow in blue; `encode(core_complement=True)` default, `--plain-finders` to
disable) so that all 8 cube corners are measured; the decoder auto-detects both variants.
Colour resolution
is a "profile" stored in the 5-bit format payload (2 bits EC level L/M/Q/H in QR encoding +
3 bits profile index):

| idx | profile | bits/module | colours | use |
|---|---|---|---|---|
| 0 | rgb111 | 3 | 8 | default, print + phone (the only colour profile proven in print) |
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
cqr/palette.py   3-D palette model (printer colour mixing) fitted by EM per symbol - primary classifier
cqr/decoder.py   image -> payload (see pipeline below); decode_all() for photos with several symbols
cqr/simulate.py  camera/print simulator (tilt, rotation, blur, noise, cast, gamma, cross-talk, JPEG)
cqr/__main__.py  CLI: python -m cqr encode|decode|capacity  (encode -p profile -e L/M/Q/H -s px -q quiet -z)
tests/           pytest suite (43 tests, ~2 min), diag.py, evaluate.py, make_print_page.py, decode_photo.py
research/        01 prior art, 02 QR structure, 03 design decisions, 04 evaluation (+ real-world print test)
examples/        sample PNGs
print_test/      A4 test page (pdf/png), manifest.json (payloads, bboxes), photos/ (user's phone photos, untracked)
```

Decoder pipeline (cqr/decoder.py): finder candidates by 1:1:3:1:1 run scanning on the
min-channel image at 5 thresholds + purity maps -> `detect_finders` (best R/G/B triple) or
`detect_symbols` (all consistent triples: |RG| ~ |RB|, perpendicular, plausible module
count) -> version estimate from finder spacing with module size corrected by cos(rotation),
candidates scored by timing-pattern agreement -> grid = affine from finders, alignment
patterns chained nearest-first with 5x5 template search and homography refit -> module
sampling (3x3 sub-grid, 50 % spread; retried with 2x2 / 30 % if decoding fails) ->
polynomial white/black shading fields -> 3x3 affine colour calibration (used for format
reading and to seed the palette model) -> **palette model** (cqr/palette.py: tensor-product
polynomial from palette coordinates to camera colour, multilinear = Neugebauer corner
interpolation + quadratic terms per axis). Init: (1) multilinear model of the 8 corners
from the labelled function modules (rings R/G/B, cores C/M/Y, white, black; with plain
finders C/M/Y come from directional extremes of the data cloud), (2) invert it per data
module (batched Gauss-Newton, `palette.invert_model`) and estimate the level positions
(tone curves) + initial labels axis by axis with 1-D quantile k-means, (3) hard EM
anchored by the function modules, interference cancellation in camera space,
nearest-colour classification under a Mahalanobis metric from the residual covariance ->
confidence per module -> RS decoding with erasures on least confident symbols. Fallback if
that fails: the old per-channel 1-D k-means classifier in affine-corrected space. Results
with uncorrectable blocks raise ValueError (never returned).

## Status / results

- All 43 tests pass (`python -m pytest tests -q`, ~2 min).
- Simulated evaluation (`python tests/evaluate.py --seeds 2`, ~10 min; V6 symbols): see
  research/04 for the table (2 seeds, final code of 2026-10-04). With the palette model:
  rgb111 and gray4 decode 100 % in the phone-poor preset (was 0-80 %), rgb333/M decodes in
  phone-good, rgb444/L now 100 % on scanner; one cell got worse (rgb444/Q screen 1/2).
  Best per preset: screen rgb444/L 8.47 net bits/module, scanner rgb444/L 8.47,
  phone-good rgb332/L 5.60, phone-poor rgb111/L 2.08.
- **Real-world print test done (2026-10-04)**, Brother CMY inkjet print on plain paper + phone photos, details
  in research/04 "Real-world print test": rgb111 decodes with 0 module errors on close-ups
  of 1.02 and 0.51 mm modules and from a whole-page photo at 9 px/module (18/18 symbols
  detected on the page; mono decodes down to 6 px/module). With the final decoder the
  page photo also yields C1 (rgb221, 1.02 mm): 6/18. rgb222 and denser still fail in print:
  neighbouring printed colours are 1.3-1.5 sigma apart; even an oracle classifier with the
  true colour means has 7-12 % module errors. The close-up palette errors are now 20 %
  (rgb221, rgb222) vs oracle 12 % / 7 %.
- **Complementary finder cores** (research/03 section 9): on a simulated subtractive print
  built from the measured palette, rgb221/rgb222 go from 0-2 of 4 decoded (plain) to 4/4
  with 0-1 % module errors (C/M/Y cores). Real cmy_cores page photo (`print_test/cmy_cores/
  photos/`): 5/18 like the plain page (noisier photo); within the photo the cores cut the
  rgb221 C1 palette error from 21 % to 13 % (oracle 7.6 %). rgb221 at 1.02 mm sits on the
  EC M limit; rgb222+ need better paper / bigger modules (research/04, last section).
- Measured printed rgb111 palette (camera RGB, B1): K 25,25,27 R 190,61,79 G 24,128,46
  B 29,70,132 C 4,124,171 M 181,50,114 Y 206,172,12 W 193,192,190 - secondaries are far
  from additive (that is why the affine calibration misread 100 % of cyan / magenta).

## Next steps

1. Close-up photos of C1/C2 on the cmy_cores page in good light (decode with
   `--manifest print_test/cmy_cores/manifest.json --id C1`); then photo/glossy paper and the
   driver's plain-sRGB mode; rgb221 with 1.5-2 mm modules or EC Q.
2. Print-specific palette profile (8 corners + gamut-aware intermediates) and/or a stored
   printer calibration profile (chart with known labels) to get 6+ bits/module in print.
3. More photos: rgb111 at 0.68 / 0.51 mm from normal phone distance; rgb221 at 1.5-2 mm
   modules and under good light to find where 5 bits/module starts working.
4. Open ideas in TODO.md: structured append, legacy-QR-readable luminance layer, local grid
   refinement for lens distortion, soft/annealed EM for > 64 printed colours.

## How to run the photo tests

- One symbol per photo: `python tests/decode_photo.py print_test/photos/CQR_B1.jpg --id B1`
  (downscales to 2500 px; `--crop x0 y0 x1 y1` to cut one symbol out).
- Whole page: `python tests/decode_photo.py print_test/photos/CQR_whole_page.jpg --all`
  (full resolution, ~6 s, prints MATCH/FAILED per symbol against manifest.json).
- `python -m cqr decode photo.jpg --report` prints geometry / calibration diagnostics;
  exit code 2 and "decode failed: ..." on failure.

## Gotchas learned

- reedsolo keeps Galois-field tables in module globals, reset by every RSCodec constructor:
  never cache codec objects across different symbol sizes (ecc._codec builds fresh ones).
- cv2.remap maps must be < 32767 per side (decoder._sample_points reshapes to a square).
- Module size from axis-aligned run scanning is inflated by 1/cos(rotation); corrected in
  estimate_geometry. The finder-centre line is on module row 3.5, NOT the timing row.
- Byte-sized RS symbols straddle 9/12-bit modules -> that is why GF(2^9)/GF(2^12) are used.
- RS erasure attempts must stay <= 3E/4: with E-1 erasures reedsolo accepts random input
  in 40-60 % of cases (one check symbol left) -> garbage decodes with ok=True. Fixed in
  ecc.rs_decode; always verify against the known payload in experiments.
- Palette EM: initialising from the (measured or extreme-based) corner model and then
  inverting it per module before the 1-D level estimation was the decisive step (simulated
  print: 31-37 % errors -> 0 % with an oracle of 0 %). Hard EM from a poor init does not
  recover; a capacity check (fit from true labels) tells init problems from model problems.
- Palette EM: hard EM with per-channel weighting split overlapping red/magenta clusters along
  the brightness axis (capture noise is correlated across channels) - the full-covariance
  Mahalanobis metric fixed it. For 8/16-level channels the EM only converges when the tone
  curves are seeded from the 1-D quantile centroids. The 2-level case equals k-means with 8
  free means. A result with failed RS blocks must raise, otherwise garbage that happens to
  parse as a container is returned and the fallback/retry never runs.
- Phone JPEGs: 4:2:0 chroma subsampling makes < 8 px/module hopeless for colour profiles
  (rgb111 oracle error 3.7 % at 9 px, 12 % at 6.5 px per module). Small red finders are
  chroma-blurred and need the intermediate darkness thresholds (0.42 / 0.58).
- load_image accepts float arrays in [0,1] now (passing an already-loaded array through
  decode_all used to turn it black).
- This machine: Windows 10, Python 3.12 (Microsoft Store), numpy/pillow/opencv/reedsolo/
  segno/pytest installed. In the Bash tool, long heredocs containing triple quotes fail
  with "unexpected EOF" - write patch scripts to a file with the Write tool and run them.
  Scratchpad scripts (diag_photo.py, oracle.py, exp_capacity.py, exp_cmy_cores.py,
  exp_em2.py) are not in the repo; their results are recorded in research/03 and 04.
- Git: identity Karol_Niedbało <KarolNI@o2.pl>; commits end with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Line endings: repo files are
  LF, git warns about CRLF conversion - harmless. The session's changes were left
  uncommitted unless the user asked for a commit.
