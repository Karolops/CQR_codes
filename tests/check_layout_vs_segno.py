"""Cross-validate cqr.layout against the segno QR encoder's internals.

Checks for all 40 versions:
  * alignment pattern centre positions,
  * the number of free (data) modules,
  * the exact data placement order (we place a known codeword sequence with
    segno.encoder.add_codewords and read it back using our data_order),
  * format / version BCH words against segno's tables.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from segno import encoder, consts
from cqr import layout, bch


def main() -> int:
    errs = 0
    for v in range(1, 41):
        L = layout.get_layout(v)
        size = L.size
        seg_pos = list(consts.ALIGNMENT_POS[v - 2]) if v >= 2 else []
        if seg_pos != layout.alignment_positions(v):
            print("ALIGN MISMATCH", v, seg_pos, layout.alignment_positions(v)); errs += 1

        def fresh():
            mm = encoder.make_matrix(size, size, reserve_regions=True, add_timing=True)
            encoder.add_finder_patterns(mm, size, size)
            encoder.add_alignment_patterns(mm, size, size)
            return mm
        m = fresh()
        arr = np.array([[(-1 if x is None else x) for x in row] for row in m])
        # segno uses 0x2 for not-yet-set modules; after drawing finders and
        # alignment patterns the remaining 2s are exactly the data modules.
        free = (arr == 2)
        if free.sum() != L.n_data_modules:
            print("DATA MODULE COUNT MISMATCH", v, int(free.sum()), L.n_data_modules); errs += 1

        # Placement order: fill with a pseudo-random codeword sequence through segno
        nbits = L.n_data_modules
        ncw = nbits // 8
        rng = np.random.default_rng(v)
        cws = rng.integers(0, 256, size=ncw, dtype=np.uint8)
        m2 = fresh()
        bitseq = [int(b) for b in np.unpackbits(cws)]
        encoder.add_codewords(m2, bitseq, v)
        arr2 = np.array([[(-1 if x is None else x) for x in row] for row in m2])
        bits = []
        for (r, c) in L.data_order[:ncw * 8]:
            bits.append(int(arr2[r, c]))
        got = np.packbits(np.array(bits, dtype=np.uint8))
        if not np.array_equal(got, cws):
            nbad = int(np.sum(got != cws))
            print("PLACEMENT ORDER MISMATCH", v, "bad codewords:", nbad); errs += 1

        if v >= 7 and bch.encode_version(v) != consts.VERSION_INFO[v - 7]:
            print("VERSION BCH MISMATCH", v); errs += 1

    fmt_ok = True
    for ec_bits, ec_idx in ((1, 0), (0, 1), (3, 2), (2, 3)):
        for mask in range(8):
            ours = bch.encode_format((ec_bits << 3) | mask)
            theirs = consts.FORMAT_INFO[(ec_bits << 3) | mask]
            if ours != theirs:
                fmt_ok = False
                print("FORMAT BCH MISMATCH", ec_bits, mask, ours, theirs)
    print("format BCH matches segno:", fmt_ok)
    # BCH decoding round trips with injected errors
    for d in range(32):
        w = bch.encode_format(d)
        for e in (0, 0b1, 0b101, 0b10000000000001):
            got = bch.decode_format(w ^ e)
            assert got is not None and got[0] == d, (d, e, got)
    for v in range(7, 41):
        w = bch.encode_version(v)
        for e in (0, 0b1, 0b1001, 0b100000000000000001):
            got = bch.decode_version(w ^ e)
            assert got is not None and got[0] == v, (v, e, got)
    print("data modules V1..V5,V40:", [layout.get_layout(v).n_data_modules for v in (1, 2, 3, 4, 5, 40)])
    print("errors:", errs)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
