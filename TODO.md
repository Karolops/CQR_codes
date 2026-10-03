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
- [ ] print a few symbols (examples/) and photograph them with a phone; run `python -m cqr decode photo.jpg --report`
      and compare with the simulated results in research/04_evaluation_results.md
- [ ] print-specific palette (CMY-friendly) as an extra profile if laser prints merge red/magenta
- [ ] local (per-region) colour calibration using alignment patterns for very large symbols under uneven light
- [ ] structured append (splitting a payload over several symbols) and ECI/charset flags
- [ ] optional legacy-QR-readable luminance layer (backward compatible mode), see design doc section 7
