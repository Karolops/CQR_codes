"""Image-level tests: render -> (simulated camera) -> decode."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from cqr import codec, render
from cqr.decoder import decode_image
from cqr.simulate import CameraParams, simulate

rng = np.random.default_rng(42)


def _payload(n):
    return bytes(rng.integers(0, 256, n, dtype=np.uint8))


@pytest.mark.parametrize("profile", ["rgb111", "rgb222", "rgb333", "rgb444", "mono", "gray4"])
@pytest.mark.parametrize("version", [1, 2, 7, 15])
def test_clean_render_roundtrip(profile, version):
    payload = _payload(codec.capacity(version, "M", profile) // 2)
    sym = codec.encode(payload, ec_level="M", profile=profile, version=version)
    img = render.to_array(sym, module_px=6)
    res = decode_image(img)
    assert res.ok and res.data == payload


@pytest.mark.parametrize("rotation", [0, 37, 90, 180, 263])
def test_rotation_and_mirror(rotation):
    payload = _payload(100)
    sym = codec.encode(payload, ec_level="M", profile="rgb222")
    img = render.to_array(sym, module_px=8)
    cam = simulate(img, CameraParams(module_px=7, rotation_deg=rotation, blur_sigma=0.5, noise_sigma=0.01))
    assert decode_image(cam).data == payload
    assert decode_image(cam[:, ::-1]).data == payload   # mirrored capture


@pytest.mark.parametrize("rotation", [38, 45, 48, 70, 135])
def test_rotation_sweep_with_blur(rotation):
    """Module size measured by axis-aligned scanning is inflated by 1/cos(angle);
    the version estimate must survive any rotation."""
    payload = _payload(200)
    sym = codec.encode(payload, ec_level="M", profile="rgb111", version=6)
    img = render.to_array(sym, module_px=8)
    cam = simulate(img, CameraParams(module_px=5.5, rotation_deg=rotation, tilt=0.1, blur_sigma=0.9,
                                     noise_sigma=0.03, jpeg_quality=80, seed=rotation))
    rep = decode_image(cam, return_report=True)
    assert rep.geometry.version == 6
    assert rep.result.ok and rep.result.data == payload


def test_moderate_camera_conditions_rgb222():
    payload = _payload(300)
    sym = codec.encode(payload, ec_level="M", profile="rgb222")
    img = render.to_array(sym, module_px=8)
    p = CameraParams(module_px=6, rotation_deg=12, tilt=0.15, blur_sigma=0.8, noise_sigma=0.02,
                     color_cast=(1.05, 1.0, 0.85), gamma=1.15, black_level=0.08, white_level=0.92,
                     crosstalk=0.05, jpeg_quality=85, seed=3)
    cam = simulate(img, p)
    rep = decode_image(cam, return_report=True)
    assert rep.result.ok and rep.result.data == payload


def test_harsh_conditions_rgb111_H():
    """Small modules (4.5 px), strong tilt, blur, noise, colour cast, gamma, contrast loss,
    cross-talk and JPEG 75 with 4:2:0 chroma subsampling. (JPEG quality 60 at this module
    size pushes the blue channel past the EC budget - see research/03_design_decisions.md.)"""
    payload = _payload(120)
    sym = codec.encode(payload, ec_level="H", profile="rgb111")
    img = render.to_array(sym, module_px=8)
    p = CameraParams(module_px=4.5, rotation_deg=-20, tilt=0.25, blur_sigma=1.0, noise_sigma=0.05,
                     color_cast=(1.1, 0.95, 0.75), gamma=1.3, black_level=0.15, white_level=0.85,
                     crosstalk=0.12, jpeg_quality=75, seed=7)
    cam = simulate(img, p)
    res = decode_image(cam)
    assert res.ok and res.data == payload


def test_large_symbol_perspective():
    payload = _payload(4000)
    sym = codec.encode(payload, ec_level="M", profile="rgb222")
    img = render.to_array(sym, module_px=6)
    p = CameraParams(module_px=5, rotation_deg=5, tilt=0.12, blur_sigma=0.6, noise_sigma=0.015, seed=11)
    cam = simulate(img, p)
    rep = decode_image(cam, return_report=True)
    assert rep.geometry.version == sym.version
    assert rep.result.ok and rep.result.data == payload


@pytest.mark.parametrize("core_complement", [True, False])
@pytest.mark.parametrize("profile", ["rgb111", "rgb222"])
def test_finder_core_variants(core_complement, profile):
    """Both finder variants decode; the decoder detects which one it sees."""
    payload = _payload(60)
    sym = codec.encode(payload, ec_level="M", profile=profile, version=3, core_complement=core_complement)
    img = render.to_array(sym, module_px=8)
    cam = simulate(img, CameraParams(module_px=6.0, rotation_deg=12, tilt=0.1, blur_sigma=0.8, noise_sigma=0.02,
                                     color_cast=(1.05, 1.0, 0.9), gamma=1.2, jpeg_quality=85, seed=3))
    rep = decode_image(cam, return_report=True)
    assert rep.result.ok and rep.result.data == payload
    assert rep.core_complement == core_complement
    assert ("cyan" in rep.calibration.refs_measured) == core_complement
