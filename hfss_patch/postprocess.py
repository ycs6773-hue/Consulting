"""Parse PyAEDT SolutionData CSV exports and extract antenna figures of merit.

CSV format (ansys.aedt.core SolutionData.export_data_to_csv): ';'-delimited,
header = sweep columns ("Freq [GHz]", "Theta [deg]", ...) followed by
expression columns ("dB(S(P1,P1))", "re(Z(P1,P1)) [ohm]", or "<expr> (Real)/(Imag)").
"""

from __future__ import annotations

import csv
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

ISM_BAND_GHZ = (2.400, 2.4835)
_HDR = re.compile(r"^(?P<name>.*?)(?P<part> \((?:Real|Imag)\))?(?: \[(?P<unit>[^\]]*)\])?$")
_FREQ_SCALE = {"hz": 1e-9, "khz": 1e-6, "mhz": 1e-3, "ghz": 1.0, "thz": 1e3}
_LEN_SCALE = {"mm": 1.0, "um": 1e-3, "cm": 10.0, "m": 1e3, "mil": 0.0254, "in": 25.4}


class ResultsError(RuntimeError):
    pass


@dataclass
class Table:
    columns: dict[str, np.ndarray]
    units: dict[str, str]
    source: str = ""

    def col(self, *names: str) -> np.ndarray:
        for n in names:
            if n in self.columns:
                return self.columns[n]
        raise ResultsError(f"{self.source}: none of {names} in {list(self.columns)}")

    def has(self, name: str) -> bool:
        return name in self.columns


def read_table(path: str | Path) -> Table:
    """Read a PyAEDT CSV; frequency columns normalised to GHz, length variables to mm."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
    except OSError as exc:
        raise ResultsError(f"cannot read {path}: {exc}") from exc
    if len(rows) < 2:
        raise ResultsError(f"{path}: no data rows")
    header, body = rows[0], [r for r in rows[1:] if r]
    try:
        data = np.array(body, dtype=float)
    except ValueError as exc:
        raise ResultsError(f"{path}: non-numeric data ({exc})") from exc
    cols: dict[str, np.ndarray] = {}
    units: dict[str, str] = {}
    for i, h in enumerate(header):
        m = _HDR.match(h.strip())
        assert m  # regex always matches
        name = m["name"].strip() + (m["part"] or "")
        unit = (m["unit"] or "").strip()
        v = data[:, i]
        if unit.lower() in _FREQ_SCALE and name.lower().startswith("freq"):
            v, unit = v * _FREQ_SCALE[unit.lower()], "GHz"
        elif unit.lower() in _LEN_SCALE:
            v, unit = v * _LEN_SCALE[unit.lower()], "mm"
        elif unit.lower() == "rad":
            v, unit = np.degrees(v), "deg"
        cols[name] = v
        units[name] = unit
    return Table(cols, units, str(path))


# --- S-parameter metrics -----------------------------------------------------------------


@dataclass
class S11Metrics:
    f_res_ghz: float
    s11_min_db: float
    bw10_lo_ghz: float | None
    bw10_hi_ghz: float | None
    bw10_mhz: float | None
    bw10_pct: float | None
    ism_worst_s11_db: float
    ism_pass: bool
    z_res_ohm: complex | None = None
    vswr_res: float | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        if self.z_res_ohm is not None:
            d["z_res_ohm"] = [self.z_res_ohm.real, self.z_res_ohm.imag]
        return d


def _crossing(f: np.ndarray, y: np.ndarray, i0: int, i1: int, level: float) -> float:
    """Linear interpolation of where y crosses `level` between samples i0 and i1."""
    if y[i1] == y[i0]:
        return float(f[i0])
    return float(f[i0] + (level - y[i0]) * (f[i1] - f[i0]) / (y[i1] - y[i0]))


def s11_metrics(freq_ghz: np.ndarray, s11_db: np.ndarray, band=ISM_BAND_GHZ, level: float = -10.0) -> S11Metrics:
    order = np.argsort(freq_ghz)
    f, s = np.asarray(freq_ghz)[order], np.asarray(s11_db)[order]
    i = int(np.argmin(s))
    lo = hi = None
    if s[i] <= level:
        j = i
        while j > 0 and s[j - 1] <= level:
            j -= 1
        lo = _crossing(f, s, j - 1, j, level) if j > 0 else None
        k = i
        while k < len(s) - 1 and s[k + 1] <= level:
            k += 1
        hi = _crossing(f, s, k, k + 1, level) if k < len(s) - 1 else None
    bw = (hi - lo) * 1e3 if lo is not None and hi is not None else None
    covered = f[0] <= band[0] and f[-1] >= band[1]
    worst = float(np.max(np.interp(np.linspace(*band, 201), f, s))) if covered else math.nan
    return S11Metrics(
        f_res_ghz=float(f[i]),
        s11_min_db=float(s[i]),
        bw10_lo_ghz=lo,
        bw10_hi_ghz=hi,
        bw10_mhz=bw,
        bw10_pct=bw / 1e3 / float(f[i]) * 100 if bw else None,
        ism_worst_s11_db=worst,
        ism_pass=bool(worst <= level),
    )


def s11_from_table(t: Table) -> tuple[S11Metrics, dict[str, np.ndarray]]:
    f = t.col("Freq")
    s = t.col("dB(S(P1,P1))")
    m = s11_metrics(f, s)
    curves = {"freq_ghz": f, "s11_db": s}
    if t.has("re(Z(P1,P1))") and t.has("im(Z(P1,P1))"):
        z = t.col("re(Z(P1,P1))") + 1j * t.col("im(Z(P1,P1))")
        curves["z"] = z
        m.z_res_ohm = complex(np.interp(m.f_res_ghz, f, z.real), np.interp(m.f_res_ghz, f, z.imag))
    if t.has("VSWR(P1)"):
        curves["vswr"] = t.col("VSWR(P1)")
        m.vswr_res = float(np.interp(m.f_res_ghz, f, curves["vswr"]))
    return m, curves


# --- far-field metrics -------------------------------------------------------------------


@dataclass
class PlaneCut:
    angle_deg: np.ndarray  # -180..180 (negative = phi+180 half)
    gain_dbi: np.ndarray
    co_dbi: np.ndarray | None = None
    cross_dbi: np.ndarray | None = None


@dataclass
class PatternMetrics:
    boresight_gain_dbi: float
    peak_gain_cut_dbi: float
    hpbw_e_deg: float | None
    hpbw_h_deg: float | None
    front_to_back_db: float
    xpd_boresight_db: float | None
    extra: dict = field(default_factory=dict)


def full_cut(t: Table, phi: float, expr: str = "dB(GainTotal)") -> tuple[np.ndarray, np.ndarray]:
    """Join theta 0..180 at phi and phi+180 into a -180..180 cut."""
    th, ph, v = t.col("Theta"), t.col("Phi"), t.col(expr)
    a = np.isclose(ph, phi)
    b = np.isclose(ph, (phi + 180) % 360)
    if not a.any():
        raise ResultsError(f"phi={phi} not in {t.source}")
    ang = np.concatenate([-th[b][::-1], th[a]])
    val = np.concatenate([v[b][::-1], v[a]])
    ang, keep = np.unique(ang, return_index=True)
    return ang, val[keep]


def hpbw(angle: np.ndarray, gain_db: np.ndarray) -> float | None:
    """-3 dB beamwidth around the cut maximum (None if the beam never drops 3 dB)."""
    a, g = angle, gain_db
    i = int(np.argmax(g))
    lvl = g[i] - 3.0
    j = i
    while j > 0 and g[j - 1] > lvl:
        j -= 1
    k = i
    while k < len(g) - 1 and g[k + 1] > lvl:
        k += 1
    if j == 0 or k == len(g) - 1:
        return None
    return _crossing(a, g, k, k + 1, lvl) - _crossing(a, g, j - 1, j, lvl)


def cut(t: Table, phi: float) -> PlaneCut:
    a, g = full_cut(t, phi)
    pc = PlaneCut(a, g)
    if t.has("dB(GainL3Y)") and t.has("dB(GainL3X)"):
        pc.co_dbi = full_cut(t, phi, "dB(GainL3Y)")[1]
        pc.cross_dbi = full_cut(t, phi, "dB(GainL3X)")[1]
    return pc


def pattern_metrics(cuts_tbl: Table) -> tuple[PatternMetrics, dict[str, PlaneCut]]:
    """Feed along y => E-plane is phi=90 (yz), H-plane is phi=0 (xz)."""
    cuts = {"E": cut(cuts_tbl, 90.0), "H": cut(cuts_tbl, 0.0)}
    e, h = cuts["E"], cuts["H"]
    bore = float(np.interp(0.0, e.angle_deg, e.gain_dbi))
    back = float(np.interp(180.0, np.abs(e.angle_deg), e.gain_dbi))
    xpd = None
    if e.co_dbi is not None and e.cross_dbi is not None:
        xpd = float(np.interp(0.0, e.angle_deg, e.co_dbi) - np.interp(0.0, e.angle_deg, e.cross_dbi))
    return (
        PatternMetrics(
            boresight_gain_dbi=bore,
            peak_gain_cut_dbi=float(max(e.gain_dbi.max(), h.gain_dbi.max())),
            hpbw_e_deg=hpbw(e.angle_deg, e.gain_dbi),
            hpbw_h_deg=hpbw(h.angle_deg, h.gain_dbi),
            front_to_back_db=bore - back,
            xpd_boresight_db=xpd,
        ),
        cuts,
    )


def peak_from_3d(t: Table) -> tuple[float, float, float]:
    """(peak dBi, theta, phi) from the full 3D gain export."""
    g = t.col("dB(GainTotal)")
    i = int(np.argmax(g))
    return float(g[i]), float(t.col("Theta")[i]), float(t.col("Phi")[i])


def antenna_params(t: Table) -> dict[str, float]:
    """Linear ratios from the 'Antenna Parameters' category -> dB / %."""
    out: dict[str, float] = {}
    for key in ("PeakGain", "PeakDirectivity", "PeakRealizedGain"):
        if t.has(key):
            v = float(t.col(key)[0])
            out[f"{key}_dBi"] = 10 * math.log10(v) if v > 0 else math.nan
    if t.has("RadiationEfficiency"):
        out["RadiationEfficiency_pct"] = float(t.col("RadiationEfficiency")[0]) * 100
    return out


def parametric_summary(t: Table, var: str) -> list[dict[str, float]]:
    """Per swept value: resonance and -10 dB bandwidth."""
    vals = t.col(var)
    rows = []
    for v in np.unique(vals):
        sel = np.isclose(vals, v)
        m = s11_metrics(t.col("Freq")[sel], t.col("dB(S(P1,P1))")[sel])
        rows.append({var: float(v), "f_res_ghz": m.f_res_ghz, "s11_min_db": m.s11_min_db, "bw10_mhz": m.bw10_mhz})
    return rows


def parametric_curves(t: Table, var: str) -> dict[float, tuple[np.ndarray, np.ndarray]]:
    vals = t.col(var)
    out = {}
    for v in np.unique(vals):
        sel = np.isclose(vals, v)
        f, s = t.col("Freq")[sel], t.col("dB(S(P1,P1))")[sel]
        o = np.argsort(f)
        out[float(v)] = (f[o], s[o])
    return out


def tune_parameter(rows: list[dict[str, float]], var: str, f_target_ghz: float) -> float | None:
    """Value of `var` that puts f_res on target, by linear fit of the parametric resonances."""
    pts = [(r[var], r["f_res_ghz"]) for r in rows]
    if len(pts) < 2:
        return None
    x, y = np.array(pts).T
    slope, icpt = np.polyfit(x, y, 1)
    if abs(slope) < 1e-9:
        return None
    return float((f_target_ghz - icpt) / slope)


def read_text_tail(path: Path, n: int = 25) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []
