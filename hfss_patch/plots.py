"""Report figures (matplotlib, Agg, print/light theme). Labels in English to avoid CJK font dependence."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .config import JobConfig  # noqa: E402
from .postprocess import ISM_BAND_GHZ, PlaneCut, S11Metrics  # noqa: E402

# Validated categorical order (dataviz reference palette, light mode) — fixed order, never cycled.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
BAND_FILL = "#f0efec"
SEQ_BLUE = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#2a78d6", "#1c5cab", "#0d366b"])
DPI = 200

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.fontsize": 8,
        "legend.frameon": False,
        "lines.linewidth": 1.6,
        "font.family": "DejaVu Sans",
    }
)


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def _despine(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def geometry_figure(cfg: JobConfig, path: Path) -> Path:
    p, b = cfg.patch, cfg.board
    fig, ax = plt.subplots(figsize=(5.2, 5.6))
    ax.add_patch(Rectangle((-b.Wsub / 2, -b.Lsub / 2), b.Wsub, b.Lsub, fc=BAND_FILL, ec=MUTED, lw=1))
    ax.add_patch(Rectangle((-p.W / 2, -p.L / 2), p.W, p.L, fc="#86b6ef", ec=SERIES[0], lw=1.2))
    ax.add_patch(Rectangle((-(p.Wf / 2 + p.gap), -p.L / 2), p.Wf + 2 * p.gap, p.y0, fc=BAND_FILL, ec="none"))
    ax.add_patch(
        Rectangle((-p.Wf / 2, -b.Lsub / 2), p.Wf, b.Lsub / 2 - p.L / 2 + p.y0, fc="#86b6ef", ec=SERIES[0], lw=1.2)
    )

    def dim(x0, y0, x1, y1, text, off=(0, 0), rot=0):
        ax.annotate("", (x0, y0), (x1, y1), arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.8))
        ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], text, color=INK, fontsize=8, ha="center", va="center",
                rotation=rot)

    dim(-p.W / 2, p.L / 2 + 3, p.W / 2, p.L / 2 + 3, f"W = {p.W:.2f}", (0, 2))
    dim(p.W / 2 + 3, -p.L / 2, p.W / 2 + 3, p.L / 2, f"L = {p.L:.2f}", (3, 0), 90)
    dim(-p.W / 2 - 3, -p.L / 2, -p.W / 2 - 3, -p.L / 2 + p.y0, f"y0 = {p.y0:.2f}", (-3, 0), 90)
    dim(-b.Wsub / 2, b.Lsub / 2 + 3, b.Wsub / 2, b.Lsub / 2 + 3, f"{b.Wsub:.0f}", (0, 2))
    dim(-b.Wsub / 2 - 4, -b.Lsub / 2, -b.Wsub / 2 - 4, b.Lsub / 2, f"{b.Lsub:.0f}", (-3, 0), 90)
    ax.text(0, -b.Lsub / 2 - 4, f"Port 1 (50 Ω, Wf = {p.Wf:.2f}, gap = {p.gap:.2f})", ha="center", fontsize=8, color=INK2)
    ax.set_xlim(-b.Wsub / 2 - 12, b.Wsub / 2 + 8)
    ax.set_ylim(-b.Lsub / 2 - 8, b.Lsub / 2 + 9)
    ax.set_aspect("equal")
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title(f"Top view — substrate εr {cfg.substrate.er}, h {cfg.substrate.h} mm (dimensions in mm)")
    _despine(ax)
    return _save(fig, path)


def s11_figure(f: np.ndarray, s: np.ndarray, m: S11Metrics, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.axvspan(*ISM_BAND_GHZ, color=BAND_FILL, lw=0)
    ax.text(sum(ISM_BAND_GHZ) / 2, 0.03, "ISM band", transform=ax.get_xaxis_transform(), ha="center",
            va="bottom", fontsize=7, color=INK2)
    ax.axhline(-10, color=MUTED, lw=0.8, ls="--")
    ax.plot(f, s, color=SERIES[0], lw=1.8)
    ax.plot([m.f_res_ghz], [m.s11_min_db], "o", ms=5, color=SERIES[0], mec=SURFACE, mew=1.5)
    ax.annotate(f"{m.f_res_ghz:.3f} GHz, {m.s11_min_db:.1f} dB", (m.f_res_ghz, m.s11_min_db), (8, 4),
                textcoords="offset points", fontsize=8, color=INK)
    ax.set_xlabel("Frequency [GHz]")
    ax.set_ylabel("|S11| [dB]")
    ax.set_title("Return loss |S11|")
    ax.set_xlim(f.min(), f.max())
    ax.set_ylim(min(-40, float(np.nanmin(s)) - 2), 0)
    ax.grid(True, axis="y")
    _despine(ax)
    return _save(fig, path)


def smith_figure(f: np.ndarray, z: np.ndarray, f_res: float, path: Path, z0: float = 50.0) -> Path:
    g = (z - z0) / (z + z0)
    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    t = np.linspace(0, 2 * np.pi, 400)
    ax.plot(np.cos(t), np.sin(t), color=MUTED, lw=0.8)
    for r in (0.2, 0.5, 1, 2, 5):
        ax.plot(r / (1 + r) + np.cos(t) / (1 + r), np.sin(t) / (1 + r), color=GRID, lw=0.6)
    for x in (0.2, 0.5, 1, 2, 5):
        for sgn in (1, -1):
            c = 1 + 1j * sgn / x
            pts = c + np.exp(1j * t) / x
            pts[np.abs(pts) > 1.0001] = np.nan  # clip to the unit circle, keep the arc continuous
            ax.plot(pts.real, pts.imag, color=GRID, lw=0.6)
    ax.axhline(0, color=GRID, lw=0.6)
    ax.plot(g.real, g.imag, color=SERIES[0], lw=1.6)
    i = int(np.argmin(np.abs(f - f_res)))
    ax.plot(g.real[i], g.imag[i], "o", ms=5, color=SERIES[0], mec=SURFACE, mew=1.5)
    ax.annotate(f"{f_res:.3f} GHz\nZ = {z[i].real:.1f}{z[i].imag:+.1f}j Ω", (g.real[i], g.imag[i]), (8, -18),
                textcoords="offset points", fontsize=8, color=INK)
    ax.text(g.real[0], g.imag[0], f" {f[0]:.1f} GHz", fontsize=7, color=INK2)
    ax.text(g.real[-1], g.imag[-1], f" {f[-1]:.1f} GHz", fontsize=7, color=INK2)
    ax.set_aspect("equal")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.axis("off")
    ax.set_title(f"Smith chart (Z0 = {z0:.0f} Ω)")
    return _save(fig, path)


def pattern_figure(cuts: dict[str, PlaneCut], path: Path, floor_db: float = -25.0) -> Path:
    fig = plt.figure(figsize=(6.6, 3.6))
    peak = max(c.gain_dbi.max() for c in cuts.values())
    top = np.ceil(peak / 5) * 5
    for k, (label, key) in enumerate((("E-plane (φ = 90°)", "E"), ("H-plane (φ = 0°)", "H"))):
        ax = fig.add_subplot(1, 2, k + 1, projection="polar")
        c = cuts[key]
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.plot(np.radians(c.angle_deg), np.clip(c.gain_dbi, floor_db, None), color=SERIES[0], lw=1.6,
                label="Total gain")
        if c.cross_dbi is not None:
            ax.plot(np.radians(c.angle_deg), np.clip(c.cross_dbi, floor_db, None), color=SERIES[1], lw=1.2,
                    ls="--", label="Cross-pol (L3X)")
        ax.set_rlim(floor_db, top)
        ax.set_rticks(np.arange(floor_db + 5, top + 0.1, 10))
        ax.tick_params(labelsize=7)
        ax.grid(color=GRID, lw=0.6)
        ax.set_title(label, fontsize=10, pad=12)
        if k == 1:
            ax.legend(loc="lower right", bbox_to_anchor=(1.25, -0.12))
    fig.suptitle("Gain [dBi] at design frequency", fontsize=11, color=INK)
    return _save(fig, path)


def gain3d_figure(phi: np.ndarray, theta: np.ndarray, gain: np.ndarray, path: Path) -> Path:
    ph_u, th_u = np.unique(phi), np.unique(theta)
    grid = np.full((len(th_u), len(ph_u)), np.nan)
    ip = np.searchsorted(ph_u, phi)
    it = np.searchsorted(th_u, theta)
    grid[it, ip] = gain
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    vmax = float(np.nanmax(grid))
    im = ax.pcolormesh(ph_u, th_u, grid, cmap=SEQ_BLUE, vmin=vmax - 20, vmax=vmax, shading="nearest")
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("Total gain [dBi]", fontsize=8, color=INK2)
    cb.ax.tick_params(labelsize=7)
    ax.set_xlabel("φ [deg]")
    ax.set_ylabel("θ [deg]")
    ax.invert_yaxis()
    ax.set_title("3D gain map (θ = 0° is broadside)")
    return _save(fig, path)


def parametric_figure(var: str, curves: dict[float, tuple[np.ndarray, np.ndarray]], nominal: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.axvspan(*ISM_BAND_GHZ, color=BAND_FILL, lw=0)
    ax.axhline(-10, color=MUTED, lw=0.8, ls="--")
    for i, (v, (f, s)) in enumerate(sorted(curves.items())):
        color = SERIES[i % len(SERIES)] if i < len(SERIES) else MUTED
        lw = 2.2 if np.isclose(v, nominal) else 1.3
        ax.plot(f, s, color=color, lw=lw, label=f"{var} = {v:g} mm" + (" (nominal)" if np.isclose(v, nominal) else ""))
    ax.set_xlabel("Frequency [GHz]")
    ax.set_ylabel("|S11| [dB]")
    ax.set_title(f"Parametric sweep: {var}")
    ax.set_ylim(-40, 0)
    ax.grid(True, axis="y")
    ax.legend(loc="lower right", ncol=2)
    _despine(ax)
    return _save(fig, path)


def compare_s11_figure(series: list[tuple[str, np.ndarray, np.ndarray]], path: Path) -> Path:
    """Overlay |S11| of design alternatives; categorical order fixed (baseline = slot 1)."""
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.axvspan(*ISM_BAND_GHZ, color=BAND_FILL, lw=0)
    ax.text(sum(ISM_BAND_GHZ) / 2, 0.03, "ISM band", transform=ax.get_xaxis_transform(), ha="center",
            va="bottom", fontsize=7, color=INK2)
    ax.axhline(-10, color=MUTED, lw=0.8, ls="--")
    for i, (label, f, s) in enumerate(series):
        ax.plot(f, s, color=SERIES[i], lw=1.8, label=label)
    ax.set_xlabel("Frequency [GHz]")
    ax.set_ylabel("|S11| [dB]")
    ax.set_title("|S11| — substrate comparison")
    ax.set_ylim(-40, 0)
    ax.grid(True, axis="y")
    ax.legend(loc="lower left")
    _despine(ax)
    return _save(fig, path)
