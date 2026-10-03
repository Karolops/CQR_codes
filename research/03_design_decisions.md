# CQR design decisions

This document records the ideas gathered from the prior-art survey
(`01_prior_art_colored_barcodes.md`), the QR structure reference
(`02_qr_code_structure.md`) and my own experiments, how each idea was judged, and
what was finally implemented in the `cqr` package.  The requirements from
`TODO.md` were: same structure as a regular QR code; the three corner markers
coloured red, green and blue and used for colour calibration; parametrised
colour resolution; maximum data capacity.

## 1. How to map colours to bits

Ideas considered:

| idea | source | judgement |
|---|---|---|
| A. *Layered QR*: print 3 independent QR codes in the C, M, Y (or R, G, B) channels, decode each channel with a standard QR decoder | Blasinski/Bulan/Sharma 2013, HiQ 2018 | Simple and reuses existing decoders, but caps density at 3 bits/module, triples the format/header overhead, and each channel needs its own black finder patterns, which conflicts with coloured finders. Rejected as the main design (it is a special case of B with k=1 anyway). |
| B. *Per-channel multilevel*: channel c carries k_c bits as 2^k_c equally spaced levels; a module carries k_R+k_G+k_B bits | generalises A and HCC2D's RGB-cube palettes | Directly gives the required "parametrised colour resolution" (choose k per channel), lets the weak blue channel get fewer levels (profile `rgb221`, `rgb332`), and classification decomposes into three 1-D problems that need few samples to adapt. **Chosen.** |
| C. *Arbitrary palette of N colours* (JAB style, N not a power of two per channel, e.g. 4 colours blue/green/magenta/yellow) | JAB Code, HCCB | More flexible for ink-optimised palettes, but needs a 3-D classifier and mixed-radix bit packing; not a power-of-two product means wasted bits. Deferred: a print-optimised palette can be added later as an extra profile index. |
| D. Luminance layer decodable by legacy QR readers (backward compatibility) | "DualCodes" concept, unproven in the literature | Attractive but costs density (dark/light must be separable by luminance, which forbids half of the colour combinations) and is unproven. Not implemented; see section 7 for how it could be added. |

Levels are **Gray coded** so that the most probable error (a neighbouring level)
flips a single bit. Levels are equally spaced in sRGB, not in linear light,
because both display and camera pipelines are approximately sRGB encoded; the
decoder's k-means step absorbs the residual nonlinearity.

Profiles are selected by a 3-bit index stored in the format information, so a
decoder learns the colour resolution before touching any coloured data module:

| index | profile | bits/module | colours |
|---|---|---|---|
| 0 | rgb111 | 3 | 8 (RGB cube vertices, same set as JAB's 8-colour palette) |
| 1 | rgb221 | 5 | 32 |
| 2 | rgb222 | 6 | 64 |
| 3 | rgb332 | 8 | 256 |
| 4 | rgb333 | 9 | 512 |
| 5 | rgb444 | 12 | 4096 |
| 6 | mono | 1 | 2 (QR-like baseline) |
| 7 | gray4 | 2 | 4 grey levels |

The literature (Fraunhofer, Tor Vergata, Bagherinia) agrees that **8 colours is
the practical ceiling for office printers plus phone cameras**; the simulation in
`04_evaluation_results.md` reproduces this: `rgb111` survives the "phone-poor"
preset while `rgb222` needs scanner- or screen-quality capture.  `rgb111` is
therefore the default; the denser profiles are for screens, scanners and
file-to-file transfer where they give up to 12 bits/module.

## 2. Keeping the QR structure

Everything geometric is taken over unchanged from ISO/IEC 18004 (verified
module-by-module against the `segno` encoder for all 40 versions by
`tests/check_layout_vs_segno.py`): finder patterns with separators, timing
patterns, alignment pattern positions, the dark module, the two copies of the
15-bit format information, the version information for V >= 7, and the zig-zag
placement order.

Why keep QR's placement order instead of a simpler raster?  It costs nothing,
it keeps the "same structure" requirement literal, and QR's column snake
spreads consecutive bits over neighbouring modules, which combines well with the
RS block interleaving: a local smudge hits consecutive codewords that belong to
*different* blocks.

**Format information** uses QR's BCH(15,5) code and the standard mask 0x5412,
so the error tolerance (3 bits per copy) is inherited.  The 5 payload bits are
redefined: 2 bits EC level (QR's own encoding) + 3 bits colour profile index.
QR's 3 mask bits are not needed (see section 4).

**Function pattern colours.**  The finders' dark modules are pure red, green,
blue (top-left, top-right, bottom-left).  All other function modules stay black
and white.  This gives five calibration references that are spread over the whole
symbol: red/green/blue in three corners, white in the separators, finder light
rings, timing light modules and alignment rings, black in the timing dark
modules, alignment rings and the dark module.  Together they are exactly the
references needed to fit an affine colour model (3x3 matrix + offset = 12
parameters from 5 points x 3 channels = 15 equations) - the user's choice of
red, green and blue finders turns out to be the minimum set that makes the
calibration well posed, because together with white they span the colour space.

JAB Code's experience ("finder pattern could not be found" was its dominant
failure) is the main argument *against* coloured finders.  The decoder avoids
that failure mode by not relying on colour for detection: red, green and blue
each have at least one zero channel, so in the **min(R,G,B) image all three
finders are as dark as a black QR finder** and the classic zxing 1:1:3:1:1
run-length scan works unchanged.  Colour is used only afterwards to tell which
finder is which.  (The per-colour purity maps are scanned as a second candidate
source for the case where the data area produces many dark false positives.)

Bonus: because colour identifies the finders, orientation is known without the
usual geometric sort, and even a **mirrored** capture (scan through a
transparent sheet, selfie camera) decodes, which a QR reader has to handle by
brute force.

## 3. Error correction

Idea: LDPC (JAB) vs Reed-Solomon (QR).  JAB chose LDPC because colour errors are
random rather than bursty.  RS over GF(256) was kept because it is what QR uses,
it is simple, it supports **erasures** (the decoder knows which modules were
uncertain), and with blocks of up to 255 bytes and QR-style interleaving the
random-error assumption is handled well enough; the bigger lever is the colour
profile.

Block structure is computed from the number of codewords instead of tabulated:
`N = floor(data_modules * bits_per_module / 8)` codewords, `B = ceil(N/255)`
blocks, `E = 2*ceil(r*N/B)` parity codewords per block with r = 7/15/25/30 % for
L/M/Q/H, data codewords split as evenly as possible (short blocks first, like
QR's two groups).  This keeps QR's semantics "level X recovers X % of codewords"
for every profile and version.

An important consequence that the tests quantify: **a module error damages one
or two whole RS symbols** (for the 9- and 12-bit profiles the RS symbol is therefore
aligned to the module, see section 7.1), so the tolerable *module* error rate is lower than the
codeword recovery rate.  A byte spans about `8/bpm + 1` modules, hence the
tolerable module error fraction is roughly `1 - (1 - r)^(1/(8/bpm + 1))`:
about 2 % (L) to 10 % (H) for `rgb111`, 3.5 % to 17 % for `rgb333`.  Denser
profiles tolerate a *higher* module error rate but produce one, because the
levels are closer together.

**Soft decoding.**  Each module gets a confidence (normalised distance margin to
the nearest decision boundary, minimum over channels).  Bytes inherit the
confidence of their weakest module.  If a block fails plain RS decoding, the
least confident bytes are declared erasures (E/4, E/2, 3E/4, E-1 of them in
turn); RS corrects v errors + e erasures when 2v + e <= E, so this roughly doubles
the tolerance when the confidence ranking is informative.  In the harsh test it
was: wrong modules had mean confidence 0.24 vs 0.44 overall.

## 4. Whitening instead of masks

QR's 8 mask patterns exist to avoid finder-like patterns and large uniform
areas in the binary image.  CQR instead XORs the final interleaved codeword
sequence with a fixed xorshift32 pseudo-random byte sequence.  Structured
payloads (zeros, repeated bytes, padding) therefore render as uniformly
distributed colours, the three format bits that QR spends on the mask index are
freed for the profile index, and the encoder does not need the penalty-score
search.  The decoder undoes the XOR before RS decoding, so parity bytes are
whitened too.

## 5. Decoder design (where most of the engineering went)

Ideas from the literature and what was done with them:

* **Reference palette inside the symbol, replicated far apart** (HCC2D, JAB,
  Konica).  Done through the function patterns as described in section 2
  without adding any new structure: three corners for R/G/B and white/black
  references distributed along both timing lines and every alignment pattern.
* **Local white/black normalisation** (HCC2D) - implemented as polynomial
  *shading fields*: per channel, a quadratic (V >= 2) or planar (V1) field is
  fitted by robust least squares to all known-white modules and a planar field
  to all known-black modules; every module is normalised by its local
  white/black before colour calibration.  This addresses the finding that
  global k-means was the worst method on phones because of uneven light.
* **3x3 mixing matrix for cross-channel interference** (Blasinski, HiQ) -
  the affine calibration (matrix + offset) is fitted from the five references.
  Printer/camera cross-talk, illuminant colour and contrast loss are corrected
  in one step.
* **Palette-seeded clustering** (HCC2D) - per-channel 1-D k-means initialised
  at the ideal level positions, with guards against centroid collapse; it
  adapts to gamma and to the actual printed levels of multi-level profiles.
* **Cross-module interference (CMI) cancellation** (HiQ) - after a first
  classification, the leak coefficient of each channel from the 4 neighbours is
  estimated by least squares and subtracted, then modules are reclassified.
  In simulation it gives a small gain (15.0 % -> 14.3 % module errors in the
  harshest case); it is kept because it is cheap and never hurt.
* **Geometry from all alignment patterns** (HiQ's RGT, zxing).  The grid is
  fitted as a single homography from the three finder centres plus every
  alignment pattern that can be found; patterns are located nearest-to-finders
  first with a 5x5 template search and the homography is refitted after each
  hit, so the prediction for the next pattern is already perspective-corrected.
  This was the fix for large tilted symbols (87 % module errors with the
  affine-only grid, 0 % after chaining).
* **Version estimation by hypothesis testing**: the finder-to-finder distance
  divided by the module size gives a first estimate; the module size measured
  by axis-aligned run scanning is inflated by 1/cos(rotation), which is
  corrected from the measured finder axis angle (without this, symbols rotated
  by 38-48 degrees were systematically read two versions too small).  A window
  of candidate versions is then fitted and scored by timing-pattern agreement,
  widened if nothing scores well; for V >= 7 the version information bits are
  read as a final confirmation.
* **Quantile-initialised level centroids**: because the codeword stream is
  whitened, every level of every channel is used equally often, so the
  quantiles of the observed values are a gamma-independent estimate of the
  level centroids.  k-means starts from them instead of from the linear ideal
  positions; this is what makes 8 and 16 levels per channel decodable when the
  capture pipeline applies an unknown tone curve.
* **Sample a small central area per module** (JAB samples 3x3 pixels) - a 3x3
  sub-grid over the central 50 % of each module, bilinear.

## 6. What the simulation showed

The camera simulator (`cqr/simulate.py`) applies, in order: scale to a target
module size, perspective tilt, rotation, gamma, illuminant colour cast, black
level lift / white level loss, channel cross-talk, Gaussian blur, sensor noise
and JPEG compression with 4:2:0 chroma subsampling.  Findings:

1. The dominant failure for small modules is **JPEG chroma subsampling plus
   coarse chroma quantisation**: at 4.5 px/module, JPEG quality 60 raises the
   `rgb111` module error rate from 2 % to 15 % (quality 90: 2 %), almost all of
   it in the blue channel, exactly the weak channel the literature reports.
   Keep modules at >= 6 px in the captured image or avoid chroma-subsampled
   JPEG (the renderer writes JPEG with subsampling disabled for this reason).
2. Blur, noise, colour cast, cross-talk and contrast loss individually cost
   only 2-8 % module errors for `rgb111` and are corrected by level M or H.
3. Final numbers (`04_evaluation_results.md`, 5 seeds per cell, V6 symbols):
   screen capture decodes every profile up to `rgb444` (8.4 net bits/module,
   12x the mono baseline); scanner-like capture decodes `rgb444` at level M
   and everything denser-than-mono below it; "phone-good" capture decodes
   `rgb332` at L (5.6 net bits/module, 8x) and every profile up to `rgb332`
   at all levels, while `rgb333`/`rgb444` fail there (16-25 % and 70 % module
   errors); "phone-poor" capture is `rgb111` territory (Q or H, 1.2 net
   bits/module, 1.8x mono) - which matches the literature's "8 colours is the
   practical phone ceiling" almost exactly.
4. Everything in `04_evaluation_results.md` is simulation; real printers add
   gamut limits (a laser printer merged red and magenta in HCC2D's tests).  The
   first real-world step is to print `examples/*.png` at >= 6 printer dots per
   module and photograph them.

## 7. Density experiments (second round)

Four ideas for squeezing out more data were tested; scripts are reproduced in
`tests/evaluate.py`-style form in the session scratchpad and summarised here.

**8.1 Module-aligned RS symbols (implemented).**  With byte-sized RS symbols a
9- or 12-bit module always straddles two bytes, so one module error costs two
codewords.  Monte-Carlo test (2000 modules, 30 % parity, QR-style interleave,
random module errors, maximum error rate still decoded in 5 of 6 trials):

| bits/module | bytes GF(2^8) | aligned GF(2^bpm) |
|---|---|---|
| 3 | 4.6 % | - (field too small) |
| 6 | 7.5 % | 7.4 % |
| 8 | 11.6 % | 11.7 % |
| 9 | 7.0 % | **13.0 %** |
| 12 | 6.9 % | **14.8 %** |

The 9- and 12-bit profiles therefore now use RS over GF(2^9) and GF(2^12)
(one module = one symbol, blocks up to 511 / 4095 symbols, which also helps
through the law of large numbers).  At equal robustness this lets those
profiles run one EC level lower, i.e. roughly 15-20 % more payload, and it
removes the anomaly that `rgb333` tolerated *fewer* module errors than
`rgb332`.  Cost: pure-Python GF(2^12) arithmetic makes a version-40 `rgb444`
decode take about 5 s instead of 2 s.

**8.2 Non-power-of-two level counts.**  Per-channel classification error at
V6 under the "phone-good" preset (no ECC, 3 seeds):

| levels per channel | 2 | 3 | 4 | 5 | 6 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|---|---|
| R error | 0 | 0 | 0 | 0.3 % | 0.7 % | 5.5 % | 18 % | 33 % |
| G error | 0 | 0 | 0 | 0 | 0 | 1.1 % | 10 % | 23 % |
| B error | 0 | 0 | 0.1 % | 1.4 % | 4.3 % | 14 % | 33 % | 48 % |

Green (sampled by half the Bayer pixels, full-resolution in JPEG luminance)
tolerates twice the levels of blue.  A mixed-radix palette such as 6x8x5 (240
colours, 7.9 bits) would sit between `rgb222` and `rgb332` with about 3 %
module errors, but at this preset the net density after parity is the same as
`rgb332`/L, so mixed radix mainly offers finer tuning, not a jump.  A better
use of the finding is an unequal power-of-two profile such as 2+3+2 bits
(4x8x4 colours, 7 bits/module, about 1 % errors here); it is not added
because the 3-bit profile field is full, but it would replace `gray4` if a
slot is needed.  Scanner-quality capture classified all 16 levels of every
channel without error, which is why `rgb444` works there.

**8.3 Quiet zone.**  Decoding with a 2-, 1- or 0-module quiet zone on grey
and dark backgrounds succeeded in 5/5 cases each under "phone-good".  The
decoder does not rely on the quiet zone (finder detection is run-length
based and the grid comes from finders + alignment patterns), so `encode -q 1`
is offered.  For a V1 symbol the printed area drops from 29^2 to 23^2 module
units, a 37 % reduction; for V40 it is 3.4 %.

**8.4 Speed.**  Version 40: `rgb111` encode 0.0 s / decode 1.5 s, `rgb333`
0.3 s / 2.1 s, `rgb444` 2.1 s / 4.9 s on a clean 925 px render (pure Python
Reed-Solomon dominates for the aligned fields).

Ideas judged but not tested because they cannot raise density per module:
orientation modulation (Bulan & Sharma) needs more pixels per module and is
equivalent to using smaller modules; "4th primary" colours cannot be separated
by a 3-channel camera; shrinking alignment patterns or dropping the second
format copy would break the QR structure for 1-4 % gain.

## 8. Ideas deliberately left for later

* **Print-optimised palette profile** (CMY-friendly, avoiding yellow-vs-white):
  reserve a profile index; needs a 3-D classifier.
* **Backward-compatible luminance layer**: use profile `rgb111` with the
  constraint that the R bit equals the luminance class and define the other two
  bits only on the chroma; a legacy reader would then see a valid QR if the
  format bits were QR's. The 3 freed mask bits are the obstacle: QR readers need
  a mask index there.  Possible but halves density; not pursued.
* **Local (per-cell) calibration for very large symbols** under spot lighting:
  the shading fields are global quadratics; a per-alignment-cell model would be
  the next step.
* **Structured append** across several symbols and ECI charset flags: the
  container has a 4-bit type field with room for both.
