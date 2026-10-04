"""Synthetic result set in PyAEDT CSV format — for pipeline tests and report previews ONLY.

Physics is deliberately simple (parallel-RLC port impedance, cavity-model-like
pattern) but parameterised from the analytic design so the numbers are plausible.
Everything written here is tagged SYNTHETIC in run_summary.json; report.py
watermarks any report built from it. Never deliver these numbers to a customer.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from .analytic import C0, design_patch, resonant_frequency
from .config import JobConfig

SYNTHETIC_TAG = "SYNTHETIC"


def _write(path: Path, header: list[str], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(header)
        w.writerows(rows)


def _zin(f: np.ndarray, f0: float, r: float, q: float, x_feed: float = 4.0) -> np.ndarray:
    return r / (1 + 1j * q * (f / f0 - f0 / f)) + 1j * x_feed * f / f0


def _s11_db(z: np.ndarray, z0: float = 50.0) -> np.ndarray:
    return 20 * np.log10(np.abs((z - z0) / (z + z0)))


def _q_total(cfg: JobConfig) -> tuple[float, float]:
    """(Q_total, radiation efficiency) from the lossless BW estimate plus dielectric loss."""
    d = design_patch(cfg.setup.f0, cfg.substrate.er, cfg.substrate.h)
    q_rad = 1 / (math.sqrt(2) * d.bw_vswr2_pct / 100)
    q_d = 1 / cfg.substrate.tand if cfg.substrate.tand > 0 else math.inf
    q = 1 / (1 / q_rad + 1 / q_d)
    return q, q / q_rad


def _r_res(cfg: JobConfig, L: float, y0: float) -> float:
    d = design_patch(cfg.setup.f0, cfg.substrate.er, cfg.substrate.h)
    return d.Rin_edge_ohm * math.cos(math.pi * y0 / L) ** 2


def _f_res(cfg: JobConfig, L: float, gap: float) -> float:
    # HFSS typically lands ~1 % below the TL model; the inset notch lowers it a little more.
    return resonant_frequency(L, cfg.patch.W, cfg.substrate.er, cfg.substrate.h) * (0.99 - 0.002 * (gap - 1.0))


def _pattern_db(theta: np.ndarray, phi: np.ndarray, cfg: JobConfig, g0_dbi: float):
    k0 = 2 * math.pi * cfg.setup.f0 * 1e9 / C0
    W, L = cfg.patch.W * 1e-3, cfg.patch.L * 1e-3
    th, ph = np.radians(theta), np.radians(phi)
    st = np.sin(th)
    x = k0 * W / 2 * st * np.cos(ph)
    sinc = np.where(np.abs(x) < 1e-9, 1.0, np.sin(x) / np.where(np.abs(x) < 1e-9, 1, x))
    # finite-ground roll-off toward the horizon (~-7 dB at theta=90 in the E-plane)
    f_e = np.cos(k0 * L / 2 * st * np.sin(ph)) ** 2 * (0.35 + 0.65 * np.cos(th) ** 2)
    f_h = (sinc * np.abs(np.cos(th))) ** 2
    shape = np.sin(ph) ** 2 * f_e + np.cos(ph) ** 2 * f_h * 0.98 + 0.02
    # back hemisphere: mirror of the front lobe, attenuated toward theta=180 (continuous at the horizon)
    th_m = np.radians(180.0 - np.minimum(theta, 180.0))
    x_m = k0 * W / 2 * np.sin(th_m) * np.cos(ph)
    sinc_m = np.where(np.abs(x_m) < 1e-9, 1.0, np.sin(x_m) / np.where(np.abs(x_m) < 1e-9, 1, x_m))
    shape_m = (np.sin(ph) ** 2 * np.cos(k0 * L / 2 * np.sin(th_m) * np.sin(ph)) ** 2 * (0.35 + 0.65 * np.cos(th_m) ** 2)
               + np.cos(ph) ** 2 * (sinc_m * np.cos(th_m)) ** 2 * 0.98 + 0.02)
    floor = 10 ** (-17 / 10)
    shape = np.where(theta <= 90, shape, shape_m * (floor + (1 - floor) * np.sin(th) ** 4))
    g = g0_dbi + 10 * np.log10(np.clip(shape, 1e-6, None))
    cross = g - 22 + 6 * np.abs(np.sin(2 * ph))
    co = 10 * np.log10(np.clip(10 ** (g / 10) - 10 ** (cross / 10), 1e-9, None))
    return g, co, cross


def write_synthetic_results(cfg: JobConfig, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    st, p = cfg.setup, cfg.patch
    q, eff = _q_total(cfg)
    f = np.round(np.arange(st.sweep_start, st.sweep_stop + st.sweep_step / 2, st.sweep_step), 6)

    f0 = _f_res(cfg, p.L, p.gap)
    z = _zin(f, f0, _r_res(cfg, p.L, p.y0), q)
    gamma = np.abs((z - 50) / (z + 50))
    _write(
        out / "s11.csv",
        ["Freq [GHz]", "dB(S(P1,P1))", "re(Z(P1,P1)) [ohm]", "im(Z(P1,P1)) [ohm]", "VSWR(P1)"],
        zip(f, _s11_db(z), z.real, z.imag, (1 + gamma) / (1 - gamma)),
    )

    directivity_dbi = 6.6
    g0 = directivity_dbi + 10 * math.log10(eff)
    theta = np.arange(0, 180.0 + 1e-9, cfg.farfield.theta_step)
    rows = []
    for phi in (0.0, 90.0, 180.0, 270.0):
        g, co, cx = _pattern_db(theta, np.full_like(theta, phi), cfg, g0)
        rows += [[phi, t, a, b, c] for t, a, b, c in zip(theta, g, co, cx)]
    _write(out / "farfield_cuts.csv", ["Phi [deg]", "Theta [deg]", "dB(GainTotal)", "dB(GainL3Y)", "dB(GainL3X)"], rows)

    phis = np.arange(0, 360.0, cfg.farfield.phi_step)
    tt, pp = np.meshgrid(theta, phis)
    g3, _, _ = _pattern_db(tt.ravel(), pp.ravel(), cfg, g0)
    _write(out / "farfield_3d.csv", ["Phi [deg]", "Theta [deg]", "dB(GainTotal)"], zip(pp.ravel(), tt.ravel(), g3))

    gpk = 10 ** (g3.max() / 10)
    _write(
        out / "antenna_params.csv",
        ["Freq [GHz]", "PeakGain", "PeakDirectivity", "RadiationEfficiency", "PeakRealizedGain"],
        [[st.f0, gpk, gpk / eff, eff, gpk * (1 - float(np.interp(st.f0, f, gamma)) ** 2)]],
    )

    for pc in cfg.parametrics:
        rows = []
        for v in np.round(np.arange(pc.start, pc.stop + pc.step / 2, pc.step), 6):
            L = v if pc.variable == "L" else p.L
            y0 = v if pc.variable == "y0" else p.y0
            gap = v if pc.variable == "gap" else p.gap
            zz = _zin(f, _f_res(cfg, L, gap), _r_res(cfg, L, y0), q)
            rows += [[v, fi, si] for fi, si in zip(f, _s11_db(zz))]
        _write(out / f"s11_param_{pc.variable}.csv", [f"{pc.variable} [mm]", "Freq [GHz]", "dB(S(P1,P1))"], rows)

    (out / "convergence.prop").write_text(
        "$begin 'ConvergenceData'\n"
        + "".join(
            f"  Pass {i}: Tetrahedra={12000 * 1.35 ** i:.0f}  MaxMagDeltaS={0.4 / 2.1 ** i:.4f}\n" for i in range(1, 8)
        )
        + "$end 'ConvergenceData'\n",
        encoding="utf-8",
    )
    (out / "mesh_stats.ms").write_text("Total number of mesh elements: 57000 (synthetic)\n", encoding="utf-8")
    summary = {
        "status": "ok",
        "data_origin": SYNTHETIC_TAG,
        "aedt_version": SYNTHETIC_TAG,
        "config": cfg.source_path,
        "config_sha256": cfg.sha256,
        "variables_mm": vars(cfg.patch),
        "synthetic_model": {"Q_total": q, "rad_efficiency": eff, "f_res_ghz": f0},
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out
