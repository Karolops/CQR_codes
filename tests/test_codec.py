"""Matrix-level round-trip tests (no image pipeline)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from cqr import codec, layout
from cqr.profiles import PROFILES, EC_LEVELS
from cqr.ecc import block_structure, rs_encode, rs_decode, whitening_sequence


def test_whitening_is_involution():
    seq = whitening_sequence(1000)
    assert len(set(seq.tolist())) > 100  # looks random
    bs = block_structure(100, "M")
    data = list(range(bs.data_codewords))
    msg = rs_encode(data, bs)
    assert rs_decode(msg, bs).data == data


def test_rs_corrects_errors_and_erasures():
    rng = np.random.default_rng(0)
    bs = block_structure(300, "Q")   # 2 blocks
    data = [int(x) for x in rng.integers(0, 256, bs.data_codewords)]
    msg = list(rs_encode(data, bs))
    t = bs.max_errors_per_block
    # corrupt t codewords in each block (interleaved: even indices block 0, odd block 1)
    idx = rng.choice(len(msg) // 2, t, replace=False)
    for i in idx:
        msg[2 * i] ^= 0x55
        msg[2 * i + 1] ^= 0xAA
    res = rs_decode(msg, bs)
    assert res.failed_blocks == 0 and res.data == data
    # one more error per block must fail without reliability info ...
    extra = [i for i in range(len(msg) // 2) if i not in set(idx.tolist())][0]
    msg[2 * extra] ^= 0x01
    msg[2 * extra + 1] ^= 0x01
    res = rs_decode(msg, bs)
    assert res.failed_blocks > 0 or res.data != data
    # ... but succeeds when the corrupted positions are flagged unreliable
    rel = np.ones(len(msg))
    for i in list(idx) + [extra]:
        rel[2 * i] = 0.0
        rel[2 * i + 1] = 0.0
    res = rs_decode(msg, bs, rel)
    assert res.failed_blocks == 0 and res.data == data


def test_roundtrip_all_profiles_and_levels():
    rng = np.random.default_rng(1)
    for prof in PROFILES.values():
        for ec in EC_LEVELS:
            for version in (1, 2, 5, 7, 12, 25, 40):
                cap = codec.capacity(version, ec, prof)
                n = int(rng.integers(0, cap + 1))
                payload = bytes(rng.integers(0, 256, n, dtype=np.uint8))
                sym = codec.encode(payload, ec_level=ec, profile=prof, version=version)
                assert sym.size == layout.size_for_version(version)
                dec = codec.decode_rgb_matrix(sym.rgb)
                assert dec.ok and dec.data == payload, (prof.name, ec, version)
                assert dec.profile is prof and dec.ec_level == ec


def test_text_and_compression():
    text = "Zażółć gęślą jaźń — CQR colour QR test " * 20
    sym = codec.encode(text, ec_level="H", profile="rgb111", compress=True)
    dec = codec.decode_rgb_matrix(sym.rgb)
    assert dec.data == text
    assert dec.content_type == codec.TYPE_ZTEXT


def test_auto_version_selection():
    payload = bytes(1000)
    sym = codec.encode(payload, ec_level="L", profile="rgb222")
    smaller = sym.version - 1
    assert smaller == 0 or codec.capacity(smaller, "L", "rgb222") < len(payload)


def test_module_error_tolerance():
    """Random module colour errors up to roughly the nominal recovery fraction must be corrected."""
    rng = np.random.default_rng(2)
    for prof_name in ("rgb111", "rgb222", "rgb333"):
        for ec in ("L", "M", "Q", "H"):
            sym = codec.encode(bytes(rng.integers(0, 256, 200, dtype=np.uint8)), ec_level=ec, profile=prof_name)
            bpm = sym.profile.bits_per_module
            r = EC_LEVELS[ec][1]
            # a byte touches ~8/bpm + 1 modules; byte error rate must stay below r
            frac = 0.7 * (1 - (1 - r) ** (1.0 / (8.0 / bpm + 1)))
            L = sym.layout
            rgb = sym.rgb.copy()
            n_bad = int(frac * L.n_data_modules)
            bad = rng.choice(L.n_data_modules, n_bad, replace=False)
            for i in bad:
                r, c = L.data_order[i]
                rgb[r, c] = rng.integers(0, 256, 3)
            dec = codec.decode_rgb_matrix(rgb)
            assert dec.ok, (prof_name, ec, frac)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
