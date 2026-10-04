"""Analytic patch model vs. Balanis, Antenna Theory 4th ed., Examples 14.1 / 14.3 (10 GHz, er 2.2, h 1.588 mm)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hfss_patch.analytic import bessel_j0, design_patch, microstrip_width, microstrip_z0, resonant_frequency
from hfss_patch.config import load_config

CFG = Path(__file__).resolve().parents[1] / "hfss_patch" / "configs" / "patch_2g4_fr4.yaml"


def test_balanis_example():
    d = design_patch(10.0, 2.2, 1.588)
    assert d.W_mm == pytest.approx(11.86, abs=0.01)
    assert d.eps_eff == pytest.approx(1.972, abs=0.001)
    assert d.dL_mm == pytest.approx(0.81, abs=0.01)
    assert d.L_mm == pytest.approx(9.06, abs=0.01)
    assert d.G1_S == pytest.approx(1.57e-3, rel=0.01)
    assert d.y0_mm == pytest.approx(3.126, abs=0.01)


def test_bessel_j0():
    assert bessel_j0(0.0) == pytest.approx(1.0)
    assert bessel_j0(2.404825557695773) == pytest.approx(0.0, abs=1e-9)  # first zero


@pytest.mark.parametrize("er,h", [(4.4, 1.6), (3.55, 0.813), (2.2, 0.787)])
def test_microstrip_synthesis_roundtrip(er, h):
    w = microstrip_width(50.0, h * 1e-3, er)
    assert microstrip_z0(w, h * 1e-3, er)[0] == pytest.approx(50.0, abs=0.01)


def test_fr4_50ohm_width():
    assert microstrip_width(50.0, 1.6e-3, 4.4) * 1e3 == pytest.approx(3.06, abs=0.05)


def test_resonance_inverse_consistent():
    d = design_patch(2.4, 4.4, 1.6)
    assert resonant_frequency(d.L_mm, d.W_mm, 4.4, 1.6) == pytest.approx(2.4, rel=1e-9)


def test_job_config_matches_analytic_design():
    cfg = load_config(CFG)
    d = design_patch(cfg.setup.f0, cfg.substrate.er, cfg.substrate.h)
    assert cfg.patch.W == pytest.approx(d.W_mm, abs=0.1)
    assert cfg.patch.L == pytest.approx(d.L_mm, abs=0.1)
    assert cfg.patch.y0 == pytest.approx(d.y0_mm, abs=0.1)
    assert cfg.patch.Wf == pytest.approx(d.Wf_mm, abs=0.05)
    y0 = next(p for p in cfg.parametrics if p.variable == "y0")
    assert y0.start < d.y0_mm < y0.stop


def test_invalid_inputs():
    with pytest.raises(ValueError):
        design_patch(0, 4.4, 1.6)
