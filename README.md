# CQR - Coloured QR codes

CQR is a 2-D barcode that keeps the **exact geometry of an ISO/IEC 18004 QR code**
(finder, timing, alignment, format and version patterns, zig-zag data placement)
but stores several bits per module in the module's **colour**.  The three finder
patterns are coloured **red (top-left), green (top-right) and blue (bottom-left)**
with **cyan, magenta and yellow cores**: together with the black and white function
modules they put all eight corners of the colour cube into every symbol as measured
calibration references and, as a bonus, resolve the symbol's orientation (and
mirroring) without any geometric reasoning.

**Live demo**, the real encoder and decoder running in the browser (Pyodide, nothing is
uploaded): https://karolops.github.io/CQR_codes/

Colour resolution is a parameter: a *colour profile* fixes how many levels each of
the R, G and B channels carries.

| profile  | colours | bits/module | intended use                                     |
|----------|---------|-------------|--------------------------------------------------|
| `mono`   | 2       | 1           | black/white baseline (QR-like density)           |
| `gray4`  | 4       | 2           | grey levels, for monochrome printers             |
| `rgb111` | 8       | 3           | **default** - printed media + phone cameras (proven in print) |
| `rgb221` | 32      | 5           | good print / scanner (blue gets fewer levels); on the edge in print |
| `rgb222` | 64      | 6           | screen-to-camera, flatbed scanners               |
| `rgb332` | 256     | 8           | screen / file transfer                           |
| `rgb333` | 512     | 9           | screen / file transfer                           |
| `rgb444` | 4096    | 12          | lossless digital transfer only                   |

A version-40 `rgb333` symbol (177x177 modules) holds **28.6 KB** at EC level L,
versus 2.95 KB for a normal QR code of the same size (9.7x); `rgb111` holds
9.5 KB (3.2x), `rgb222` 19 KB (6.5x) and `rgb444` 38 KB (13x).  Run
`python -m cqr capacity` for the full table.  The quiet zone can be reduced from the QR
standard 4 modules to 1 (`encode -q 1`) without loss in simulation, which shrinks the
printed area of small symbols by about a third.

## Install / run

Python 3.10+, `numpy`, `pillow`, `reedsolo`; `opencv-python` is optional (faster
sampling, otherwise numpy fallbacks are used, which is how the browser demo runs).  Tests
also use `pytest` and `segno` (only to cross-validate the layout).

```
pip install numpy pillow reedsolo opencv-python
python -m cqr encode "Hello, colour!" -o hello.png            # rgb111, EC M, smallest version
python -m cqr encode -f archive.zip -p rgb222 -e L -o big.png -z
python -m cqr decode hello.png --report
python -m cqr capacity -p rgb111
```

Python API:

```python
from cqr import codec, render
from cqr.decoder import decode_image

sym = codec.encode(b"payload bytes", ec_level="M", profile="rgb111")   # -> Symbol
render.save(sym, "out.png", module_px=10)
res = decode_image("out.png")           # or a PIL image / numpy RGB array
print(res.ok, res.data, res.profile.name, res.corrected_codewords)
```

## Layout of the repository

```
cqr/layout.py     QR geometry: function patterns, format/version bit positions, placement order
cqr/bch.py        BCH(15,5) format and BCH(18,6) version codes
cqr/profiles.py   colour profiles, Gray-coded levels, format payload packing
cqr/ecc.py        Reed-Solomon block structure, interleaving, whitening
cqr/codec.py      payload container, encode -> module colours, decode from module levels
cqr/render.py     Symbol -> PNG/JPEG
cqr/palette.py    colour model of one captured symbol (printer mixing), fitted by EM
cqr/decoder.py    image -> payload (detection, geometry, calibration, classification); decode_all()
cqr/simulate.py   camera / print simulator used by the tests
cqr/__main__.py   command line interface
tests/            pytest suite, segno cross-check, diagnostics, evaluation, print page, photo decoding
research/         01 prior art, 02 QR structure reference, 03 design decisions, 04 evaluation
examples/         sample symbols
print_test/       A4 test pages (plain finders and cmy_cores/), manifests, phone photos
web/              browser demo (Pyodide), published by .github/workflows/pages.yml
```

Run the tests with `python -m pytest tests -q` (48 tests, about 2 min) and the full
robustness evaluation with `python tests/evaluate.py` (writes `research/04_evaluation_results.md`).
Photos of the printed test pages: `python tests/decode_photo.py photo.jpg --all` (every
symbol in the image) or `--id B1` (one symbol, compared with the manifest).

## Symbol format in one page

* **Geometry**: identical to QR version 1..40 (21..177 modules, 4-module white quiet zone).
* **Finder patterns**: the 7x7 ring of the top-left / top-right / bottom-left finder is
  pure red / green / blue, the 3x3 core the complementary cyan / magenta / yellow, light
  modules white.  Separators white.  (`encode(core_complement=False)` or `--plain-finders`
  gives plain red / green / blue finders; the decoder detects both variants.)
* **Timing, alignment, dark module, format and version modules**: black and white exactly as
  in QR.  Together with the finders they provide the eight calibration references
  black, white, red, green, blue, cyan, magenta, yellow, spread over the whole symbol.
* **Format information** (15 bits, BCH(15,5), masked with 0x5412, both copies at the QR
  positions, black/white): 5 payload bits = 2 bits EC level (QR encoding L=01, M=00, Q=11,
  H=10) + 3 bits colour profile index (table above, `mono`=6, `gray4`=7).
* **Version information** (V >= 7): identical to QR.
* **Data modules**: visited in QR placement order.  Each module carries
  `k_R + k_G + k_B` bits (R bits first, MSB first).  A channel's `k` bits select one of
  `2^k` equally spaced sRGB levels via Gray code (`level = gray_decode(bits)`), so a
  neighbouring-level misread costs one bit.
* **Bit stream**: RS symbols are `s` bits wide, with `s = 9` for `rgb333`, `s = 12` for
  `rgb444` (one module = one RS symbol) and `s = 8` otherwise (GF(256) with QR's primitive
  polynomial 0x11D; GF(2^9)/GF(2^12) use reedsolo's default primitive polynomials, generator
  roots alpha^0..).  `N = floor(data_modules * bits_per_module / s)` symbols,
  `B = ceil(N/(2^s-1))` blocks, `E = 2*ceil(r*N/B)` parity symbols per block with
  r = 7/15/25/30 % for L/M/Q/H, data symbols split as evenly as possible (short blocks
  first).  Symbols are interleaved like QR (data i of every block, then parity i of every
  block) and XORed with a fixed xorshift32 whitening sequence (seed 0xC0DEC0DE, top `s` bits
  of each state).  The container bytes are packed MSB-first into the data symbols.  There
  are no mask patterns.
* **Payload container**: byte 0 = `type << 4 | 0xC` (type 0 bytes, 1 UTF-8 text,
  2 zlib bytes, 3 zlib text), bytes 1-2 = big-endian length, then the data, then
  alternating pad bytes 0xEC 0x11.

## Decoder outline

1. finder detection by 1:1:3:1:1 run scanning of the min-channel image (all three coloured
   finders are dark there) and of the per-colour purity maps; colour keying of candidates;
2. version estimation from the finder spacing (module size corrected for rotation), with
   candidate versions scored by timing-pattern agreement and confirmed by the version bits;
3. grid fitting: affine from the three finders, then alignment patterns located one by one
   with a 5x5 template search and the homography refitted after each hit;
4. module sampling over a small central sub-grid (retried with a tighter window if
   decoding fails); shading correction from the known white/black modules (polynomial
   fields); a 3x3 affine colour calibration for reading the format bits;
5. colour model of this symbol (`cqr/palette.py`): Neugebauer interpolation of the eight
   measured corner colours, inverted per module to estimate the tone curves axis by axis,
   then expectation-maximisation with a tensor-product polynomial model, neighbour
   interference cancellation and a Mahalanobis nearest-colour classifier (printers mix
   subtractively: the secondaries are far from the sum of the primaries, which is why a
   per-channel calibration fails on real prints); confidence per module; RS decoding with
   erasures on the least confident symbols (at most 3/4 of the parity).

## Real-world print test (inkjet, plain paper, phone camera)

Test pages with 18 symbols each (V3, EC M; profiles mono to rgb333; modules 1.02, 0.68,
0.51 mm) were printed on a Brother CMY inkjet and photographed with a phone.  Results
(details and the measured printed palette in `research/04_evaluation_results.md`):

| profile | bits/module | gain vs QR | result |
|---|---|---|---|
| mono | 1 | 1.1x | decodes everywhere, down to 6 px/module in a whole-page photo |
| rgb111 | 3 | **3.5x** | 0 module errors on close-ups at 1.02 and 0.51 mm; decodes from a page photo at 9 px/module |
| rgb221 | 5 | 5.8x | on the edge: decodes from a good page photo at 1.02 mm (8 % module errors), not from a noisier one |
| rgb222 and denser | 6+ | | not decodable on plain paper: printed colours 1.3 sigma apart, even an oracle classifier has 17 % errors |

Capacity grows with the logarithm of the number of colours and the printer's gamut
compression plus camera noise set how many colours remain distinguishable, so 3 bits per
module is the robust print density and 5 the achievable one; the denser profiles are for
screens and scanners.

## Measured robustness (simulated capture, `tests/evaluate.py`)

Highest-density profile that decoded 100 % of symbols per capture preset (net payload
bits per module after header and parity, gain relative to the `mono` profile at level L):

| preset | conditions | best profile | net bits/module | gain |
|---|---|---|---|---|
| screen | 8 px/module, slight tilt, JPEG 90 | rgb444 / L | 8.47 | 12.5x |
| scanner | 6 px/module, mild cast, cross-talk 6 % | rgb444 / L | 8.47 | 12.5x |
| phone-good | 6 px/module, tilt, blur, cast, JPEG 85 | rgb332 / L | 5.60 | 8.2x |
| phone-poor | 4.5 px/module, strong tilt/blur/noise/cast, JPEG 70 | rgb111 / L | 2.08 | 3.1x |

`rgb111` (8 colours) decodes every "phone-good" and "phone-poor" symbol at all EC levels;
`rgb222` (64 colours) needs phone-good or better.  These are simulation results; printer
gamut is not modelled there (see the real-world section above).

See `research/03_design_decisions.md` for why these choices were made and
`research/04_evaluation_results.md` for the full table.
