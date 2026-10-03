# Prior art: colored / high-capacity 2D barcodes (with emphasis on colored QR codes)

Research memo compiled 2026-10-03 from web sources. Every factual claim carries a source link; where a
primary source could not be fetched (paywall, 403, broken certificate) the claim is marked **[unverified]**
and should not be relied on without checking. Numbers are quoted from the sources, not rounded.

---

## 1. Microsoft HCCB (High Capacity Color Barcode) / Microsoft Tag

**What it is.** A 2D code developed at Microsoft Research (inventor: Gavin Jancke) that encodes data in rows of
colored **triangles** rather than square modules. Palettes: 8-color, 4-color, or 2-color (black/white).
Microsoft claimed lab tests with off-the-shelf printers and scanners yielded 8-color HCCBs "equivalent to
approximately 3,500 characters per square inch" ([Wikipedia](https://en.wikipedia.org/wiki/High_Capacity_Color_Barcode)).
The Microsoft Research project page quotes "2,000 binary bytes, or 3,500 alphabetical characters per square inch"
with a 600 dpi business-card scanner, a minimum readable size of 3/4 inch square on cellphones, decoding in
"30 ms on a 200 MHz ARM processor", and a project start date of 18 Dec 2007
([Microsoft Research project page](https://www.microsoft.com/en-us/research/project/high-capacity-color-barcodes-hccb/)).

**Layout.** HCCB consists of rows of triangles (up to eight colors) with consecutive rows separated by a white
line, inside a black border. The decoder's strategy is to "identify four clusters in color space using mean
shift, and to assign each cluster center to one of the colors in a palette, contained in the barcode itself";
Bagherinia & Manduchi's Fig. 1 shows "the rightmost four patches in the last row" as the palette of reference
colors for a 4-color code ([Bagherinia & Manduchi, "A Theory of Color Barcodes", ICCV Workshops 2011, PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).
The primary localization/segmentation paper is Parikh & Jancke, "Localization and Segmentation of a 2D High
Capacity Color Barcode", IEEE WACV 2008 ([ResearchGate listing](https://www.researchgate.net/publication/4343443_Localization_and_Segmentation_of_A_2D_High_Capacity_Color_Barcode));
the full PDF could not be fetched in this session (certificate error on the Cornell mirror), so details such
as the exact number of palette triangles are **[unverified]**.

**Microsoft Tag.** The commercial implementation used **4 colors in a 5 x 10 grid** and also worked in
monochrome; it resolved tags via Microsoft's online service rather than storing payload offline
([Wikipedia](https://en.wikipedia.org/wiki/High_Capacity_Color_Barcode)). Tag launched in 2009; Microsoft
announced on 19 Aug 2013 that the service would shut down on **19 Aug 2015**, with Scanbuy/ScanLife offered
as a migration path from 18 Sep 2013 ([TechCrunch](https://techcrunch.com/2013/08/19/microsoft-gives-up-on-its-tag-barcode-service-schedules-it-for-shutdown-in-2015/),
[Wikipedia](https://en.wikipedia.org/wiki/High_Capacity_Color_Barcode)). Press coverage attributes the shutdown
to weak consumer adoption of a proprietary alternative to QR (TechCrunch above); Microsoft did not publish a
technical post-mortem. HCCB was separately licensed to the ISAN International Agency for audiovisual
identifiers ([Wikipedia](https://en.wikipedia.org/wiki/High_Capacity_Color_Barcode)).

**Why it matters for us.** HCCB demonstrated (a) an in-symbol reference palette, (b) clustering-based color
classification, and (c) that a proprietary, server-dependent ecosystem loses to an open, offline standard.
Bagherinia & Manduchi also note that palette-based clustering "only works for dense barcodes, with the number
of patches largely exceeding the number N of colors available" and "is not guaranteed to work well when many
more colors are present" ([PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).

---

## 2. JAB Code (Fraunhofer SIT) - ISO/IEC 23634:2022

**Status.** Developed by Fraunhofer SIT on behalf of the German BSI; open source under LGPL v2.1
([Fraunhofer SIT press release, 26 Jun 2020](https://www.sit.fraunhofer.de/en/news/latest/press-releases/details/news-article/show/bunter-barcode-wird-iso-standard/),
[GitHub jabcode/jabcode](https://github.com/jabcode/jabcode)). Standardized as ISO/IEC 23634:2022
"JAB Code polychrome bar code symbology specification", published 20 Apr 2022, 72 pages
([iTeh listing](https://standards.iteh.ai/catalog/standards/iso/196b22f3-f557-416d-b2b5-f65f3207aed5/iso-iec-23634-2022)).
The freely downloadable pre-ISO specification is BSI TR-03137 Part 2
([BSI PDF](https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/TechGuidelines/TR03137/BSI-TR-03137_Part2.pdf?__blob=publicationFile&v=1));
all spec details below are from that document unless stated otherwise.

**Colors.** Eight module-color modes: 2, 4, 8, 16, 32, 64, 128 or 256 colors; a module carries log2(Nc) bits.
Annex F prescribes the palettes: 4-color mode uses blue, green, magenta, yellow; 8-color mode uses the eight
RGB-cube vertices (black, blue, green, cyan, red, magenta, yellow, white; palette index order in Table 3 is
Black, Blue, Green, Cyan, Red, Magenta, Yellow, White); 16-color mode quantizes R to {0,85,170,255} with G,B
binary; 64-color mode uses 4 levels per channel; 128/256-color modes use 8 levels on R (and G)
(BSI TR-03137 Part 2, Annex F). Fraunhofer's own evaluation: "with current printer and reader hardware,
using more than 8 colors is difficult in practice. More colors should only be used if the printing and
capturing processes are optimized for a particular color set"
([Berchtold et al., "JAB Code - A Versatile Polychrome 2D Barcode", IS&T Electronic Imaging 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).

**Embedded color palette (calibration).** Every symbol (primary or secondary) embeds **two** color palettes
in reserved module positions around the finder patterns / metadata; `CPalette = MIN(64, Nc) x 2` modules, so
up to 128 modules are reserved for palettes and each palette holds at most 64 colors. For 128/256-color modes
only a subset is embedded and the full palette is reconstructed by per-channel interpolation. Decoding samples a
3x3-pixel area at each palette-module grid intersection to build the palettes, then assigns each data module to
"the nearest color palette in the symbol" (BSI TR-03137 Part 2, sections 3.3.8, 3.4.4, 6.5, 6.6, Annex F.2).
Berchtold et al. describe this as "the code stores colors redundantly in a color palette as a reference in order
to provide high robustness" ([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).

**Finder and alignment patterns.** Four finder patterns (UL, UR, LR, LL) near the corners, each made of two
3x3 squares overlapping in one core module; each has its own color order and orientation so that both rotation
and mirroring can be resolved; 4 x 17 = 68 modules total in a primary symbol. No quiet zone is required.
Alignment patterns (two 2x2 squares overlapping in a core module) appear from side-version 6. Secondary
symbols have no finder patterns; they use alignment patterns at the finder positions instead
(BSI TR-03137 Part 2, sections 3.3.1, 3.3.6, 3.3.7; [IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).
The detector binarizes the image in each of the three color channels and accepts a finder pattern only if the
alternating pattern is found in three of four scan directions in **all three channels** (IS&T 2020).

**Symbol sizes and cascading.** Side-versions 1-32 give square sizes 21x21 to 145x145 modules in steps of 4;
rectangles from 21x25 to 141x145 are allowed. A JAB Code is one **primary symbol** plus optionally many
**secondary symbols** docked horizontally or vertically (the docked sides must have equal module counts),
which allows U-shapes and other free forms (BSI TR-03137 Part 2, sections 3.3, 3.5; IS&T 2020).

**Error correction.** LDPC codes, chosen because they handle random errors (frequent with color) better than
Reed-Solomon; data and ECC bits are pseudo-randomly interleaved so that burst damage becomes random errors
(IS&T 2020). Eleven ECC levels; parameters wc in [3,8], wr in [4,9]; code rate R = 1 - wc/wr; K = floor(C x wc/wr)
parity bits; parity-check matrix built from wc random permutations of a block of wr ones (seed 785465 for data,
38545 for metadata) followed by Gauss-Jordan elimination (BSI TR-03137 Part 2, section 4.4). Metadata is
LDPC-encoded separately (doubling its length) and always written with at most 8 colors so that it can be read
before the full palette is known (sections 3.4.3, 3.3.8).

**Capacity (Table 1, default wc=4, wr=7, i.e. rate 3/7).** Side-version 1 (21x21): 364 data modules, net
payload 312 bits (4 colors) / 466 bits (8 colors). Side-version 32 (145x145): 20,940 data modules, net payload
17,948 bits (4 colors) / 26,925 bits (8 colors) (BSI TR-03137 Part 2, Table 1). Worked example from
Fraunhofer: a 1,363-byte signed prescription needs a 133x133 QR code (17,689 modules) but only an 85x85 JAB
Code (7,225 modules), "approximately three times higher data density" with eight colors
([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).

**Reported robustness (IS&T 2020, same source).** Recognition rate on white paper: inkjet 96 %, laser 95 %,
phone 94 %, flatbed scanner 100 %; on colored/textured paper: 90 / 86 / 84 / 94 %. Light temperature
(phones): 3000 K 94 %, 4000 K 92 %, 5000 K 96 %, 6500 K 96 %, daylight 98 %. Damage: folded 100 %,
stamps 100 / 98 %, shadow 100 / 97 %, coffee stains 95 % (inkjet) / 78 % (laser). Failure analysis: most
failures were finder patterns not found; a laser printer rendered red (255,0,0) and magenta (255,0,255)
"almost indistinguishable", motivating per-printer color selection; microscope images show colorants
"disperse into other module areas" (cross-module interference). The iPhone 7 reproduced warm light casts
more faithfully than Android phones and decoded worse under warm light.

---

## 3. HCC2D - High Capacity Colored 2-Dimensional code (Univ. of Rome Tor Vergata)

**Origin.** Grillo, Lentini, Querini & Italiano, "High Capacity Colored Two Dimensional codes", IMCSIT 2010,
pp. 709-716 ([PDF](https://annals-csis.org/proceedings/2010/pliks/79.pdf)); extended in Querini, Grillo,
Lentini & Italiano, "2D Color Barcodes for Mobile Phones", IJCSA 8(1):136-155, 2011
([Semantic Scholar](https://www.semanticscholar.org/paper/2D-Color-Barcodes-for-Mobile-Phones-Querini-Grillo/729b220b3f2de47f32c9454cd3814627fef141e0)).

**How it reuses QR.** HCC2D keeps **all** QR function patterns (position detection, alignment, timing,
separators), the Format Information and the Version Information in black and white, "preserving the strong
robustness to geometric distortions of QR code"; only the Data and Error Correction Codewords area is colored.
With 4 colors each module carries 2 bits, with 8 colors 3 bits
([Querini & Italiano, "Reliability and Data Density in High Capacity Color Barcodes", ComSIS 11(4):1595-1615, 2014](https://www.comsis.org/pdf.php?id=mm067-1308)).
The 2010 prototype used 4 or **16** colors ([Grillo et al. 2010](https://annals-csis.org/proceedings/2010/pliks/79.pdf);
also stated in [Melgar et al., CQR Code-9 slides](https://pdfs.semanticscholar.org/95c7/fe455a084b0f0ce9923e996652156c1f7998.pdf)
and by [Bagherinia & Manduchi](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)); the later
2013-2014 papers settled on 4 or 8.

**Color Palette Patterns.** Because "to consider the color palette as an a priori shared knowledge between
encoding and decoding processes is not a reliable solution", HCC2D adds **four Color Palette Patterns** located
at the symbol boundaries, "not too close to the three Position Detection Patterns areas and far away from each
other", taking "only 2 rows and 2 columns" of the 21-177 module symbol. The replicated palettes are used
"either for cluster initialization or for training machine learning classifiers"
([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308)).

**Reported capacity and error rates (desktop, 600 dpi print and scan, low-cost color laser MFPs).**
Test symbols: 149x149 cells, 4x4 printer dots per cell, 1 square inch, 4 colors, 4,930 bytes/in² gross
(data + ECC), 512 known palette cells for training and 19,720 cells to classify. Under identical conditions
"black and white QR codes had an average byte error rate of roughly 2% while their 4-color counterpart
(HCC2D codes) had an average byte error rate of roughly 10%". Mean byte error rate (ByER) by classifier:
Euclidean 9.56 %, **K-means 4.54 %**, LMT 8.51 %, Louvain 7.84 %, Naive Bayes 6.21 %, SVM 8.09 %. Using the
90th percentile of K-means ByER (9.71 %) and Reed-Solomon redundancy = 2 x ByER gives a redundancy rate of
19.42 % and an effective density of **3,972 bytes/in² at 90 % success** (4,105 at 85 %, 3,820 at 95 %).
Features were in **YUV** space because RGB channels are highly correlated
([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308); conference version
[Querini & Italiano, FedCSIS 2013, pp. 611-618](https://annals-csis.org/Volume_1/pliks/67.pdf)).

**Mobile results (Nexus 4 / Nexus 5, 1.5 inch print, 6x6 dots per cell).** K-means collapsed to a mean
ByER of 29.1 % (it "appears to degrade its performance in case of strongly non-uniform illumination" and
"in many bad cases K-means fails to converge"); LMT 4.56 %, SVM 5.96 %, Euclidean 6.64 %, Naive Bayes 8.41 %,
Louvain 11.47 %. Conclusion: on phones "simple and efficient methods (in terms of computational time) such as
the Euclidean and the K-means classifiers are not effective (in terms of error rate), while, more complex
methods are effective but not efficient" ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308)).

**Other HCC2D findings.** Decoding overhead over QR averaged about 15 % (4 colors) and 25 % (16 colors). On an
inkjet MFP at 1 square inch, 180 dpi draft printing failed for all versions; at 360 dpi versions 5 and 10
decoded but version 15 (77x77) needed 720 dpi ([Grillo et al. 2010](https://annals-csis.org/proceedings/2010/pliks/79.pdf)).

**2025-era re-specification (hcc2d.com).** Marco Querini now publishes an "HCC2D Code Specification
v0.9.0" with HCC2D4 (4 colors) and HCC2D8 (8 colors), QR versions 1-40, QR-compatible Reed-Solomon with
codeword blocks doubled/tripled, bit planes de-interleaved by stride, two palette models (screen: black, red
(220,0,0), cyan (0,200,220), white; print: black, magenta, cyan, white) and a palette implemented as a
**one-module colored border** cycling through palette indices on all four sides, so the full symbol is
(N+2)x(N+2). The decoder "has no prior knowledge of the palette colors, except that the first entry is black
and the last is white" ([hcc2d.com spec](https://hcc2d.com/en/spec)). The site carries a disclaimer that the
views are the author's and not an institution's ([hcc2d.com](https://hcc2d.com/en)). Note that this border
palette differs from the four interior Color Palette Patterns of the 2010-2014 papers.

---

## 4. Layered / per-colorant-channel color QR codes

### 4.1 Bulan, Monga & Sharma (orientation modulation)
Bulan, Monga & Sharma, "High capacity color barcodes using dot orientation and color separability", SPIE
Media Forensics and Security 2009, embedded data in two colorant channels via halftone-dot orientation
modulation ("to print two colors at the same spatial location"), and Bulan & Sharma, "High Capacity Color
Barcodes: Per Channel Data Encoding via Orientation Modulation in Elliptical Dot Arrays", IEEE Trans. Image
Processing 20(5):1337-1350, 2011, extended this to three colorants (C, M, Y) with an interference-mitigating
orientation design, reporting **16,875 bits per square inch** on a print-and-scan channel
([ResearchGate listing](https://www.researchgate.net/publication/47793929_High_Capacity_Color_Barcodes_Per_Channel_Data_Encoding_via_Orientation_Modulation_in_Elliptical_Dot_Arrays);
summary in [Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308); density also quoted in
[US 9,111,186](https://patents.google.com/patent/US9111186B2/en)).

### 4.2 Blasinski, Bulan & Sharma - per-colorant-channel color barcodes (IEEE TIP 2013)
"Per-Colorant-Channel Color Barcodes for Mobile Applications: An Interference Cancellation Framework", IEEE
TIP 22(4):1498-1511, 2013: independent data (e.g. three ordinary QR codes) is printed in the **C, M, Y**
colorant channels and read from the complementary **R, G, B** camera channels, "a three-fold increase in data
rate" ([Stanford publication list](https://stanford.edu/~hblasins/publications.html),
[Semantic Scholar](https://www.semanticscholar.org/paper/Per-Colorant-Channel-Color-Barcodes-for-Mobile-An-Blasinski-Bulan/0df9838dfb97132f644021acc7a7baf05a05b77d)).
The companion patent US 9,111,186 (Univ. of Rochester) details the model and cancellation:
- **Interference model:** normalized optical densities are linear in the colorant indicator images,
  d_k(x,y) = sum_i d_ki * I_i(x,y), where d_ki is the density of colorant i seen in camera channel k, i.e. a
  3x3 **mixing matrix D** (spectral absorption model).
- **Pilot-block method:** six reference patches (C, M, Y, CM, CY, MY - the chromatic Neugebauer primaries)
  are embedded in the positioning marks; their known input/output pairs give D by constrained least squares.
- **EM-type method:** jointly estimates D and the binary colorant images as latent variables.
- **Results:** cyan channel about 90 % decoding; yellow channel "<3 % decoding" without interference
  cancellation (best with EM); overall synchronization 95 %
  ([Google Patents US9111186B2](https://patents.google.com/patent/US9111186B2/en)).
The colorant-to-channel correspondence (cyan->red, magenta->green, yellow->blue) is also stated in Xerox
patent US 8,100,330 ([Google Patents](https://patents.google.com/patent/US8100330B2/en)).

### 4.3 HiQ - Yang, Xu, Deng, Loy & Lau (CUHK), IEEE TIP 2018
"Robust and Fast Decoding of High-Capacity Color QR Codes for Mobile Applications", IEEE TIP 27(12):6093-6108,
Dec 2018, DOI 10.1109/TIP.2018.2855419 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/30028700/),
[arXiv 1704.06447](https://ar5iv.labs.arxiv.org/html/1704.06447)). Key points from the arXiv version:
- **Structure:** n independent monochrome QR layers -> 2^n colors (1 layer: 2, 2 layers: 4, 3 layers: 8).
  Capacity examples: **2,900 bytes in 26x26 mm², 7,700 bytes in 38x38 mm², 8,900 bytes in 42x42 mm²**.
- **Three chromatic distortions:** cross-channel interference (CCI, print colorants leaking into the wrong
  RGB channel), illumination variation, and a newly identified **cross-module interference (CMI)** where
  neighboring modules' colors bleed into the sampled module in dense codes.
- **Color recovery:** LSVM-CMI (layered SVM: n binary classifiers instead of a 2^n-class one, with a linear CMI
  cancellation term) and QDA-CMI (quadratic discriminant analysis jointly learning class covariances and mixing
  coefficients). Adding CMI modeling lowered failure rate from 65 % to 56 % and BER from 4.3 % to 3.2 %.
- **Geometry:** Robust Geometric Transformation (RGT) uses all finder/alignment patterns in a weighted
  over-determined system solved by SVD instead of just four corner points.
- **Dataset CUHK-CQRC:** 5,390 samples (1,506 photos + 3,884 video frames), 8 phone models, 5 lighting
  conditions; printers Ricoh Aficio MP C5501A, Ricoh MP C6004, HP DeskJet 2130.
- **Versus the per-colorant-channel baseline (PCCC):** decoding success improved from about 54 % to at least
  84 % and BER by 60 %; decoding within 3 s on phones.
- **Noisiest layer:** "The third layer (yellow channel in PCCC) always yields the worst performance",
  struggling to separate yellow from white under strong light and blue from black under dim light.
Code: [cuhk-mobitec/HiQ](https://github.com/cuhk-mobitec/HiQ-Robust-and-Fast-Decoding-of-High-Capacity-Color-QR-Codes)
(desktop generator + Android decoder in Java on ZXing, plus MATLAB for the CMI algorithms; dataset at authpaper.net).
Melgar et al. quote HiQ at 8,097 bytes in 38x38 mm = 3,617.63 bytes/in²
([search summary citing CQR Code-9](https://www.researchgate.net/publication/311666529_A_High_Density_Colored_2D-Barcode_CQR_Code-9)).

### 4.4 The "three QR codes in RGB/CMY" folk approach
Several hobby implementations simply overlay three QR codes in the R, G, B image channels and split channels
to decode (see section 8: tmk3qr, ColorZXing.Net). Without a mixing model this is exactly the configuration
Blasinski et al. show collapses in the yellow/blue channel (<3 % decoding) when printed
([US9111186B2](https://patents.google.com/patent/US9111186B2/en)).

---

## 5. Other color barcode systems

| System | Year / venue | Notes | Source |
|---|---|---|---|
| **COBRA** (Hao, Zhou, Xing, Michigan State) | MobiSys 2012, pp. 85-98 | Screen-to-camera streaming code; "smart border" of color corner trackers and timing reference blocks; 4 colors -> 2 bits per block; sender adapts block size/layout to blur ("blur-aware color ordering"); throughput figures in the 100-200 kbps range appear in the preview charts **[full text not fetched; ACM 403]** | [ACM DL](https://dl.acm.org/doi/10.1145/2307636.2307645), [yumpu preview](https://www.yumpu.com/en/document/view/4350371/cobra-color-barcode-streaming-for-smartphone-systems) |
| **Strata** (Hu, Mao, Huang, Xue, She, Bian, Shen) | MobiCom 2014 | Hierarchical modulation borrowed from RF: layered coding so near/high-res cameras decode more layers, far/low-res cameras fewer; adjacent-layer interference controlled so each layer is independently decodable | [ACM DL](https://dl.acm.org/doi/10.1145/2639108.2639132), [Semantic Scholar](https://www.semanticscholar.org/paper/Strata:-layered-coding-for-scalable-visual-Hu-Mao/6d0829624336f2fc8afbb871ce41c1cfb727a674) |
| **RDCode** (Wang et al.) | MobiCom 2014 | Packet-frame-block structure with ECC at intra-block, inter-block and inter-frame levels; claimed error rate down to 10 % and at least 2x COBRA's rate | [ACM DL](https://dl.acm.org/doi/10.1145/2639108.2639135) |
| **PiCode** (Chen, Huang, Zhou, Liu, Mow, HKUST) | IEEE TIP 25(8):3444-3458, 2016 | Picture-embedding barcode; optimizes perceptual quality of the embedded image vs decodability. Not a color-data code | [HKUST](https://researchportal.hkust.edu.hk/en/publications/picode-a-new-picture-embedding-2d-barcode/) |
| **CQR Code-5** (Melgar et al., Univ. of Brasilia) | IEEE ICCE-Berlin 2012 | 49x49 QR-like structure; 5 colors (black, white, red, green, blue) chosen for maximum RGB equidistance; 1,024 info bits + 3,392 RS parity bits (38.40 % ECC) | [ResearchGate](https://www.researchgate.net/publication/261075725_CQR_codes_Colored_quick-response_codes), [CQR-9 slides](https://pdfs.semanticscholar.org/95c7/fe455a084b0f0ce9923e996652156c1f7998.pdf) |
| **CQR Code-9** (Melgar, Farias, Vidal, Zaghetto) | SIBGRAPI 2016 | 49x49; black function patterns + 8 data colors (R=000, G=001, B=010, C=011, M=100, Y=101, W=110, Gray=111), 3 bits/module; 2,048 info bits + 4,576 parity bits, RS(414,128) over GF(2^16); a 1.3x1.3 cm print decoded at 7-13 cm with a Galaxy S5 | [slides PDF](https://pdfs.semanticscholar.org/95c7/fe455a084b0f0ce9923e996652156c1f7998.pdf) |
| **ColorCode** (ColorZip Media, Korea) | patent filed 2000, granted 2006; launched 2005 | Matrix of colored cells with data, **parity**, **reference** and control areas; example with 8 colors (3 bits); parity cells are XOR of data values and a mismatch triggers re-estimation of brightness/illumination parameters; supports indirect (database-pointer) encoding | [US 7,020,327](https://patents.google.com/patent/US7020327B2/en), [history page](https://free-barcode.com/barcode/barcode-history/history-colorcode-colorzip.asp) |
| **ImageID color bar code** (Sali & Lax) | US 7,210,631 (2007), US 7,051,935 (2006) | N colors (example black, blue (0,200,255), green, red, yellow); calibration by photographing a printed color chart under many conditions and building a k-nearest-neighbor RGB->color lookup table; later assigned to Microsoft | [US7210631B2](https://patents.google.com/patent/US7210631B2/en), [US7051935B2](https://patents.google.com/patent/US7051935B2/en) |
| **Konica Minolta high-capacity 2D color barcode** (Gang Fang) | US 2015/0347886 A1 (filed 2014) | CMYK, 2 bits/cell; **border of reference cells** in repeating Y,K,M,K,C,K order; yellow reference cells elongated for detectability; decoding in CIE L*a*b* with CIEDE94 distances and position-interpolated offsets; 134x134 grid = 16,788 data cells in about 1.15x1.15 in at 600 dpi | [Google Patents](https://patents.google.com/patent/US20150347886A1/en) |
| **Ultracode** (AIM ISS, Zebra) | AIM standard; public domain | Long thin strip of column pairs of 7 monochrome or 8 colored cells (W/R/G/B or C/M/Y/K); Reed-Solomon levels EC0-EC5; explicitly "not positioned as high-capacity" | [barcode.ro](https://www.barcode.ro/tutorials/barcodes/ultracode.html), [BWIPP wiki](https://github.com/bwipp/postscriptbarcode/wiki/Ultracode) |
| **ChromoCode** (Inventerprise LLC) | commercial | Colors mapped to characters; includes calibration colors "so color variation between printers can be accommodated" **[site unreachable in this session; from search snippet only]** | [chromocode.com](http://chromocode.com/chromocode-description.php) |
| **PixNet** (MIT) | MobiCom 2010 | LCD-camera link using 2D OFDM in the frequency domain, up to 12 Mb/s at 10 m; not a color-module barcode | [PDF](https://people.csail.mit.edu/nabeel/pixnet-mobicom10.pdf) |
| **cimbar** (sz3) | open source, 2020- | "color-icon-matrix": 16 icon shapes x 2-3 color bits = 6-7 bits/tile, Reed-Solomon; about 7,500 bytes per frame; screen-to-camera target >= 100 kB/s | [GitHub](https://github.com/sz3/cimbar) |
| **Bagherinia & Manduchi palette-free codes** | ICCV Workshops 2011; ECCV 2012 | Decodes groups of k patches jointly as nearest low-dimensional subspace; 24 colors, k=5 -> 3.8 bits/bar with P(error) < 0.001 for 60 bars; follow-up used 2-6 reference colors | [PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf), [Springer](https://link.springer.com/chapter/10.1007/978-3-642-33868-7_48) |

**Not color-coded (for disambiguation).** Denso Wave's **Frame QR** only adds a free "canvas area" for
graphics inside an otherwise standard QR; data is not carried by color
([Denso Wave](https://www.qrcode.com/en/codes/frameqr.html)). **Han Xin Code** (ISO/IEC 20830:2021) is a
monochrome Chinese matrix code ([Wikipedia](https://en.wikipedia.org/wiki/Han_Xin_code),
[ISO](https://www.iso.org/standard/69321.html)). A broad 2023 survey listing further systems (CodeCube 2017,
UnseenCode 2019, 4D color barcode 2015, Kato et al. 2010 color selection, Melgar CQR) is
[Color Barcodes from Debut to Present](https://www.alphanumericjournal.com/article/color-barcodes-from-debut-to-present-a-broad-survey-on-the-state-of-the-art).

---

## 6. Color calibration and classification techniques found in the literature

1. **Reference palettes embedded in the symbol.** HCCB (palette triangles in the last row), HCC2D (four
   2-row/2-column palette patterns; later a one-module border), JAB Code (two redundant palettes of up to
   64 colors around the finder patterns, 128 modules), Konica Minolta (full border of reference cells),
   ColorCode (reference area). Rationale from HCC2D: palette cells "are supposed to be distorted in the same
   way color cells of the Encoding Region are" ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308)).
   Cost: Bagherinia & Manduchi show the information rate of a palette-displaying code is
   (1 - N/K) log2 N, so for short codes the palette dominates; the optimum for a 60-patch code is N = 16
   colors and about 3 bits/patch ([PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).
2. **Finder patterns as references.** Blasinski et al. embed the six Neugebauer-primary pilot patches inside the
   positioning marks ([US9111186B2](https://patents.google.com/patent/US9111186B2/en)); JAB Code's colored
   finder patterns are detected per channel ([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).
   ColorZXing.Net estimates per-channel black/white references from the finder area and normalizes gain and
   white balance before thresholding ([GitHub](https://github.com/HainanZhao/ColorZXing.Net)).
3. **Linear / diagonal color correction.** The 3x3 density mixing matrix D estimated by least squares from pilot
   patches (Blasinski); the diagonal von Kries model where each channel scales by an illuminant-dependent gain,
   which lets Bagherinia & Manduchi calibrate from one photo of the palette (at a 10x higher error rate than a
   PCA subspace trained on 5 illuminants). Wang & Manduchi estimate a parametric transform from "one or two
   reference color patches" ([PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).
4. **Per-channel thresholding** (layered codes): each RGB channel is binarized like a normal QR after
   interference cancellation; the yellow/blue layer is the weak link ([US9111186B2](https://patents.google.com/patent/US9111186B2/en),
   [HiQ](https://ar5iv.labs.arxiv.org/html/1704.06447)).
5. **Clustering** (k-means, mean shift) seeded by palette colors: best on scanners (HCC2D 4.54 % ByER), worst on
   phones with non-uniform illumination (29.1 %) ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308));
   HCCB used mean shift ([Bagherinia & Manduchi](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).
6. **Supervised classifiers** trained on palette cells: SVM, logistic model trees, Naive Bayes (HCC2D); layered
   SVM and QDA with explicit CMI terms (HiQ); k-NN lookup tables built offline from a color chart (ImageID).
7. **Perceptual color spaces:** YUV (HCC2D) and CIE L*a*b* with CIEDE94 (Konica Minolta) are preferred over raw
   RGB because luminance and chrominance decouple ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308),
   [US20150347886A1](https://patents.google.com/patent/US20150347886A1/en)).
8. **Modeled nuisances.** Cross-channel interference (CMY inks are not spectrally pure complements of RGB
   filters), illumination color casts (warm 3000 K light hurt JAB decoding, especially on an iPhone 7 whose
   pipeline preserves the cast), cross-module interference / blur at color boundaries (HiQ's CMI; JAB
   microscope images of colorant dispersion), printer driver color conversion (laser printer merging red
   and magenta), specular reflection, JPEG compression, color fading and printer drift
   ([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004),
   [HiQ](https://ar5iv.labs.arxiv.org/html/1704.06447), [Bagherinia & Manduchi](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf),
   [survey](https://www.alphanumericjournal.com/article/color-barcodes-from-debut-to-present-a-broad-survey-on-the-state-of-the-art)).

---

## 7. Practical limits reported in the literature

- **Number of colors.** Shipping/standardized systems use 4 or 8 (HCCB, HCC2D, JAB default, Microsoft Tag = 4).
  Fraunhofer: more than 8 colors "is difficult in practice" with current printers and readers
  ([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).
  HCC2D's 16-color variant (2010) was dropped for 8 in later work. Bagherinia & Manduchi reached 24 printed
  colors only by decoding groups jointly with a trained illuminant subspace, and warn that clustering "is not
  guaranteed to work well when many more colors are present" ([PDF](https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf)).
  JAB reserves 16-256 color modes for future hardware (BSI TR-03137 Part 2, Annex F).
- **Error-rate penalty of color.** Same printer/scanner/size: QR about 2 % byte errors vs 4-color HCC2D about
  10 %; the needed RS redundancy roughly doubles that, so a 4-color code nets about 80 % of its gross capacity,
  i.e. about 1.6x QR rather than 2x ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308)).
  JAB's default LDPC setting (wc=4, wr=7) spends 4/7 of the gross bits on parity (BSI TR-03137 Part 2, Table 1).
  HiQ reports BER 3.2-4.3 % for 3-layer codes with phones and 84 %+ frame decoding success
  ([arXiv](https://ar5iv.labs.arxiv.org/html/1704.06447)).
- **Achieved densities.** HCC2D 3,972 bytes/in² at 90 % success (scanner, 600 dpi); HiQ about 3,600 bytes/in²
  with phones; Bulan & Sharma 16,875 bits/in² (about 2,100 bytes/in²) with orientation modulation; HCCB
  claim 2,000 bytes/in² with a 600 dpi scanner; JAB about 3x QR density at equal ECC (sources above).
- **Which channel is weakest.** Consistently the **yellow colorant / blue camera channel**: Blasinski: yellow
  "<3 % decoding" without interference cancellation vs cyan about 90 %; HiQ: the yellow layer "always yields
  the worst performance" (yellow vs white under strong light, blue vs black in dim light)
  ([US9111186B2](https://patents.google.com/patent/US9111186B2/en), [HiQ](https://ar5iv.labs.arxiv.org/html/1704.06447)).
  Physical reasons discussed in the imaging literature: yellow ink has the lowest optical density/contrast
  against white paper; a Bayer CFA samples blue (and red) at only 1/4 of pixels vs 1/2 for green, and blue is
  typically boosted by white-balance gain, amplifying noise ([Bayer CFA analysis](https://www.strollswithmydog.com/bayer-cfa-effect-on-sharpness/)).
  A primary quantitative source for "silicon QE is lowest in blue" was not retrieved in this session **[unverified]**.
- **Printing constraints.** 4x4 printer dots per module at 600 dpi worked on a scanner; phones needed 6x6 dots
  and a 1.5 inch print for focus; draft (180 dpi) printing failed outright ([Querini & Italiano 2014](https://www.comsis.org/pdf.php?id=mm067-1308),
  [Grillo et al. 2010](https://annals-csis.org/proceedings/2010/pliks/79.pdf)). JAB recommends module size as an
  integer multiple of the print-head pixel and consistent lighting over the whole symbol (BSI TR-03137 Part 2, 5.5).
- **Scanner vs phone.** Every study that tested both found phones worse (JAB: 94 % vs 100 %; HCC2D: K-means
  4.5 % vs 29 % ByER), due to motion blur, non-uniform illumination and vendor image pipelines; JAB suggests
  decoding from a video stream rather than a single shutter press ([IS&T 2020](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004)).

---

## 8. Open-source implementations

| Repository | Language / license | Approach | Source |
|---|---|---|---|
| **jabcode/jabcode** | C11, LGPL 2.1, about 1.0k stars | Reference encoder/decoder of ISO/IEC 23634 JAB Code (4/8 colors default), libpng/libtiff; demo at jabcode.org | [GitHub](https://github.com/jabcode/jabcode), [jabcode.org](https://jabcode.org/) |
| **cuhk-mobitec/HiQ-...** | Java (desktop generator, Android decoder on ZXing) + MATLAB | n-layer color QR (2^n colors), LSVM/QDA color recovery with CMI cancellation, RGT geometry; CUHK-CQRC dataset; README "more details to come", no explicit license | [GitHub](https://github.com/cuhk-mobitec/HiQ-Robust-and-Fast-Decoding-of-High-Capacity-Color-QR-Codes) |
| **marco-querini/hcc2d-cli-c-encoder** / **hcc2d-cli-c-streamer** | single-file C, Apache 2.0, 3 stars | HCC2D4/HCC2D8 encoder per hcc2d.com spec v0.9.0 (ECC L/M/Q/H, versions 1-40, screen/print palette models, border palette); streamer shows animated symbol sequences; decoder is a closed app on Google Play / App Store | [encoder](https://github.com/marco-querini/hcc2d-cli-c-encoder), [streamer](https://github.com/marco-querini/hcc2d-cli-c-streamer), [hcc2d.com](https://hcc2d.com/en) |
| **HainanZhao/ColorZXing.Net** | C#, MIT (on ZXing.Net) | Three QR payloads on R/G/B planes (3x), plus a 6-layer / 4-levels-per-channel high-density mode; decoder locates geometry once, estimates per-channel black/white references, normalizes gain/white balance; warns about JPEG, lighting and white balance | [GitHub](https://github.com/HainanZhao/ColorZXing.Net) |
| **iladshyan/tmk3qr** | Python (qrcode, Pillow, zbar), 2 stars | Merges three QR codes into R, G, B channels; decodes by channel split + zbar; no calibration | [GitHub](https://github.com/iladshyan/tmk3qr) |
| **sz3/cimbar** | C++/Python/WASM, MIT | Icon shape (4 bits) + color (2-3 bits) per tile, Reed-Solomon, nearest-expected-color decoding; screen-to-camera file transfer | [GitHub](https://github.com/sz3/cimbar) |
| **yxpil/CQRC** | C# + JavaScript | Despite the name, colors are styling (gradients, round eyes) on a standard QR; no color-data | [GitHub](https://github.com/yxpil/CQRC) |
| **ruitaocc/vCode** | C++ | Halftone/colorful aesthetic QR, not color-data | [GitHub topic color-qr](https://github.com/topics/color-qr) |

---

## 9. Comparison table

| System | Year | Colors | Bits/module | Calibration method | ECC | Status |
|---|---|---|---|---|---|---|
| Microsoft HCCB / Tag | 2007 / 2009-2015 | 4 or 8 (Tag: 4) | 2 or 3 per triangle | Palette triangles in last row; mean-shift clustering | not published | Discontinued 19 Aug 2015; proprietary |
| JAB Code | 2018; ISO/IEC 23634:2022 | 4 or 8 default, modes to 256 | 2-3 (up to 8) | Two embedded palettes (up to 64 colors each, 128 modules), nearest-palette-color, per-channel finder detection | LDPC, 11 levels, rate 1 - wc/wr, interleaved | Open (LGPL 2.1), ISO standard |
| HCC2D (Tor Vergata) | 2010-2014 | 4 or 8 (16 in 2010) | 2-3 | Four 2-row/2-col palette patterns; k-means / SVM / LMT in YUV | QR Reed-Solomon | Academic; 2025 re-spec + apps by Querini |
| HCC2D spec v0.9.0 (hcc2d.com) | 2025 | 4 or 8 | 2-3 | One-module palette border on all sides | QR RS, blocks x2 / x3 | Encoder open (Apache 2.0), decoder app only |
| Bulan & Sharma orientation modulation | 2011 | C,M,Y channels | 3 orientation bits per dot cell | Per-channel; orientation robust to tone variation | per channel | Academic, patented |
| Blasinski/Bulan/Sharma PCCC | 2013 | 3 layers (8 composite colors) | 3 | Six Neugebauer pilot patches in finder marks -> 3x3 mixing matrix; EM | QR RS per layer | Academic, patented (US 9,111,186) |
| HiQ (CUHK) | 2016 / 2018 | 2^n (n <= 3 tested) | n | Trained LSVM/QDA with CMI cancellation, RGT | QR RS per layer | Academic; code on GitHub |
| CQR Code-5 / -9 | 2012 / 2016 | 5 / 9 | 2 / 3 | Histogram segmentation, RGB equidistant colors | RS, 38 % / 34.5 % | Academic |
| ColorCode (ColorZip) | 2000-2005 | e.g. 8 | 3 | Reference + parity areas, iterative re-estimation | XOR parity | Commercial (Korea), patents expired 2022 |
| Konica Minolta patent | 2014 | 4 (CMYK) | 2 | Full reference-cell border, L*a*b*/CIEDE94 | not detailed | Patent application |
| COBRA | 2012 | 4 | 2 per block | Corner trackers / timing blocks; blur-aware | CRC + stream-level | Academic (screen-camera) |
| Ultracode | AIM ISS | 2 or up to 8 | approx 3 per cell | n/a (standard) | RS EC0-EC5 | Public domain, low adoption |
| cimbar | 2020- | 4-8 + 16 icons | 6-7 per tile | Nearest expected color | RS | Open (MIT), hobby |

---

## 10. Lessons learned / design implications for a new colored QR variant

1. **Keep every QR function pattern monochrome and geometrically identical to ISO 18004.** HCC2D, CQR and HiQ
   all did this and inherited QR's detection robustness; JAB had to invent colored finder patterns and reports
   that most of its failures were "finder pattern could not be found". Black/white finder, timing, alignment,
   format and version modules also give free luminance references.
2. **Target 4 colors (2 bits/module) as the robust default and 8 colors (3 bits) as the dense option; do not
   design around 16+ colors for printed media.** Fraunhofer, Tor Vergata and Bagherinia all converge on 8 as the
   practical phone/office-printer ceiling; reserve higher modes in the format metadata only if cheap.
3. **Choose palette colors at RGB-cube vertices (or the subset black/white/cyan/magenta for 4 colors) and make the
   palette selectable per medium (screen vs print).** JAB's 8-color palette and HCC2D's screen/print models both
   do this; a laser printer merged red and magenta, so avoid pairs that differ in only one weakly printed channel.
4. **Embed a reference palette, replicated in several places, inside the symbol.** All deployed systems do;
   HCC2D's four interior patterns (2 rows + 2 columns), JAB's two palettes (2 x min(64,Nc) modules), and
   Konica's border all exist because a priori palettes fail under real illumination. Place replicas far apart to
   survive local shadows and stains, and keep them away from the finder patterns' quiet areas.
5. **Budget realistically: expect byte error rates about 5x those of monochrome QR under identical conditions**
   (about 10 % vs 2 %), so a 4-color symbol nets about 1.6x QR, not 2x, after Reed-Solomon redundancy. Expose high
   ECC levels; JAB's default spends 4/7 of bits on parity.
6. **Prefer interleaving so color-classification errors look random, and consider LDPC or at least RS with
   deep interleaving.** JAB chose LDPC explicitly because color misclassification is a random-error process while
   RS is tuned for bursts; if staying QR-compatible with RS, keep QR's block interleaving and consider mapping the
   bit planes to separate RS blocks so a bad channel does not poison every codeword (HCC2D v0.9 de-interleaves
   planes by stride).
7. **Model the camera-side distortions explicitly: cross-channel interference, illumination cast and
   cross-module blur.** The single largest gain in HiQ came from a 3x3 mixing matrix plus a neighbor-bleed
   term; Blasinski's six pilot patches (C, M, Y, CM, CY, MY) are enough to solve a 3x3 mixing matrix by least
   squares. A palette whose entries span all channel combinations doubles as this training set.
8. **Classify in a luminance/chrominance space (YUV, Lab) with a supervised or probabilistic classifier seeded by
   the palette, not plain Euclidean RGB or unseeded k-means.** k-means was best on flatbed scans (4.5 % ByER)
   but the worst method on phones (29 %) because of non-uniform illumination; LMT/SVM/QDA were best on phones.
   A cheap compromise used by HCC2D is k-means initialized from the averaged palette patterns plus a per-region
   (local) white/black normalization.
9. **Treat the yellow colorant / blue camera channel as the weak link.** Give it the most redundancy or the
   fewest decision levels, avoid distinguishing yellow from white and blue from black by luminance alone, and
   consider favoring cyan/magenta/black for the 4-color palette (HCC2D's print model: black, magenta, cyan,
   white).
10. **Design the module size for the printer, not the screen:** 4x4 dots at 600 dpi was the scanner limit, 6x6
    dots and a 1.5 inch symbol were needed for phones; draft-mode printing (180 dpi) failed. Specify a minimum
    module size per color mode and make the module an integer multiple of the printer dot.
11. **Decode from a video stream, estimate geometry from all finder/alignment patterns (RGT), and sample a small
    central area per module** (JAB samples 3x3 pixels) to minimize blur-induced CMI.
12. **Stay backward-compatible and offline.** Microsoft Tag's dependence on a resolver service and proprietary
    reader is the cited reason it died; JAB and HCC2D publish specs and LGPL/Apache code. A design that lets a
    legacy QR reader decode at least the luminance plane (format info and a base layer) is attractive but
    unproven in the literature (only noted conceptually as "DualCodes", Springer 2013, not fetched).
13. **Publish a test corpus and protocol.** No standard robustness test exists for color codes (Fraunhofer's
    complaint); HiQ's CUHK-CQRC (5,390 images, 8 phones, 5 illuminants, 3 printers) is the closest reference
    and should guide our own evaluation matrix: printer type (inkjet vs laser), paper, light temperature
    3000-6500 K, phone vendor pipelines, damage.

---

## Sources

- Wikipedia, High Capacity Color Barcode: https://en.wikipedia.org/wiki/High_Capacity_Color_Barcode
- Microsoft Research, High Capacity Color Barcodes project page: https://www.microsoft.com/en-us/research/project/high-capacity-color-barcodes-hccb/
- TechCrunch, "Microsoft Gives Up On Its Tag Barcode Service..." (19 Aug 2013): https://techcrunch.com/2013/08/19/microsoft-gives-up-on-its-tag-barcode-service-schedules-it-for-shutdown-in-2015/
- Parikh & Jancke, WACV 2008 (listing): https://www.researchgate.net/publication/4343443_Localization_and_Segmentation_of_A_2D_High_Capacity_Color_Barcode
- Bagherinia & Manduchi, "A Theory of Color Barcodes", ICCV Workshops 2011: https://users.soe.ucsc.edu/~manduchi/papers/ColorBarcodes.pdf
- Bagherinia & Manduchi, "High Information Rate and Efficient Color Barcode Decoding", ECCV 2012 workshops: https://link.springer.com/chapter/10.1007/978-3-642-33868-7_48
- Wikipedia, JAB Code: https://en.wikipedia.org/wiki/JAB_Code
- Fraunhofer SIT press release (26 Jun 2020): https://www.sit.fraunhofer.de/en/news/latest/press-releases/details/news-article/show/bunter-barcode-wird-iso-standard/
- ISO/IEC 23634:2022 listing: https://standards.iteh.ai/catalog/standards/iso/196b22f3-f557-416d-b2b5-f65f3207aed5/iso-iec-23634-2022
- BSI TR-03137 Part 2 (JAB Code specification): https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/TechGuidelines/TR03137/BSI-TR-03137_Part2.pdf?__blob=publicationFile&v=1
- Berchtold et al., "JAB Code - A Versatile Polychrome 2D Barcode", IS&T EI 2020: https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/ei/32/3/art00004
- jabcode GitHub: https://github.com/jabcode/jabcode ; demo: https://jabcode.org/
- Grillo, Lentini, Querini, Italiano, "High Capacity Colored Two Dimensional codes", IMCSIT 2010: https://annals-csis.org/proceedings/2010/pliks/79.pdf
- Querini, Grillo, Lentini, Italiano, "2D Color Barcodes for Mobile Phones", IJCSA 2011: https://www.semanticscholar.org/paper/2D-Color-Barcodes-for-Mobile-Phones-Querini-Grillo/729b220b3f2de47f32c9454cd3814627fef141e0
- Querini & Italiano, "Color Classifiers for 2D Color Barcodes", FedCSIS 2013: https://annals-csis.org/Volume_1/pliks/67.pdf
- Querini & Italiano, "Reliability and Data Density in High Capacity Color Barcodes", ComSIS 2014: https://www.comsis.org/pdf.php?id=mm067-1308
- HCC2D Code Specification v0.9.0 (M. Querini): https://hcc2d.com/en/spec ; site: https://hcc2d.com/en
- marco-querini/hcc2d-cli-c-encoder: https://github.com/marco-querini/hcc2d-cli-c-encoder ; streamer: https://github.com/marco-querini/hcc2d-cli-c-streamer
- Bulan & Sharma, IEEE TIP 2011 (listing): https://www.researchgate.net/publication/47793929_High_Capacity_Color_Barcodes_Per_Channel_Data_Encoding_via_Orientation_Modulation_in_Elliptical_Dot_Arrays
- Blasinski, Bulan, Sharma, IEEE TIP 2013 (listing): https://www.semanticscholar.org/paper/Per-Colorant-Channel-Color-Barcodes-for-Mobile-An-Blasinski-Bulan/0df9838dfb97132f644021acc7a7baf05a05b77d ; https://stanford.edu/~hblasins/publications.html
- US 9,111,186 B2, "Color barcodes for mobile applications: a per channel framework": https://patents.google.com/patent/US9111186B2/en
- US 8,100,330 B2 (Xerox), colorant/channel correspondence: https://patents.google.com/patent/US8100330B2/en
- Yang, Xu, Deng, Loy, Lau, "Robust and Fast Decoding of High-Capacity Color QR Codes...", IEEE TIP 2018: https://pubmed.ncbi.nlm.nih.gov/30028700/ ; arXiv: https://ar5iv.labs.arxiv.org/html/1704.06447
- HiQ GitHub: https://github.com/cuhk-mobitec/HiQ-Robust-and-Fast-Decoding-of-High-Capacity-Color-QR-Codes
- Hao, Zhou, Xing, "COBRA", MobiSys 2012: https://dl.acm.org/doi/10.1145/2307636.2307645 ; preview: https://www.yumpu.com/en/document/view/4350371/cobra-color-barcode-streaming-for-smartphone-systems
- Hu et al., "Strata", MobiCom 2014: https://dl.acm.org/doi/10.1145/2639108.2639132
- RDCode, MobiCom 2014: https://dl.acm.org/doi/10.1145/2639108.2639135
- PiCode, IEEE TIP 2016: https://researchportal.hkust.edu.hk/en/publications/picode-a-new-picture-embedding-2d-barcode/
- Melgar et al., "CQR codes", ICCE-Berlin 2012 (listing): https://www.researchgate.net/publication/261075725_CQR_codes_Colored_quick-response_codes
- Melgar et al., "A High Density Colored 2D-Barcode: CQR Code-9", SIBGRAPI 2016 slides: https://pdfs.semanticscholar.org/95c7/fe455a084b0f0ce9923e996652156c1f7998.pdf
- US 7,020,327 B2 (Colorzip ColorCode): https://patents.google.com/patent/US7020327B2/en ; history: https://free-barcode.com/barcode/barcode-history/history-colorcode-colorzip.asp
- US 7,210,631 B2 and US 7,051,935 B2 (ImageID / Sali & Lax): https://patents.google.com/patent/US7210631B2/en ; https://patents.google.com/patent/US7051935B2/en
- US 2015/0347886 A1 (Konica Minolta): https://patents.google.com/patent/US20150347886A1/en
- Ultracode: https://www.barcode.ro/tutorials/barcodes/ultracode.html ; https://github.com/bwipp/postscriptbarcode/wiki/Ultracode
- ChromoCode: http://chromocode.com/chromocode-description.php (unreachable in session)
- PixNet, MobiCom 2010: https://people.csail.mit.edu/nabeel/pixnet-mobicom10.pdf
- Denso Wave Frame QR: https://www.qrcode.com/en/codes/frameqr.html
- Han Xin Code: https://en.wikipedia.org/wiki/Han_Xin_code ; https://www.iso.org/standard/69321.html
- Survey, "Color Barcodes from Debut to Present" (Alphanumeric Journal, 2023): https://www.alphanumericjournal.com/article/color-barcodes-from-debut-to-present-a-broad-survey-on-the-state-of-the-art
- ColorZXing.Net: https://github.com/HainanZhao/ColorZXing.Net
- tmk3qr: https://github.com/iladshyan/tmk3qr
- cimbar: https://github.com/sz3/cimbar
- CQRC (styling only): https://github.com/yxpil/CQRC ; GitHub topic color-qr: https://github.com/topics/color-qr
- Bayer CFA / blue channel sampling: https://www.strollswithmydog.com/bayer-cfa-effect-on-sharpness/
