CQR - colored QR code
data is coded both in QR code layout and color
- has the same structure as regular QR code
- uses the 3 QR code corner markers as color calibration, one is RED, one is GREEN, one is BLUE
- has parametrized color resolution
- maximizes the amount of data that can be encoded


The plan
- [x] reasearch throughly if anyone has done it before and if so then how  -> research/01_prior_art_colored_barcodes.md
- [x] reasearch deeply QR code structure and layout                         -> research/02_qr_code_structure.md
- [x] save all the research into a special folder                           -> research/ (+ 03 design decisions, 04 evaluation)
- [x] write the code                                                        -> cqr/ package, CLI: python -m cqr
- [x] test the code                                                         -> tests/ (pytest), tests/evaluate.py

Open ideas / next steps
- [x] print a few symbols and photograph them with a phone (2026-10-04, print_test/photos/, results in
      research/04 "Real-world print test"): rgb111 decodes down to 0.51 mm modules and from a whole-page photo at
      9 px/module; rgb221 and denser fail on an inkjet print (printed colours 1.3-1.5 sigma apart, oracle 7-12 % errors)
- [x] complementary C/M/Y finder cores as free secondary-colour references + palette init by inverting the
      corner model (2026-10-04, research/03 section 9); page in print_test/cmy_cores/ still to be printed
- [ ] print-specific palette (CMY-friendly) as an extra profile: 8 corners + intermediates chosen inside the printer
      gamut (orange / purple / teal ...) instead of a dense RGB lattice; needs a profile slot (gray4 is the least useful)
- [ ] stored printer profile: a one-time calibration chart (all palette colours with known labels) measured once per
      printer/camera pair; would let the oracle-level classifier (7 % errors on rgb222) run on real prints
- [ ] more photos: rgb111 at 0.68 / 0.51 mm from a phone at normal distance, and rgb221 under better light / larger
      modules (1.5-2 mm) to find where 5 bits/module starts working in print
- [ ] soft (annealed) EM or a better init for the palette model when more than 64 colours are printed
- [ ] local (per-region) colour calibration using alignment patterns for very large symbols under uneven light
- [ ] structured append (splitting a payload over several symbols) and ECI/charset flags
- [ ] optional legacy-QR-readable luminance layer (backward compatible mode), see design doc section 7
