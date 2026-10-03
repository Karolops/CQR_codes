# QR Code (ISO/IEC 18004, Model 2) Symbol Structure - Implementation Reference

Scope: QR Code Model 2, versions 1-40, as specified in ISO/IEC 18004 (2000 / 2006 / 2015 / 2024 editions; also JIS X 0510). Micro QR and rMQR are out of scope.
Purpose: an exact, machine-readable reference for implementing a QR-layout-compatible encoder and decoder from scratch.

Coordinate convention used in this document: `(row, col)` with origin `(0, 0)` at the TOP-LEFT module, row increasing downward, col increasing rightward. `size = 17 + 4*V`. Bit indices in integers are LSB = bit 0 unless stated otherwise. "Dark" = 1 = black, "light" = 0 = white.

Verification note: every numeric table below was regenerated from formulas/tables in Project Nayuki's `qrcodegen.py` and cross-checked, cell by cell, against zxing `Version.java` (EC blocks + alignment centres), python-qrcode `base.py` (`RS_BLOCK_TABLE`), segno `consts.py` (format/version bit strings, data-bit capacities), and Thonky's capacity / alignment / remainder-bit / format-string tables. Zero mismatches were found. Sources:
- Thonky QR Code Tutorial: https://www.thonky.com/qr-code-tutorial/
- Nayuki, "Creating a QR Code step by step": https://www.nayuki.io/page/creating-a-qr-code-step-by-step and library: https://github.com/nayuki/QR-Code-generator (python/qrcodegen.py)
- zxing: https://github.com/zxing/zxing/tree/master/core/src/main/java/com/google/zxing/qrcode (decoder/Version.java, decoder/BitMatrixParser.java, decoder/FormatInformation.java, decoder/DataMask.java, encoder/MatrixUtil.java, detector/Detector.java, detector/FinderPatternFinder.java)
- segno: https://github.com/heuer/segno/blob/master/segno/consts.py (annotated with ISO/IEC 18004:2015 table numbers)
- python-qrcode: https://github.com/lincolnloop/python-qrcode/blob/main/qrcode/base.py
- Wikipedia "QR code": https://en.wikipedia.org/wiki/QR_code
- OpenCV objdetect: https://github.com/opencv/opencv/blob/4.x/modules/objdetect/src/qrcode.cpp
- Denso Wave module-size guidance: https://www.qrcode.com/en/howto/cell.html

---

## 1. Versions, sizes and module budget

- `size(V) = 21 + 4*(V-1) = 17 + 4*V` modules per side, V = 1..40 (21x21 .. 177x177). (Wikipedia; zxing `getDimensionForVersion`.)
- `size` is always odd and `size mod 4 == 1`. Decoders use this: a measured dimension not congruent to 1 mod 4 is wrong (zxing `computeDimension` nudges it).
- Total modules = `size^2`.
- Raw data modules (bits available for data+EC codewords+remainder bits), closed form (Nayuki `_get_num_raw_data_modules`):
  ```
  raw = (16*V + 128)*V + 64
  if V >= 2:
      numAlign = V // 7 + 2            # alignment centres per axis
      raw -= (25*numAlign - 10)*numAlign - 55
      if V >= 7:
          raw -= 36                    # two 6x3 version-info blocks
  ```
  Derivation: `size^2` minus 3 finders with separators (3*64 = 192), minus the two 15-bit format copies + dark module (31), minus timing patterns (2*(size-16)), minus `(numAlign^2 - 3)` alignment patterns of 25 modules each, plus the 5 modules where each of the `2*(numAlign-2)` edge alignment patterns overlaps the timing pattern, minus 36 version bits for V >= 7.
- Total codewords = `raw // 8`; remainder bits = `raw mod 8` (0, 3, 4 or 7). Total codewords are identical for all four EC levels of a version.
- "Function + reserved modules" below = `size^2 - raw`: finders, separators, timing, alignment, format info (2x15), dark module, version info (2x18 when V >= 7).

### Table 1 - per-version geometry (all 40 versions)

| Version | Size | Align. patterns (count) | Align. centers | Function+reserved modules | Raw data modules (bits) | Total codewords | Remainder bits |
|---|---|---|---|---|---|---|---|
| 1 | 21 | 0 | - | 233 | 208 | 26 | 0 |
| 2 | 25 | 1 | 6,18 | 266 | 359 | 44 | 7 |
| 3 | 29 | 1 | 6,22 | 274 | 567 | 70 | 7 |
| 4 | 33 | 1 | 6,26 | 282 | 807 | 100 | 7 |
| 5 | 37 | 1 | 6,30 | 290 | 1079 | 134 | 7 |
| 6 | 41 | 1 | 6,34 | 298 | 1383 | 172 | 7 |
| 7 | 45 | 6 | 6,22,38 | 457 | 1568 | 196 | 0 |
| 8 | 49 | 6 | 6,24,42 | 465 | 1936 | 242 | 0 |
| 9 | 53 | 6 | 6,26,46 | 473 | 2336 | 292 | 0 |
| 10 | 57 | 6 | 6,28,50 | 481 | 2768 | 346 | 0 |
| 11 | 61 | 6 | 6,30,54 | 489 | 3232 | 404 | 0 |
| 12 | 65 | 6 | 6,32,58 | 497 | 3728 | 466 | 0 |
| 13 | 69 | 6 | 6,34,62 | 505 | 4256 | 532 | 0 |
| 14 | 73 | 13 | 6,26,46,66 | 678 | 4651 | 581 | 3 |
| 15 | 77 | 13 | 6,26,48,70 | 686 | 5243 | 655 | 3 |
| 16 | 81 | 13 | 6,26,50,74 | 694 | 5867 | 733 | 3 |
| 17 | 85 | 13 | 6,30,54,78 | 702 | 6523 | 815 | 3 |
| 18 | 89 | 13 | 6,30,56,82 | 710 | 7211 | 901 | 3 |
| 19 | 93 | 13 | 6,30,58,86 | 718 | 7931 | 991 | 3 |
| 20 | 97 | 13 | 6,34,62,90 | 726 | 8683 | 1085 | 3 |
| 21 | 101 | 22 | 6,28,50,72,94 | 949 | 9252 | 1156 | 4 |
| 22 | 105 | 22 | 6,26,50,74,98 | 957 | 10068 | 1258 | 4 |
| 23 | 109 | 22 | 6,30,54,78,102 | 965 | 10916 | 1364 | 4 |
| 24 | 113 | 22 | 6,28,54,80,106 | 973 | 11796 | 1474 | 4 |
| 25 | 117 | 22 | 6,32,58,84,110 | 981 | 12708 | 1588 | 4 |
| 26 | 121 | 22 | 6,30,58,86,114 | 989 | 13652 | 1706 | 4 |
| 27 | 125 | 22 | 6,34,62,90,118 | 997 | 14628 | 1828 | 4 |
| 28 | 129 | 33 | 6,26,50,74,98,122 | 1270 | 15371 | 1921 | 3 |
| 29 | 133 | 33 | 6,30,54,78,102,126 | 1278 | 16411 | 2051 | 3 |
| 30 | 137 | 33 | 6,26,52,78,104,130 | 1286 | 17483 | 2185 | 3 |
| 31 | 141 | 33 | 6,30,56,82,108,134 | 1294 | 18587 | 2323 | 3 |
| 32 | 145 | 33 | 6,34,60,86,112,138 | 1302 | 19723 | 2465 | 3 |
| 33 | 149 | 33 | 6,30,58,86,114,142 | 1310 | 20891 | 2611 | 3 |
| 34 | 153 | 33 | 6,34,62,90,118,146 | 1318 | 22091 | 2761 | 3 |
| 35 | 157 | 46 | 6,30,54,78,102,126,150 | 1641 | 23008 | 2876 | 0 |
| 36 | 161 | 46 | 6,24,50,76,102,128,154 | 1649 | 24272 | 3034 | 0 |
| 37 | 165 | 46 | 6,28,54,80,106,132,158 | 1657 | 25568 | 3196 | 0 |
| 38 | 169 | 46 | 6,32,58,84,110,136,162 | 1665 | 26896 | 3362 | 0 |
| 39 | 173 | 46 | 6,26,54,82,110,138,166 | 1673 | 28256 | 3532 | 0 |
| 40 | 177 | 46 | 6,30,58,86,114,142,170 | 1681 | 29648 | 3706 | 0 |

Remainder bits by version (Thonky "Structure final message", confirmed by formula): V1: 0; V2-6: 7; V7-13: 0; V14-20: 3; V21-27: 4; V28-34: 3; V35-40: 0.

---

## 2. Finder patterns (position detection patterns)

- Three 7x7 finder patterns, identical, at top-left (rows 0-6, cols 0-6), top-right (rows 0-6, cols size-7..size-1), bottom-left (rows size-7..size-1, cols 0-6). (Thonky "Module placement in matrix".)
- Layout (1 = dark): 7x7 dark ring, 5x5 light ring, 3x3 dark centre. Using Chebyshev distance d from the centre module: dark iff `d != 2` (d in {0,1} centre, d = 3 outer ring); Nayuki draws a 9x9 block with `dark iff max(|dx|,|dy|) not in {2, 4}`, where d = 4 is the separator.
  ```
  1111111
  1000001
  1011101
  1011101
  1011101
  1000001
  1111111
  ```
- Separator: 1-module light border on the sides of each finder that face the interior of the symbol (an L shape of 15 modules per finder): row 7 cols 0-7 and col 7 rows 0-7 for the top-left finder; row 7 cols size-8..size-1 and col size-8 rows 0-7 for the top-right; row size-8 cols 0-7 and col 7 rows size-8..size-1 for the bottom-left. Finder + separator occupy an 8x8 corner block each (zxing `buildFunctionPattern` reserves 9x9 / 8x9 / 9x8 including the adjacent format strip).
- Detection signature: any scan line through the centre (horizontal, vertical or diagonal) has dark:light:dark:light:dark run lengths in ratio 1:1:3:1:1. This is the property finders rely on (see section 12). Finder patterns are deliberately chosen so this ratio is unlikely to appear elsewhere in the symbol (penalty rule 3 in masking discourages it).

---

## 3. Timing patterns

- Horizontal timing pattern: row 6, cols 8 .. size-9 (between the separators). Vertical timing pattern: col 6, rows 8 .. size-9.
- Alternating dark/light, starting and ending with dark. Module `(6, c)` is dark iff `c` is even; module `(r, 6)` is dark iff `r` is even (zxing `embedTimingPatterns`: `bit = (i + 1) % 2`; Nayuki: `self._set_function_module(6, i, i % 2 == 0)`). Both end modules adjacent to separators (col 8 and col size-9, both even) are dark, consistent with the finder's outer dark ring at col 6 continuing through.
- Alignment patterns whose centre lies on row 6 or col 6 overlap the timing pattern; the colours are compatible (alignment outer ring dark on the even coordinate, inner ring light on the odd ones, dark centre on the even centre).

---

## 4. Alignment patterns

- Present for V >= 2. Each is 5x5: dark outer ring, light 3x3 ring, single dark centre: dark iff `max(|dx|,|dy|) != 1` (Nayuki `_draw_alignment_pattern`).
  ```
  11111
  10001
  10101
  10001
  11111
  ```
- Centre coordinates: the same list `P` of positions is used for both rows and columns; alignment centres are at every `(P[a], P[b])` EXCEPT the three that would overlap finder patterns: `(P[0], P[0])` top-left, `(P[0], P[last])` top-right, `(P[last], P[0])` bottom-left. Count = `numAlign^2 - 3`. (zxing `buildFunctionPattern`: `if ((x != 0 || (y != 0 && y != max - 1)) && (x != max - 1 || y != 0))`.)
- Closed-form position list (Nayuki `_get_alignment_pattern_positions`, reproduces ISO/IEC 18004 Annex E Table E.1 exactly for all 40 versions):
  ```
  if V == 1: P = []
  numAlign = V // 7 + 2
  step = (V*8 + numAlign*3 + 5) // (numAlign*4 - 4) * 2       # integer division, result even
  P = [6] + [size - 7 - i*step for i in range(numAlign-2, -1, -1)]   # ascending
  ```
  i.e. first centre is always 6, last is always `size - 7`, interior centres are spaced by the even integer `step` working backwards from `size - 7`; the gap between 6 and the second position is the only irregular one.
- Full table (Table E.1; verified identical in Thonky, zxing `Version.java`, segno `ALIGNMENT_POS`):

| V | Centres | V | Centres | V | Centres | V | Centres |
|---|---|---|---|---|---|---|---|
| 1 | - | 11 | 6,30,54 | 21 | 6,28,50,72,94 | 31 | 6,30,56,82,108,134 |
| 2 | 6,18 | 12 | 6,32,58 | 22 | 6,26,50,74,98 | 32 | 6,34,60,86,112,138 |
| 3 | 6,22 | 13 | 6,34,62 | 23 | 6,30,54,78,102 | 33 | 6,30,58,86,114,142 |
| 4 | 6,26 | 14 | 6,26,46,66 | 24 | 6,28,54,80,106 | 34 | 6,34,62,90,118,146 |
| 5 | 6,30 | 15 | 6,26,48,70 | 25 | 6,32,58,84,110 | 35 | 6,30,54,78,102,126,150 |
| 6 | 6,34 | 16 | 6,26,50,74 | 26 | 6,30,58,86,114 | 36 | 6,24,50,76,102,128,154 |
| 7 | 6,22,38 | 17 | 6,30,54,78 | 27 | 6,34,62,90,118 | 37 | 6,28,54,80,106,132,158 |
| 8 | 6,24,42 | 18 | 6,30,56,82 | 28 | 6,26,50,74,98,122 | 38 | 6,32,58,84,110,136,162 |
| 9 | 6,26,46 | 19 | 6,30,58,86 | 29 | 6,30,54,78,102,126 | 39 | 6,26,54,82,110,138,166 |
| 10 | 6,28,50 | 20 | 6,34,62,90 | 30 | 6,26,52,78,104,130 | 40 | 6,30,58,86,114,142,170 |

- Placement order matters for an encoder that draws into a blank matrix: draw finders + separators first, then alignment patterns (they never overlap finders because of the 3-exclusion rule, but they do overlap timing patterns consistently), then timing patterns only on still-empty modules (zxing checks `isEmpty`).

---

## 5. Dark module

- Exactly one always-dark module at `(row, col) = (4*V + 9, 8) = (size - 8, 8)`, i.e. immediately above the bottom-left finder's separator, to the right of the vertical format strip. (Thonky writes it as `(8, 4V+9)` in (x, y) order; Nayuki `_set_function_module(8, size-8, True)`; zxing `embedDarkDotAtLeftBottomCorner`: `matrix.set(8, height - 8, 1)`.)
- It is a function module: never masked, not part of format information, not data.

---

## 6. Format information (15 bits, two copies)

### 6.1 Content
- 5 data bits: 2 EC-level bits followed by 3 mask-pattern bits (`data = ecBits << 3 | mask`).
- EC level indicator (ISO Table 12; segno `ERROR_LEVEL_*`; Nayuki `Ecc.formatbits`): **L = 01, M = 00, Q = 11, H = 10**. Note the order is not L<M<Q<H numerically.
- 10 BCH(15,5) check bits: remainder of `data(x) * x^10` modulo generator `G(x) = x^10 + x^8 + x^5 + x^4 + x^2 + x + 1` = `10100110111` = **0x537**. Bit-serial computation (Nayuki):
  ```
  rem = data
  for _ in range(10): rem = (rem << 1) ^ ((rem >> 9) * 0x537)
  bits15 = ((data << 10) | rem) ^ 0x5412
  ```
- The 15-bit result is XORed with the fixed mask `101010000010010` = **0x5412** so that no EC/mask combination yields all zeros. (zxing `TYPE_INFO_MASK_PATTERN`, Thonky.)
- Decoders: the 32 valid codewords have minimum pairwise Hamming distance 7, so up to 3 bit errors can be corrected by nearest-codeword lookup (zxing `FormatInformation.decodeFormatInformation`, accepts `<= 3` differing bits; it also retries with the 0x5412 mask removed to tolerate non-conformant encoders).

### 6.2 All 32 format strings (bit 14 = MSB written first; verified against Thonky and segno `FORMAT_INFO`)

| EC level | EC bits | Mask 0 | Mask 1 | Mask 2 | Mask 3 | Mask 4 | Mask 5 | Mask 6 | Mask 7 |
|---|---|---|---|---|---|---|---|---|---|
| L | 01 | 111011111000100 (0x77C4) | 111001011110011 (0x72F3) | 111110110101010 (0x7DAA) | 111100010011101 (0x789D) | 110011000101111 (0x662F) | 110001100011000 (0x6318) | 110110001000001 (0x6C41) | 110100101110110 (0x6976) |
| M | 00 | 101010000010010 (0x5412) | 101000100100101 (0x5125) | 101111001111100 (0x5E7C) | 101101101001011 (0x5B4B) | 100010111111001 (0x45F9) | 100000011001110 (0x40CE) | 100111110010111 (0x4F97) | 100101010100000 (0x4AA0) |
| Q | 11 | 011010101011111 (0x355F) | 011000001101000 (0x3068) | 011111100110001 (0x3F31) | 011101000000110 (0x3A06) | 010010010110100 (0x24B4) | 010000110000011 (0x2183) | 010111011011010 (0x2EDA) | 010101111101101 (0x2BED) |
| H | 10 | 001011010001001 (0x1689) | 001001110111110 (0x13BE) | 001110011100111 (0x1CE7) | 001100111010000 (0x19D0) | 000011101100010 (0x0762) | 000001001010101 (0x0255) | 000110100001100 (0x0D0C) | 000100000111011 (0x083B) |

### 6.3 Placement (bit index i = i-th least significant bit of the final 15-bit value; bit 14 is the MSB)

Copy 1 (wraps around the top-left finder's separator, on row 8 and col 8):

| bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (row, col) | (0,8) | (1,8) | (2,8) | (3,8) | (4,8) | (5,8) | (7,8) | (8,8) | (8,7) | (8,5) | (8,4) | (8,3) | (8,2) | (8,1) | (8,0) |

(Module (6,8) and (8,6) are skipped: they belong to the timing patterns.)

Copy 2 (split between the top-right and bottom-left finders):

| bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (row, col) | (8,size-1) | (8,size-2) | (8,size-3) | (8,size-4) | (8,size-5) | (8,size-6) | (8,size-7) | (8,size-8) | (size-7,8) | (size-6,8) | (size-5,8) | (size-4,8) | (size-3,8) | (size-2,8) | (size-1,8) |

Source: Nayuki `_draw_format_bits` (`set(8, i)` for bits 0-5 means x=8,y=i i.e. (row i, col 8)); zxing `BitMatrixParser.readFormatInformation` reads copy 1 MSB-first as (x=0..5,y=8), (7,8), (8,8), (8,7), (8,y=5..0) and copy 2 as (x=8, y=size-1..size-7) then (x=size-8..size-1, y=8) - identical mapping; zxing `MatrixUtil.TYPE_INFO_COORDINATES` likewise. CAUTION: Thonky's placement diagram numbers the bits 0..14 from the MSB, i.e. Thonky's "bit 0" is bit 14 here.

Decoder reading order for copy 1 (MSB first): (8,0),(8,1),(8,2),(8,3),(8,4),(8,5),(8,7),(8,8),(7,8),(5,8),(4,8),(3,8),(2,8),(1,8),(0,8). For copy 2 (MSB first): (size-1,8) up to (size-7,8), then (8,size-8) rightwards to (8,size-1).

---

## 7. Version information (V >= 7; 18 bits, two copies)

- 6 data bits = version number (7..40), followed by 12 BCH(18,6) check bits using generator `x^12 + x^11 + x^10 + x^9 + x^8 + x^5 + x^2 + 1` = `1111100100101` = **0x1F25**. No XOR mask.
  ```
  rem = V
  for _ in range(12): rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
  bits18 = (V << 12) | rem
  ```
- Minimum Hamming distance between valid version codewords is 8, so decoders correct up to 3 bit errors (zxing `decodeVersionInformation`).
- Placement (bit i = i-th least significant bit; Nayuki `_draw_version`, confirmed by zxing `readVersion` / `maybeEmbedVersionInfo` and Thonky's layout tables):
  - Top-right block, 6 rows x 3 cols: `(row = i // 3, col = size - 11 + i % 3)`. So bit 0 at (0, size-11), bit 1 at (0, size-10), bit 2 at (0, size-9), bit 3 at (1, size-11), ..., bit 17 at (5, size-9). It occupies rows 0-5, cols size-11..size-9 (immediately left of the top-right separator).
  - Bottom-left block, 3 rows x 6 cols: `(row = size - 11 + i % 3, col = i // 3)`. Bit 0 at (size-11, 0), bit 1 at (size-10, 0), bit 2 at (size-9, 0), bit 3 at (size-11, 1), ..., bit 17 at (size-9, 5). It occupies rows size-11..size-9, cols 0-5 (immediately above the bottom-left separator).
  - The two blocks are transposes of each other.
- Table D.1 - all version strings (verified identical to zxing `VERSION_DECODE_INFO` and segno `VERSION_INFO`):

| Version | 18-bit version string | Hex |
|---|---|---|
| 7 | 000111110010010100 | 0x07C94 |
| 8 | 001000010110111100 | 0x085BC |
| 9 | 001001101010011001 | 0x09A99 |
| 10 | 001010010011010011 | 0x0A4D3 |
| 11 | 001011101111110110 | 0x0BBF6 |
| 12 | 001100011101100010 | 0x0C762 |
| 13 | 001101100001000111 | 0x0D847 |
| 14 | 001110011000001101 | 0x0E60D |
| 15 | 001111100100101000 | 0x0F928 |
| 16 | 010000101101111000 | 0x10B78 |
| 17 | 010001010001011101 | 0x1145D |
| 18 | 010010101000010111 | 0x12A17 |
| 19 | 010011010100110010 | 0x13532 |
| 20 | 010100100110100110 | 0x149A6 |
| 21 | 010101011010000011 | 0x15683 |
| 22 | 010110100011001001 | 0x168C9 |
| 23 | 010111011111101100 | 0x177EC |
| 24 | 011000111011000100 | 0x18EC4 |
| 25 | 011001000111100001 | 0x191E1 |
| 26 | 011010111110101011 | 0x1AFAB |
| 27 | 011011000010001110 | 0x1B08E |
| 28 | 011100110000011010 | 0x1CC1A |
| 29 | 011101001100111111 | 0x1D33F |
| 30 | 011110110101110101 | 0x1ED75 |
| 31 | 011111001001010000 | 0x1F250 |
| 32 | 100000100111010101 | 0x209D5 |
| 33 | 100001011011110000 | 0x216F0 |
| 34 | 100010100010111010 | 0x228BA |
| 35 | 100011011110011111 | 0x2379F |
| 36 | 100100101100001011 | 0x24B0B |
| 37 | 100101010000101110 | 0x2542E |
| 38 | 100110101001100100 | 0x26A64 |
| 39 | 100111010101000001 | 0x27541 |
| 40 | 101000110001101001 | 0x28C69 |

- For V <= 6 there is no version information; decoders infer `V = (size - 17) / 4` from the measured dimension. For V >= 7, zxing still derives a provisional version from the dimension and only accepts the decoded version info if it matches that dimension.

---

## 8. Codeword placement (zig-zag)

Reference: ISO/IEC 18004 "Symbol character placement"; Nayuki `_draw_codewords`; zxing `MatrixUtil.embedDataBits` (encoder) and `BitMatrixParser.readCodewords` (decoder); Thonky "Module placement in matrix".

- The final bit stream (interleaved data codewords, then interleaved EC codewords, then remainder bits) is placed MSB first: bit 7 of codeword 0 is the first bit placed.
- Placement walks 2-module-wide vertical column pairs from the right edge to the left edge:
  ```
  i = 0                                   # bit index into the stream
  right = size - 1
  while right >= 1:
      if right == 6: right = 5            # skip the vertical timing pattern column entirely
      upward = ((right + 1) & 2) == 0     # equivalently: pairs alternate, first (rightmost) pair goes UP
      for vert in range(size):
          row = size - 1 - vert if upward else vert
          for col in (right, right - 1):  # right column first, then left column
              if not is_function(row, col):
                  if i < nbits: module[row][col] = bit(i); i += 1
                  # else: remainder bit, leave 0
      right -= 2
  ```
  Column pairs in order: (size-1,size-2) upward, (size-3,size-4) downward, ..., (8,7) upward, then (5,4) downward, (3,2) upward, (1,0) downward. Because `size-1` is a multiple of 4, the pair with right column `r` goes upward iff `r mod 4 == 0` for r >= 8, and the pairs (5,4),(3,2),(1,0) go down, up, down. Direction therefore simply alternates with every pair, including across the skipped column 6.
- Within a pair the two modules of each row are visited right then left, so a codeword in an unobstructed region occupies a 4-row x 2-col block, bits 7,6 on the first row (right, left), 5,4 on the next, etc.
- Function modules (finders, separators, timing, alignment, format, version, dark module) are skipped; the bit stream simply continues at the next non-function module. This is how codewords get "bent" around alignment patterns and split across the horizontal timing row.
- Remainder bits (0, 3, 4 or 7 of them - Table 1) are the last modules visited; they are filled with 0 (ISO 8.4.9 / JIS X 0510 8.4.9: pad with 0s) and then masked like data.
- Decoders use exactly the same walk to read `total codewords * 8` bits (after unmasking), and zxing checks that exactly `getTotalCodewords()` bytes were produced.
- Encoders typically fill the matrix with function patterns, RESERVE the format and version areas (and dark module) as function modules with dummy values before placement, then overwrite them with real format bits after mask selection (Nayuki, zxing).

---

## 9. Data masking

- Masking XORs the data region only: every module that is not a function module (function = finders, separators, timing, alignment, format info, version info, dark module). Remainder bits are masked too (they are data-region modules). Function patterns are NEVER masked.
- A module `(i = row, j = col)` is inverted iff the mask condition is true (ISO Table 10; Thonky "Mask patterns"; zxing `DataMask`; Nayuki `_MASK_PATTERNS` with x = col, y = row):

| Mask (3 bits) | Condition (invert when true) |
|---|---|
| 000 (0) | `(i + j) mod 2 == 0` |
| 001 (1) | `i mod 2 == 0` |
| 010 (2) | `j mod 3 == 0` |
| 011 (3) | `(i + j) mod 3 == 0` |
| 100 (4) | `(floor(i/2) + floor(j/3)) mod 2 == 0` |
| 101 (5) | `(i*j) mod 2 + (i*j) mod 3 == 0` |
| 110 (6) | `((i*j) mod 2 + (i*j) mod 3) mod 2 == 0` |
| 111 (7) | `((i + j) mod 2 + (i*j) mod 3) mod 2 == 0` |

- The chosen mask number is written into the format information. Decoders apply the same XOR to undo it (XOR is self-inverse).
- Mask selection (encoder only; not needed for decoding): try all 8, compute penalty, pick lowest. Penalty weights (ISO Table 11): N1 = 3, N2 = 3, N3 = 40, N4 = 10 (Nayuki `_PENALTY_N1..N4`, Thonky "Data masking"). Evaluated on the complete symbol (function patterns included, format bits present):
  1. Rule 1: for each row and each column, every run of >= 5 consecutive same-colour modules adds `N1 + (runLength - 5)`.
  2. Rule 2: every 2x2 block of same-colour modules adds N2 (overlapping blocks counted; an m x n block counts `(m-1)(n-1)` times).
  3. Rule 3: in rows and columns, each occurrence of the finder-like run pattern dark:light:dark:dark:dark:light:dark in ratio 1:1:3:1:1 that is preceded OR followed by >= 4 light modules adds N3. Implementations differ on edge handling and double counting: Nayuki treats the area outside the symbol as light and counts a pattern with light on both sides twice; Thonky counts each match of the 11-module pattern (`10111010000` or `00001011101`). This only affects which mask an encoder picks, never decodability.
  4. Rule 4: let `d` = dark modules / total modules in percent; `k = floor(|d - 50| / 5)`; add `N4 * k` (Thonky: take the two nearest multiples of 5, subtract 50, abs, divide by 5, take the smaller; Nayuki: smallest k with `(45-5k)% <= d <= (55+5k)%` - all equivalent).
- Any mask is valid for decoding regardless of its penalty; a decoder must support all 8.

---

## 10. Error correction (Reed-Solomon)

### 10.1 Field and generator
- Codewords are bytes = elements of GF(2^8) defined by the primitive polynomial `x^8 + x^4 + x^3 + x^2 + 1` = `100011101` = **0x11D** (285 decimal). Addition = XOR. Multiplication reduces modulo 0x11D (Nayuki `_reed_solomon_multiply`; python-qrcode `EXP_TABLE[i] = EXP[i-4]^EXP[i-5]^EXP[i-6]^EXP[i-8]`; Thonky "Error correction coding"; Wikipedia).
- Primitive element alpha = 2 (`0x02`), so `alpha^i` for i = 0..254 enumerates all non-zero elements; log/antilog tables with `exp[i+255] = exp[i]`.
- Generator polynomial for n EC codewords: `g(x) = (x - alpha^0)(x - alpha^1)...(x - alpha^(n-1))` - NOTE the roots start at `alpha^0 = 1`, not alpha^1 (Thonky; Nayuki `_reed_solomon_compute_divisor`). Degree n, monic.
- EC codewords for a block of k data codewords `d_0..d_{k-1}` (d_0 = first) are the n coefficients of the remainder of `D(x) * x^n` divided by `g(x)` where `D(x) = d_0 x^{k-1} + ... + d_{k-1}` (systematic encoding; polynomial long division in GF(256); the remainder's highest-degree coefficient is the first EC codeword). Sanity vector (Thonky "HELLO WORLD", 1-M): data `[32,91,11,120,209,114,220,77,67,64,236,17,236,17,236,17]` gives EC `[196,35,39,119,235,215,231,226,93,23]` (reproduced by the formulas above).
- Only 13 distinct block EC sizes occur in the standard: 7, 10, 13, 15, 16, 17, 18, 20, 22, 24, 26, 28, 30. Precomputed generators (coefficients from x^n down to x^0):

| EC codewords (degree) | Generator polynomial coefficients, high to low (integer form, leading 1 included) | Same, as exponents of alpha |
|---|---|---|
| 7 | 1, 127, 122, 154, 164, 11, 68, 117 | 0, 87, 229, 146, 149, 238, 102, 21 |
| 10 | 1, 216, 194, 159, 111, 199, 94, 95, 113, 157, 193 | 0, 251, 67, 46, 61, 118, 70, 64, 94, 32, 45 |
| 13 | 1, 137, 73, 227, 17, 177, 17, 52, 13, 46, 43, 83, 132, 120 | 0, 74, 152, 176, 100, 86, 100, 106, 104, 130, 218, 206, 140, 78 |
| 15 | 1, 29, 196, 111, 163, 112, 74, 10, 105, 105, 139, 132, 151, 32, 134, 26 | 0, 8, 183, 61, 91, 202, 37, 51, 58, 58, 237, 140, 124, 5, 99, 105 |
| 16 | 1, 59, 13, 104, 189, 68, 209, 30, 8, 163, 65, 41, 229, 98, 50, 36, 59 | 0, 120, 104, 107, 109, 102, 161, 76, 3, 91, 191, 147, 169, 182, 194, 225, 120 |
| 17 | 1, 119, 66, 83, 120, 119, 22, 197, 83, 249, 41, 143, 134, 85, 53, 125, 99, 79 | 0, 43, 139, 206, 78, 43, 239, 123, 206, 214, 147, 24, 99, 150, 39, 243, 163, 136 |
| 18 | 1, 239, 251, 183, 113, 149, 175, 199, 215, 240, 220, 73, 82, 173, 75, 32, 67, 217, 146 | 0, 215, 234, 158, 94, 184, 97, 118, 170, 79, 187, 152, 148, 252, 179, 5, 98, 96, 153 |
| 20 | 1, 152, 185, 240, 5, 111, 99, 6, 220, 112, 150, 69, 36, 187, 22, 228, 198, 121, 121, 165, 174 | 0, 17, 60, 79, 50, 61, 163, 26, 187, 202, 180, 221, 225, 83, 239, 156, 164, 212, 212, 188, 190 |
| 22 | 1, 89, 179, 131, 176, 182, 244, 19, 189, 69, 40, 28, 137, 29, 123, 67, 253, 86, 218, 230, 26, 145, 245 | 0, 210, 171, 247, 242, 93, 230, 14, 109, 221, 53, 200, 74, 8, 172, 98, 80, 219, 134, 160, 105, 165, 231 |
| 24 | 1, 122, 118, 169, 70, 178, 237, 216, 102, 115, 150, 229, 73, 130, 72, 61, 43, 206, 1, 237, 247, 127, 217, 144, 117 | 0, 229, 121, 135, 48, 211, 117, 251, 126, 159, 180, 169, 152, 192, 226, 228, 218, 111, 0, 117, 232, 87, 96, 227, 21 |
| 26 | 1, 246, 51, 183, 4, 136, 98, 199, 152, 77, 56, 206, 24, 145, 40, 209, 117, 233, 42, 135, 68, 70, 144, 146, 77, 43, 94 | 0, 173, 125, 158, 2, 103, 182, 118, 17, 145, 201, 111, 28, 165, 53, 161, 21, 245, 142, 13, 102, 48, 227, 153, 145, 218, 70 |
| 28 | 1, 252, 9, 28, 13, 18, 251, 208, 150, 103, 174, 100, 41, 167, 12, 247, 56, 117, 119, 233, 127, 181, 100, 121, 147, 176, 74, 58, 197 | 0, 168, 223, 200, 104, 224, 234, 108, 180, 110, 190, 195, 147, 205, 27, 232, 201, 21, 43, 245, 87, 42, 195, 212, 119, 242, 37, 9, 123 |
| 30 | 1, 212, 246, 77, 73, 195, 192, 75, 98, 5, 70, 103, 177, 22, 217, 138, 51, 181, 246, 72, 25, 18, 46, 228, 74, 216, 195, 11, 106, 130, 150 | 0, 41, 173, 145, 152, 216, 31, 179, 182, 50, 48, 110, 86, 239, 96, 222, 125, 42, 173, 226, 193, 224, 130, 156, 37, 251, 216, 238, 40, 192, 180 |

### 10.2 EC levels
| Level | Format bits | Nominal recovery capacity (of total codewords) |
|---|---|---|
| L | 01 | ~7 % |
| M | 00 | ~15 % |
| Q | 11 | ~25 % |
| H | 10 | ~30 % |

- Each block with n EC codewords can correct up to `floor((n - p) / 2)` erroneous codewords (errors at unknown positions) or `n - p` erasures (known positions), where `p` = misdecode-protection codewords. In ISO/IEC 18004 Table 9, p = 3 for 1-L, p = 2 for 1-M and 2-L, p = 1 for 1-Q, 1-H and 3-L, and p = 0 for all other version/level combinations (recalled from the standard; verify against your copy). Practical decoders such as zxing ignore p and attempt to correct up to `floor(n/2)` errors, relying on the RS decoder's failure detection.

### 10.3 Block structure
- Total codewords of a version are split into `numBlocks` RS blocks. All blocks of a (version, level) have the same number of EC codewords (`EC/block`). Data codewords per block differ by at most one: the first `group1` blocks are "short" (c data codewords), the remaining `group2` blocks have c + 1. Nayuki computes the split as `shortBlocks = numBlocks - totalCodewords mod numBlocks`, `shortLen = totalCodewords // numBlocks` (total per short block incl. EC), which reproduces ISO Table 9 exactly (verified against zxing and python-qrcode).
- Full ISO/IEC 18004 Table 9 (all 160 rows) with byte-mode capacity appended:

| Version | Level | Total codewords | Data codewords | EC codewords total | Blocks | EC/block | Group 1 (blocks x data cw) | Group 2 (blocks x data cw) | Max byte-mode chars |
|---|---|---|---|---|---|---|---|---|---|
| 1 | L | 26 | 19 | 7 | 1 | 7 | 1 x 19 | - | 17 |
| 1 | M | 26 | 16 | 10 | 1 | 10 | 1 x 16 | - | 14 |
| 1 | Q | 26 | 13 | 13 | 1 | 13 | 1 x 13 | - | 11 |
| 1 | H | 26 | 9 | 17 | 1 | 17 | 1 x 9 | - | 7 |
| 2 | L | 44 | 34 | 10 | 1 | 10 | 1 x 34 | - | 32 |
| 2 | M | 44 | 28 | 16 | 1 | 16 | 1 x 28 | - | 26 |
| 2 | Q | 44 | 22 | 22 | 1 | 22 | 1 x 22 | - | 20 |
| 2 | H | 44 | 16 | 28 | 1 | 28 | 1 x 16 | - | 14 |
| 3 | L | 70 | 55 | 15 | 1 | 15 | 1 x 55 | - | 53 |
| 3 | M | 70 | 44 | 26 | 1 | 26 | 1 x 44 | - | 42 |
| 3 | Q | 70 | 34 | 36 | 2 | 18 | 2 x 17 | - | 32 |
| 3 | H | 70 | 26 | 44 | 2 | 22 | 2 x 13 | - | 24 |
| 4 | L | 100 | 80 | 20 | 1 | 20 | 1 x 80 | - | 78 |
| 4 | M | 100 | 64 | 36 | 2 | 18 | 2 x 32 | - | 62 |
| 4 | Q | 100 | 48 | 52 | 2 | 26 | 2 x 24 | - | 46 |
| 4 | H | 100 | 36 | 64 | 4 | 16 | 4 x 9 | - | 34 |
| 5 | L | 134 | 108 | 26 | 1 | 26 | 1 x 108 | - | 106 |
| 5 | M | 134 | 86 | 48 | 2 | 24 | 2 x 43 | - | 84 |
| 5 | Q | 134 | 62 | 72 | 4 | 18 | 2 x 15 | 2 x 16 | 60 |
| 5 | H | 134 | 46 | 88 | 4 | 22 | 2 x 11 | 2 x 12 | 44 |
| 6 | L | 172 | 136 | 36 | 2 | 18 | 2 x 68 | - | 134 |
| 6 | M | 172 | 108 | 64 | 4 | 16 | 4 x 27 | - | 106 |
| 6 | Q | 172 | 76 | 96 | 4 | 24 | 4 x 19 | - | 74 |
| 6 | H | 172 | 60 | 112 | 4 | 28 | 4 x 15 | - | 58 |
| 7 | L | 196 | 156 | 40 | 2 | 20 | 2 x 78 | - | 154 |
| 7 | M | 196 | 124 | 72 | 4 | 18 | 4 x 31 | - | 122 |
| 7 | Q | 196 | 88 | 108 | 6 | 18 | 2 x 14 | 4 x 15 | 86 |
| 7 | H | 196 | 66 | 130 | 5 | 26 | 4 x 13 | 1 x 14 | 64 |
| 8 | L | 242 | 194 | 48 | 2 | 24 | 2 x 97 | - | 192 |
| 8 | M | 242 | 154 | 88 | 4 | 22 | 2 x 38 | 2 x 39 | 152 |
| 8 | Q | 242 | 110 | 132 | 6 | 22 | 4 x 18 | 2 x 19 | 108 |
| 8 | H | 242 | 86 | 156 | 6 | 26 | 4 x 14 | 2 x 15 | 84 |
| 9 | L | 292 | 232 | 60 | 2 | 30 | 2 x 116 | - | 230 |
| 9 | M | 292 | 182 | 110 | 5 | 22 | 3 x 36 | 2 x 37 | 180 |
| 9 | Q | 292 | 132 | 160 | 8 | 20 | 4 x 16 | 4 x 17 | 130 |
| 9 | H | 292 | 100 | 192 | 8 | 24 | 4 x 12 | 4 x 13 | 98 |
| 10 | L | 346 | 274 | 72 | 4 | 18 | 2 x 68 | 2 x 69 | 271 |
| 10 | M | 346 | 216 | 130 | 5 | 26 | 4 x 43 | 1 x 44 | 213 |
| 10 | Q | 346 | 154 | 192 | 8 | 24 | 6 x 19 | 2 x 20 | 151 |
| 10 | H | 346 | 122 | 224 | 8 | 28 | 6 x 15 | 2 x 16 | 119 |
| 11 | L | 404 | 324 | 80 | 4 | 20 | 4 x 81 | - | 321 |
| 11 | M | 404 | 254 | 150 | 5 | 30 | 1 x 50 | 4 x 51 | 251 |
| 11 | Q | 404 | 180 | 224 | 8 | 28 | 4 x 22 | 4 x 23 | 177 |
| 11 | H | 404 | 140 | 264 | 11 | 24 | 3 x 12 | 8 x 13 | 137 |
| 12 | L | 466 | 370 | 96 | 4 | 24 | 2 x 92 | 2 x 93 | 367 |
| 12 | M | 466 | 290 | 176 | 8 | 22 | 6 x 36 | 2 x 37 | 287 |
| 12 | Q | 466 | 206 | 260 | 10 | 26 | 4 x 20 | 6 x 21 | 203 |
| 12 | H | 466 | 158 | 308 | 11 | 28 | 7 x 14 | 4 x 15 | 155 |
| 13 | L | 532 | 428 | 104 | 4 | 26 | 4 x 107 | - | 425 |
| 13 | M | 532 | 334 | 198 | 9 | 22 | 8 x 37 | 1 x 38 | 331 |
| 13 | Q | 532 | 244 | 288 | 12 | 24 | 8 x 20 | 4 x 21 | 241 |
| 13 | H | 532 | 180 | 352 | 16 | 22 | 12 x 11 | 4 x 12 | 177 |
| 14 | L | 581 | 461 | 120 | 4 | 30 | 3 x 115 | 1 x 116 | 458 |
| 14 | M | 581 | 365 | 216 | 9 | 24 | 4 x 40 | 5 x 41 | 362 |
| 14 | Q | 581 | 261 | 320 | 16 | 20 | 11 x 16 | 5 x 17 | 258 |
| 14 | H | 581 | 197 | 384 | 16 | 24 | 11 x 12 | 5 x 13 | 194 |
| 15 | L | 655 | 523 | 132 | 6 | 22 | 5 x 87 | 1 x 88 | 520 |
| 15 | M | 655 | 415 | 240 | 10 | 24 | 5 x 41 | 5 x 42 | 412 |
| 15 | Q | 655 | 295 | 360 | 12 | 30 | 5 x 24 | 7 x 25 | 292 |
| 15 | H | 655 | 223 | 432 | 18 | 24 | 11 x 12 | 7 x 13 | 220 |
| 16 | L | 733 | 589 | 144 | 6 | 24 | 5 x 98 | 1 x 99 | 586 |
| 16 | M | 733 | 453 | 280 | 10 | 28 | 7 x 45 | 3 x 46 | 450 |
| 16 | Q | 733 | 325 | 408 | 17 | 24 | 15 x 19 | 2 x 20 | 322 |
| 16 | H | 733 | 253 | 480 | 16 | 30 | 3 x 15 | 13 x 16 | 250 |
| 17 | L | 815 | 647 | 168 | 6 | 28 | 1 x 107 | 5 x 108 | 644 |
| 17 | M | 815 | 507 | 308 | 11 | 28 | 10 x 46 | 1 x 47 | 504 |
| 17 | Q | 815 | 367 | 448 | 16 | 28 | 1 x 22 | 15 x 23 | 364 |
| 17 | H | 815 | 283 | 532 | 19 | 28 | 2 x 14 | 17 x 15 | 280 |
| 18 | L | 901 | 721 | 180 | 6 | 30 | 5 x 120 | 1 x 121 | 718 |
| 18 | M | 901 | 563 | 338 | 13 | 26 | 9 x 43 | 4 x 44 | 560 |
| 18 | Q | 901 | 397 | 504 | 18 | 28 | 17 x 22 | 1 x 23 | 394 |
| 18 | H | 901 | 313 | 588 | 21 | 28 | 2 x 14 | 19 x 15 | 310 |
| 19 | L | 991 | 795 | 196 | 7 | 28 | 3 x 113 | 4 x 114 | 792 |
| 19 | M | 991 | 627 | 364 | 14 | 26 | 3 x 44 | 11 x 45 | 624 |
| 19 | Q | 991 | 445 | 546 | 21 | 26 | 17 x 21 | 4 x 22 | 442 |
| 19 | H | 991 | 341 | 650 | 25 | 26 | 9 x 13 | 16 x 14 | 338 |
| 20 | L | 1085 | 861 | 224 | 8 | 28 | 3 x 107 | 5 x 108 | 858 |
| 20 | M | 1085 | 669 | 416 | 16 | 26 | 3 x 41 | 13 x 42 | 666 |
| 20 | Q | 1085 | 485 | 600 | 20 | 30 | 15 x 24 | 5 x 25 | 482 |
| 20 | H | 1085 | 385 | 700 | 25 | 28 | 15 x 15 | 10 x 16 | 382 |
| 21 | L | 1156 | 932 | 224 | 8 | 28 | 4 x 116 | 4 x 117 | 929 |
| 21 | M | 1156 | 714 | 442 | 17 | 26 | 17 x 42 | - | 711 |
| 21 | Q | 1156 | 512 | 644 | 23 | 28 | 17 x 22 | 6 x 23 | 509 |
| 21 | H | 1156 | 406 | 750 | 25 | 30 | 19 x 16 | 6 x 17 | 403 |
| 22 | L | 1258 | 1006 | 252 | 9 | 28 | 2 x 111 | 7 x 112 | 1003 |
| 22 | M | 1258 | 782 | 476 | 17 | 28 | 17 x 46 | - | 779 |
| 22 | Q | 1258 | 568 | 690 | 23 | 30 | 7 x 24 | 16 x 25 | 565 |
| 22 | H | 1258 | 442 | 816 | 34 | 24 | 34 x 13 | - | 439 |
| 23 | L | 1364 | 1094 | 270 | 9 | 30 | 4 x 121 | 5 x 122 | 1091 |
| 23 | M | 1364 | 860 | 504 | 18 | 28 | 4 x 47 | 14 x 48 | 857 |
| 23 | Q | 1364 | 614 | 750 | 25 | 30 | 11 x 24 | 14 x 25 | 611 |
| 23 | H | 1364 | 464 | 900 | 30 | 30 | 16 x 15 | 14 x 16 | 461 |
| 24 | L | 1474 | 1174 | 300 | 10 | 30 | 6 x 117 | 4 x 118 | 1171 |
| 24 | M | 1474 | 914 | 560 | 20 | 28 | 6 x 45 | 14 x 46 | 911 |
| 24 | Q | 1474 | 664 | 810 | 27 | 30 | 11 x 24 | 16 x 25 | 661 |
| 24 | H | 1474 | 514 | 960 | 32 | 30 | 30 x 16 | 2 x 17 | 511 |
| 25 | L | 1588 | 1276 | 312 | 12 | 26 | 8 x 106 | 4 x 107 | 1273 |
| 25 | M | 1588 | 1000 | 588 | 21 | 28 | 8 x 47 | 13 x 48 | 997 |
| 25 | Q | 1588 | 718 | 870 | 29 | 30 | 7 x 24 | 22 x 25 | 715 |
| 25 | H | 1588 | 538 | 1050 | 35 | 30 | 22 x 15 | 13 x 16 | 535 |
| 26 | L | 1706 | 1370 | 336 | 12 | 28 | 10 x 114 | 2 x 115 | 1367 |
| 26 | M | 1706 | 1062 | 644 | 23 | 28 | 19 x 46 | 4 x 47 | 1059 |
| 26 | Q | 1706 | 754 | 952 | 34 | 28 | 28 x 22 | 6 x 23 | 751 |
| 26 | H | 1706 | 596 | 1110 | 37 | 30 | 33 x 16 | 4 x 17 | 593 |
| 27 | L | 1828 | 1468 | 360 | 12 | 30 | 8 x 122 | 4 x 123 | 1465 |
| 27 | M | 1828 | 1128 | 700 | 25 | 28 | 22 x 45 | 3 x 46 | 1125 |
| 27 | Q | 1828 | 808 | 1020 | 34 | 30 | 8 x 23 | 26 x 24 | 805 |
| 27 | H | 1828 | 628 | 1200 | 40 | 30 | 12 x 15 | 28 x 16 | 625 |
| 28 | L | 1921 | 1531 | 390 | 13 | 30 | 3 x 117 | 10 x 118 | 1528 |
| 28 | M | 1921 | 1193 | 728 | 26 | 28 | 3 x 45 | 23 x 46 | 1190 |
| 28 | Q | 1921 | 871 | 1050 | 35 | 30 | 4 x 24 | 31 x 25 | 868 |
| 28 | H | 1921 | 661 | 1260 | 42 | 30 | 11 x 15 | 31 x 16 | 658 |
| 29 | L | 2051 | 1631 | 420 | 14 | 30 | 7 x 116 | 7 x 117 | 1628 |
| 29 | M | 2051 | 1267 | 784 | 28 | 28 | 21 x 45 | 7 x 46 | 1264 |
| 29 | Q | 2051 | 911 | 1140 | 38 | 30 | 1 x 23 | 37 x 24 | 908 |
| 29 | H | 2051 | 701 | 1350 | 45 | 30 | 19 x 15 | 26 x 16 | 698 |
| 30 | L | 2185 | 1735 | 450 | 15 | 30 | 5 x 115 | 10 x 116 | 1732 |
| 30 | M | 2185 | 1373 | 812 | 29 | 28 | 19 x 47 | 10 x 48 | 1370 |
| 30 | Q | 2185 | 985 | 1200 | 40 | 30 | 15 x 24 | 25 x 25 | 982 |
| 30 | H | 2185 | 745 | 1440 | 48 | 30 | 23 x 15 | 25 x 16 | 742 |
| 31 | L | 2323 | 1843 | 480 | 16 | 30 | 13 x 115 | 3 x 116 | 1840 |
| 31 | M | 2323 | 1455 | 868 | 31 | 28 | 2 x 46 | 29 x 47 | 1452 |
| 31 | Q | 2323 | 1033 | 1290 | 43 | 30 | 42 x 24 | 1 x 25 | 1030 |
| 31 | H | 2323 | 793 | 1530 | 51 | 30 | 23 x 15 | 28 x 16 | 790 |
| 32 | L | 2465 | 1955 | 510 | 17 | 30 | 17 x 115 | - | 1952 |
| 32 | M | 2465 | 1541 | 924 | 33 | 28 | 10 x 46 | 23 x 47 | 1538 |
| 32 | Q | 2465 | 1115 | 1350 | 45 | 30 | 10 x 24 | 35 x 25 | 1112 |
| 32 | H | 2465 | 845 | 1620 | 54 | 30 | 19 x 15 | 35 x 16 | 842 |
| 33 | L | 2611 | 2071 | 540 | 18 | 30 | 17 x 115 | 1 x 116 | 2068 |
| 33 | M | 2611 | 1631 | 980 | 35 | 28 | 14 x 46 | 21 x 47 | 1628 |
| 33 | Q | 2611 | 1171 | 1440 | 48 | 30 | 29 x 24 | 19 x 25 | 1168 |
| 33 | H | 2611 | 901 | 1710 | 57 | 30 | 11 x 15 | 46 x 16 | 898 |
| 34 | L | 2761 | 2191 | 570 | 19 | 30 | 13 x 115 | 6 x 116 | 2188 |
| 34 | M | 2761 | 1725 | 1036 | 37 | 28 | 14 x 46 | 23 x 47 | 1722 |
| 34 | Q | 2761 | 1231 | 1530 | 51 | 30 | 44 x 24 | 7 x 25 | 1228 |
| 34 | H | 2761 | 961 | 1800 | 60 | 30 | 59 x 16 | 1 x 17 | 958 |
| 35 | L | 2876 | 2306 | 570 | 19 | 30 | 12 x 121 | 7 x 122 | 2303 |
| 35 | M | 2876 | 1812 | 1064 | 38 | 28 | 12 x 47 | 26 x 48 | 1809 |
| 35 | Q | 2876 | 1286 | 1590 | 53 | 30 | 39 x 24 | 14 x 25 | 1283 |
| 35 | H | 2876 | 986 | 1890 | 63 | 30 | 22 x 15 | 41 x 16 | 983 |
| 36 | L | 3034 | 2434 | 600 | 20 | 30 | 6 x 121 | 14 x 122 | 2431 |
| 36 | M | 3034 | 1914 | 1120 | 40 | 28 | 6 x 47 | 34 x 48 | 1911 |
| 36 | Q | 3034 | 1354 | 1680 | 56 | 30 | 46 x 24 | 10 x 25 | 1351 |
| 36 | H | 3034 | 1054 | 1980 | 66 | 30 | 2 x 15 | 64 x 16 | 1051 |
| 37 | L | 3196 | 2566 | 630 | 21 | 30 | 17 x 122 | 4 x 123 | 2563 |
| 37 | M | 3196 | 1992 | 1204 | 43 | 28 | 29 x 46 | 14 x 47 | 1989 |
| 37 | Q | 3196 | 1426 | 1770 | 59 | 30 | 49 x 24 | 10 x 25 | 1423 |
| 37 | H | 3196 | 1096 | 2100 | 70 | 30 | 24 x 15 | 46 x 16 | 1093 |
| 38 | L | 3362 | 2702 | 660 | 22 | 30 | 4 x 122 | 18 x 123 | 2699 |
| 38 | M | 3362 | 2102 | 1260 | 45 | 28 | 13 x 46 | 32 x 47 | 2099 |
| 38 | Q | 3362 | 1502 | 1860 | 62 | 30 | 48 x 24 | 14 x 25 | 1499 |
| 38 | H | 3362 | 1142 | 2220 | 74 | 30 | 42 x 15 | 32 x 16 | 1139 |
| 39 | L | 3532 | 2812 | 720 | 24 | 30 | 20 x 117 | 4 x 118 | 2809 |
| 39 | M | 3532 | 2216 | 1316 | 47 | 28 | 40 x 47 | 7 x 48 | 2213 |
| 39 | Q | 3532 | 1582 | 1950 | 65 | 30 | 43 x 24 | 22 x 25 | 1579 |
| 39 | H | 3532 | 1222 | 2310 | 77 | 30 | 10 x 15 | 67 x 16 | 1219 |
| 40 | L | 3706 | 2956 | 750 | 25 | 30 | 19 x 118 | 6 x 119 | 2953 |
| 40 | M | 3706 | 2334 | 1372 | 49 | 28 | 18 x 47 | 31 x 48 | 2331 |
| 40 | Q | 3706 | 1666 | 2040 | 68 | 30 | 34 x 24 | 34 x 25 | 1663 |
| 40 | H | 3706 | 1276 | 2430 | 81 | 30 | 20 x 15 | 61 x 16 | 1273 |

### 10.4 Interleaving (ISO "Constructing the final message sequence"; Thonky "Structure final message"; Nayuki `_add_ecc_and_interleave`)
1. Split the data codeword sequence into blocks in order: group-1 blocks first (each c codewords), then group-2 blocks (each c+1).
2. Compute EC codewords for every block independently.
3. Final sequence = data codewords interleaved: `D1_1, D2_1, ..., Dn_1, D1_2, D2_2, ..., Dn_2, ...` (codeword 1 of every block, then codeword 2 of every block, ...). When the short blocks run out (after c rounds), the (c+1)-th codewords of the group-2 blocks only are appended, in block order.
4. Followed by EC codewords interleaved the same way: `E1_1, E2_1, ..., En_1, E1_2, ...` (all EC blocks have equal length, so no ragged tail).
5. Followed by the remainder bits (zeros).
- Decoders reverse this: distribute the first `totalData` codewords of the read stream round-robin to blocks (respecting the ragged tail), then the EC codewords round-robin, RS-decode each block, then concatenate the corrected data codewords in block order.

---

## 11. Data encoding (bit stream)

### 11.1 Segment structure
`[mode indicator (4 bits)] [character count indicator (CCI)] [data bits]`, repeated for each segment, then `[terminator]` `[0-pad to byte boundary]` `[pad codewords]`.

| Mode | Indicator | Notes |
|---|---|---|
| ECI | 0111 | followed by ECI assignment number: 8 bits `0xxxxxxx` (0-127), 16 bits `10xxxxxx xxxxxxxx` (128-16383), or 24 bits `110xxxxx ...` (16384-999999); no CCI (Nayuki `make_eci`) |
| Numeric | 0001 | digits 0-9 |
| Alphanumeric | 0010 | 45-char set |
| Byte | 0100 | 8 bits per byte; default interpretation ISO-8859-1 (ECI 3); UTF-8 is ECI 26 and is what most decoders assume today when no ECI is present and the data is valid UTF-8 |
| Kanji | 1000 | Shift JIS double-byte characters, 13 bits each |
| Structured Append | 0011 | followed by 4-bit symbol index (0-15), 4-bit total-1 (0-15), 8-bit parity (XOR of all data bytes); no CCI |
| FNC1 (first position) | 0101 | GS1 formatting; no CCI |
| FNC1 (second position) | 1001 | followed by 8-bit application indicator; no CCI |
| Terminator | 0000 | may be truncated (fewer than 4 bits) if the capacity is reached; omitted entirely if the data exactly fills the capacity |

(Mode indicators per Wikipedia and segno `MODE_*`; Thonky "Data encoding".)

### 11.2 Character count indicator lengths (ISO Table 3; Thonky; Nayuki `Mode(..., (a, b, c))`)

| Mode | V1-9 | V10-26 | V27-40 |
|---|---|---|---|
| Numeric | 10 | 12 | 14 |
| Alphanumeric | 9 | 11 | 13 |
| Byte | 8 | 16 | 16 |
| Kanji | 8 | 10 | 12 |

Nayuki's compact index: `group = (V + 7) // 17` gives 0, 1, 2 for the three ranges.

### 11.3 Mode data bit rules
- Numeric: split digits into groups of 3; each 3-digit group -> 10 bits (value 0-999); a trailing 2-digit group -> 7 bits; a trailing 1-digit group -> 4 bits. Total bits = `10*floor(n/3) + {0, 4, 7}[n mod 3]`.
- Alphanumeric: character values `0-9 -> 0-9`, `A-Z -> 10-35`, space 36, `$` 37, `%` 38, `*` 39, `+` 40, `-` 41, `.` 42, `/` 43, `:` 44 (table order `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:`). Pairs -> 11 bits (`45*first + second`); a trailing single character -> 6 bits. Total bits = `11*floor(n/2) + 6*(n mod 2)`.
- Byte: 8 bits per byte, CCI counts bytes (not characters).
- Kanji (Thonky "Kanji mode encoding"): for Shift JIS code `c`: if `0x8140 <= c <= 0x9FFC` subtract `0x8140`; if `0xE040 <= c <= 0xEBBF` subtract `0xC140`; then `value = (hi_byte * 0xC0) + lo_byte`, emit 13 bits. CCI counts characters.
- Terminator `0000` (truncated to fit), then zero bits to the next byte boundary, then alternating pad codewords **0xEC (11101100)** and **0x11 (00010001)** until the data-codeword count of the chosen version/level is reached.
- Total data bits available = `dataCodewords * 8` (segno `SYMBOL_CAPACITY`, Table 7 of ISO; equals `8 * Data codewords` in Table 9 above).

### 11.4 Character capacities (ISO Table 7) - all versions, all levels
Capacity for a single segment of one mode = `floor` of what fits in `dataBits - 4 - CCI` by the rules in 11.3 (for numeric: `3*floor(b/10) + (b mod 10 >= 7 ? 2 : b mod 10 >= 4 ? 1 : 0)`; alphanumeric: `2*floor(b/11) + (b mod 11 >= 6 ? 1 : 0)`; byte: `floor(b/8)`; kanji: `floor(b/13)`). Computed values match Thonky's table in all 160 x 4 cells. Maximum (40-L): 7089 numeric / 4296 alphanumeric / 2953 byte / 1817 kanji (Wikipedia).

Format of each cell: Numeric / Alphanumeric / Byte / Kanji.

| Version | L: Num / Alnum / Byte / Kanji | M: Num / Alnum / Byte / Kanji | Q: Num / Alnum / Byte / Kanji | H: Num / Alnum / Byte / Kanji |
|---|---|---|---|---|
| 1 | 41 / 25 / 17 / 10 | 34 / 20 / 14 / 8 | 27 / 16 / 11 / 7 | 17 / 10 / 7 / 4 |
| 2 | 77 / 47 / 32 / 20 | 63 / 38 / 26 / 16 | 48 / 29 / 20 / 12 | 34 / 20 / 14 / 8 |
| 3 | 127 / 77 / 53 / 32 | 101 / 61 / 42 / 26 | 77 / 47 / 32 / 20 | 58 / 35 / 24 / 15 |
| 4 | 187 / 114 / 78 / 48 | 149 / 90 / 62 / 38 | 111 / 67 / 46 / 28 | 82 / 50 / 34 / 21 |
| 5 | 255 / 154 / 106 / 65 | 202 / 122 / 84 / 52 | 144 / 87 / 60 / 37 | 106 / 64 / 44 / 27 |
| 6 | 322 / 195 / 134 / 82 | 255 / 154 / 106 / 65 | 178 / 108 / 74 / 45 | 139 / 84 / 58 / 36 |
| 7 | 370 / 224 / 154 / 95 | 293 / 178 / 122 / 75 | 207 / 125 / 86 / 53 | 154 / 93 / 64 / 39 |
| 8 | 461 / 279 / 192 / 118 | 365 / 221 / 152 / 93 | 259 / 157 / 108 / 66 | 202 / 122 / 84 / 52 |
| 9 | 552 / 335 / 230 / 141 | 432 / 262 / 180 / 111 | 312 / 189 / 130 / 80 | 235 / 143 / 98 / 60 |
| 10 | 652 / 395 / 271 / 167 | 513 / 311 / 213 / 131 | 364 / 221 / 151 / 93 | 288 / 174 / 119 / 74 |
| 11 | 772 / 468 / 321 / 198 | 604 / 366 / 251 / 155 | 427 / 259 / 177 / 109 | 331 / 200 / 137 / 85 |
| 12 | 883 / 535 / 367 / 226 | 691 / 419 / 287 / 177 | 489 / 296 / 203 / 125 | 374 / 227 / 155 / 96 |
| 13 | 1022 / 619 / 425 / 262 | 796 / 483 / 331 / 204 | 580 / 352 / 241 / 149 | 427 / 259 / 177 / 109 |
| 14 | 1101 / 667 / 458 / 282 | 871 / 528 / 362 / 223 | 621 / 376 / 258 / 159 | 468 / 283 / 194 / 120 |
| 15 | 1250 / 758 / 520 / 320 | 991 / 600 / 412 / 254 | 703 / 426 / 292 / 180 | 530 / 321 / 220 / 136 |
| 16 | 1408 / 854 / 586 / 361 | 1082 / 656 / 450 / 277 | 775 / 470 / 322 / 198 | 602 / 365 / 250 / 154 |
| 17 | 1548 / 938 / 644 / 397 | 1212 / 734 / 504 / 310 | 876 / 531 / 364 / 224 | 674 / 408 / 280 / 173 |
| 18 | 1725 / 1046 / 718 / 442 | 1346 / 816 / 560 / 345 | 948 / 574 / 394 / 243 | 746 / 452 / 310 / 191 |
| 19 | 1903 / 1153 / 792 / 488 | 1500 / 909 / 624 / 384 | 1063 / 644 / 442 / 272 | 813 / 493 / 338 / 208 |
| 20 | 2061 / 1249 / 858 / 528 | 1600 / 970 / 666 / 410 | 1159 / 702 / 482 / 297 | 919 / 557 / 382 / 235 |
| 21 | 2232 / 1352 / 929 / 572 | 1708 / 1035 / 711 / 438 | 1224 / 742 / 509 / 314 | 969 / 587 / 403 / 248 |
| 22 | 2409 / 1460 / 1003 / 618 | 1872 / 1134 / 779 / 480 | 1358 / 823 / 565 / 348 | 1056 / 640 / 439 / 270 |
| 23 | 2620 / 1588 / 1091 / 672 | 2059 / 1248 / 857 / 528 | 1468 / 890 / 611 / 376 | 1108 / 672 / 461 / 284 |
| 24 | 2812 / 1704 / 1171 / 721 | 2188 / 1326 / 911 / 561 | 1588 / 963 / 661 / 407 | 1228 / 744 / 511 / 315 |
| 25 | 3057 / 1853 / 1273 / 784 | 2395 / 1451 / 997 / 614 | 1718 / 1041 / 715 / 440 | 1286 / 779 / 535 / 330 |
| 26 | 3283 / 1990 / 1367 / 842 | 2544 / 1542 / 1059 / 652 | 1804 / 1094 / 751 / 462 | 1425 / 864 / 593 / 365 |
| 27 | 3517 / 2132 / 1465 / 902 | 2701 / 1637 / 1125 / 692 | 1933 / 1172 / 805 / 496 | 1501 / 910 / 625 / 385 |
| 28 | 3669 / 2223 / 1528 / 940 | 2857 / 1732 / 1190 / 732 | 2085 / 1263 / 868 / 534 | 1581 / 958 / 658 / 405 |
| 29 | 3909 / 2369 / 1628 / 1002 | 3035 / 1839 / 1264 / 778 | 2181 / 1322 / 908 / 559 | 1677 / 1016 / 698 / 430 |
| 30 | 4158 / 2520 / 1732 / 1066 | 3289 / 1994 / 1370 / 843 | 2358 / 1429 / 982 / 604 | 1782 / 1080 / 742 / 457 |
| 31 | 4417 / 2677 / 1840 / 1132 | 3486 / 2113 / 1452 / 894 | 2473 / 1499 / 1030 / 634 | 1897 / 1150 / 790 / 486 |
| 32 | 4686 / 2840 / 1952 / 1201 | 3693 / 2238 / 1538 / 947 | 2670 / 1618 / 1112 / 684 | 2022 / 1226 / 842 / 518 |
| 33 | 4965 / 3009 / 2068 / 1273 | 3909 / 2369 / 1628 / 1002 | 2805 / 1700 / 1168 / 719 | 2157 / 1307 / 898 / 553 |
| 34 | 5253 / 3183 / 2188 / 1347 | 4134 / 2506 / 1722 / 1060 | 2949 / 1787 / 1228 / 756 | 2301 / 1394 / 958 / 590 |
| 35 | 5529 / 3351 / 2303 / 1417 | 4343 / 2632 / 1809 / 1113 | 3081 / 1867 / 1283 / 790 | 2361 / 1431 / 983 / 605 |
| 36 | 5836 / 3537 / 2431 / 1496 | 4588 / 2780 / 1911 / 1176 | 3244 / 1966 / 1351 / 832 | 2524 / 1530 / 1051 / 647 |
| 37 | 6153 / 3729 / 2563 / 1577 | 4775 / 2894 / 1989 / 1224 | 3417 / 2071 / 1423 / 876 | 2625 / 1591 / 1093 / 673 |
| 38 | 6479 / 3927 / 2699 / 1661 | 5039 / 3054 / 2099 / 1292 | 3599 / 2181 / 1499 / 923 | 2735 / 1658 / 1139 / 701 |
| 39 | 6743 / 4087 / 2809 / 1729 | 5313 / 3220 / 2213 / 1362 | 3791 / 2298 / 1579 / 972 | 2927 / 1774 / 1219 / 750 |
| 40 | 7089 / 4296 / 2953 / 1817 | 5596 / 3391 / 2331 / 1435 | 3993 / 2420 / 1663 / 1024 | 3057 / 1852 / 1273 / 784 |

---

## 12. Decoding pipeline (zxing / OpenCV practice)

### 12.1 Binarisation
- zxing: `GlobalHistogramBinarizer` (one threshold from the luminance histogram) or `HybridBinarizer` (8x8 block local thresholds, 5x5 block neighbourhood averaging) producing a 1-bit `BitMatrix`.
- OpenCV `QRCodeDetector`: `adaptiveThreshold(gray, 255, ADAPTIVE_THRESH_GAUSSIAN_C, THRESH_BINARY, blockSize=83, C=2)`.

### 12.2 Finder pattern detection (zxing `FinderPatternFinder`)
- Scan rows (initial row skip `iSkip = 3*height/(4*97)`, min 3 = `MIN_SKIP`; drops to 2 once a centre is confirmed; `MAX_MODULES = 97` i.e. up to V20 assumed for the skip heuristic). Maintain a 5-element run-length state `[dark, light, dark, light, dark]`.
- `foundPatternCross(stateCount)`: all 5 counts > 0, total >= 7, `moduleSize = total / 7`, `maxVariance = moduleSize / 2`; accept iff `|moduleSize - s[k]| < maxVariance` for k = 0,1,3,4 and `|3*moduleSize - s[2]| < 3*maxVariance` (i.e. < 50 % deviation from 1:1:3:1:1). Diagonal check uses a looser `moduleSize / 1.333`.
- Centre of a run: `centerFromEnd = end - s[4] - s[3] - s[2]/2`.
- Candidate confirmation: `crossCheckVertical` through the horizontal centre, then `crossCheckHorizontal` through the refined vertical centre, then `crossCheckDiagonal`; each must again satisfy the 1:1:3:1:1 test, and the total run length must stay within 40 % (vertical) / 20 % (horizontal) of the original horizontal total (`5*|total - original| >= 2*original` resp. `>= original` rejects elongated blobs). Repeated detections of the same centre (`FinderPattern.aboutEquals`: within one module size in x and y, and module-size difference <= 1 px or <= the existing estimate) are merged with a running average; a centre needs `CENTER_QUORUM = 2` confirmations. The alignment-pattern finder uses the same scheme with a 3-run 1:1:1 test (`AlignmentPatternFinder.foundPatternCross`, each run within `moduleSize/2` of the known module size).
- `selectBestPatterns`: among confirmed centres choose the triple whose module sizes are within 1.4x of each other and whose squared pairwise distances `a <= b <= c` minimise `|c - 2b| + |c - 2a|` (closest to an isosceles right triangle).
- Order the three as top-left / top-right / bottom-left (`ResultPoint.orderBestPatterns`): the point opposite the longest side is top-left; the sign of the cross product of (TL->BL) x (TL->TR) decides which of the remaining two is BL vs TR (handles mirrored images by later attempting a transposed decode).

### 12.3 Module size, dimension, version (zxing `Detector`)
- `calculateModuleSize`: along the line TL->TR and TL->BL (and the reverse directions), count the pixel length of the dark-light-dark run through the finder centre (`sizeOfBlackWhiteBlackRunBothWays`, which spans 3+1+1+1+1 = 7 modules); `moduleSize = (est1 + est2) / 14`, then average both axes. Reject if `moduleSize < 1` pixel.
- `computeDimension`: `d = round(dist(TL,TR)/moduleSize)`, `e = round(dist(TL,BL)/moduleSize)`; `dimension = (d + e)/2 + 7` (centres are 7 modules in from the edge on each side: `size - 7` apart). Force `dimension mod 4 == 1`: `+1` if `mod 4 == 0`, `-1` if `== 2`, `-2` if `== 3`. Provisional version `V = (dimension - 17) / 4`.
- OpenCV `QRDecode::versionDefinition`: counts dark/light transitions along the timing patterns between the finder patterns to estimate the module count, cross-checks with module count from finder-pattern side length, and for V >= 7 reads the 18-bit version info from both locations choosing the nearest valid codeword by Hamming distance.

### 12.4 Fourth corner / alignment pattern
- Estimated bottom-right finder position `BR = TR - TL + BL` (parallelogram).
- For V >= 2, the bottom-right alignment pattern centre is 3 modules inside BR along the diagonal: `estAlign = TL + (1 - 3/(dimension - 7)) * (BR - TL)` (`correctionToTopLeft`). Search with `AlignmentPatternFinder` (a 1:1:1 dark:light:dark run test with `moduleSize` tolerance) in a square region of half-width `allowance` = 4, then 8, then 16 module sizes (`findAlignmentInRegion`). If none is found, continue without it.
- OpenCV instead computes the fourth corner geometrically as the intersection of the two outer edges of the convex hull passing through the TR and BL finders (`computeTransformationPoints` / `getQuadrilateral`), after ordering the three finder clusters (k-means, k=3) by checking the right angle (rejecting triangles with `|cos| > 0.85`).

### 12.5 Perspective transform and sampling (zxing `createTransform`, `sampleGrid`)
- Module-space source points (module centres; finder centre is at 3.5,3.5): `(3.5, 3.5)`, `(dimension-3.5, 3.5)`, `(3.5, dimension-3.5)` map to the TL, TR, BL finder centres in image space. The fourth source point is `(dimension-6.5, dimension-6.5)` mapped to the alignment pattern centre when found, else `(dimension-3.5, dimension-3.5)` mapped to the estimated BR.
- `PerspectiveTransform.quadrilateralToQuadrilateral` (8-DOF homography); `GridSampler.sampleGrid` evaluates the transform at `(x + 0.5, y + 0.5)` for every module and samples the binary image, producing a `dimension x dimension` BitMatrix. OpenCV warps to a square of at least 251 px (`warpPerspective`, `INTER_NEAREST`) with a 10 % border, then samples each module cell.

### 12.6 Symbol decoding (zxing `Decoder`, `BitMatrixParser`)
1. Read both format-info copies (section 6.3), decode with <= 3 bit-error tolerance; if both fail, retry with the 0x5412 mask not applied; if still failing, try the mirrored (transposed) matrix (`QRCodeReader` / `Decoder.decode` mirror fallback).
2. Determine version: from dimension if `V <= 6`, else read version bits top-right, falling back to bottom-left; the decoded version must match the dimension.
3. Build the function-pattern mask for this version (`Version.buildFunctionPattern`: 9x9 TL, 8x9 TR, 9x8 BL corner blocks incl. format strips, 5x5 alignment blocks, timing lines, 3x6/6x3 version blocks for V >= 7).
4. Unmask the data region with the mask from the format info (`DataMask.unmaskBitMatrix` - applied to the entire matrix in zxing, which is harmless because function modules are skipped on read).
5. Read codewords with the zig-zag walk (section 8), MSB first, until `totalCodewords` bytes.
6. De-interleave into blocks (`DataBlock.getDataBlocks`), RS-decode each (`ReedSolomonDecoder` with `GenericGF.QR_CODE_FIELD_256` = 0x11D, generator base 0), concatenate the data codewords, parse segments (`DecodedBitStreamParser`), stopping at the terminator or when fewer than 4 bits remain.
7. Report the result with the (3 or 4) result points; zxing exposes ECI/charset handling and Structured Append metadata.

---

## 13. Quiet zone and physical sizing

- Quiet zone: ISO/IEC 18004 requires a light margin of at least **4 modules** on all four sides of a QR Code Model 2 symbol (2 modules for Micro QR). Many phone decoders tolerate less, but detectors that measure module size along the finder-pattern line or compute the outer edges (OpenCV) degrade quickly when the margin is below 1-2 modules; always emit 4 (Thonky, Wikipedia; segno `TYPE_QUIET_ZONE`, default border 4 in python-qrcode / segno / Nayuki examples).
- Module (cell) size for printing (Denso Wave, https://www.qrcode.com/en/howto/cell.html): print each module as >= 4 printer dots for stability; that gives minimum module sizes of ~0.17 mm at 600 dpi, ~0.33 mm at 300 dpi, ~0.5 mm at 200 dpi. The reader's optical resolution must be finer than the module size (industrial readers: 0.1-0.25 mm per module). Print as large as the available area permits.
- Common field guidance (Scanova, Delivr, QR size guides linked from the search above): minimum symbol size for smartphone scanning about 10 mm (recommended >= 12 mm, or 20 x 20 mm for general use) excluding the quiet zone; symbol width >= 1/10 of the intended scanning distance; module size >= 0.25 mm absolute minimum for ISO-conformant print, with ~0.5 mm being a safe floor for consumer cameras. Lower versions (fewer modules) at the same physical size scan more reliably; prefer increasing physical size over EC level when space allows.
- Contrast: dark modules on a light background; inverted (light-on-dark) symbols are not conformant to ISO 18004 Model 2 (decoders such as zxing only read them via an explicit inverted attempt), and reflectance difference should be high (ISO/IEC 15415 print-quality grading).
