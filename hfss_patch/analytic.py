"""Closed-form rectangular patch design (transmission-line model, Balanis ch.14).

Used to (1) seed the HFSS model, (2) sanity-check HFSS results in the report.
Pure Python + math only so it runs anywhere the config does.

References
- C. A. Balanis, Antenna Theory, 4th ed., §14.2 (W, eps_eff, dL, L, G1, G12, inset feed).
- E. O. Hammerstad, "Equations for microstrip circuit design", 1975 (microstrip Z0 / synthesis).
- D. R. Jackson, N. G. Alexopoulos, IEEE TAP 1991 (bandwidth estimate).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

C0 = 299_792_458.0
ETA0 = 376.730313668


@dataclass(frozen=True)
class PatchDesign:
    f0_ghz: float
    er: float
    h_mm: float
    W_mm: float
    eps_eff: float
    dL_mm: float
    L_mm: float
    G1_S: float
    G12_S: float
    Rin_edge_ohm: float  # with mutual conductance (Balanis 14-17)
    Rin_edge_noG12_ohm: float
    y0_mm: float  # inset depth for z0_ohm match
    Wf_mm: float  # microstrip width for z0_ohm
    z0_ohm: float
    bw_vswr2_pct: float  # lossless estimate; substrate loss widens the real BW

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _simpson(f, a: float, b: float, n: int = 2000) -> float:
    n += n % 2
    hstep = (b - a) / n
    s = f(a) + f(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * f(a + i * hstep)
    return s * hstep / 3


def bessel_j0(x: float) -> float:
    """J0(x) = (1/pi) * integral_0^pi cos(x sin t) dt."""
    return _simpson(lambda t: math.cos(x * math.sin(t)), 0.0, math.pi, 400) / math.pi


def patch_width(f0: float, er: float) -> float:
    """Efficient-radiator width [m] (Balanis 14-6)."""
    return C0 / (2 * f0) * math.sqrt(2 / (er + 1))


def eps_effective(er: float, h: float, W: float) -> float:
    """Balanis 14-1, valid for W/h > 1."""
    return (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h / W) ** -0.5


def delta_l(h: float, W: float, eps_eff: float) -> float:
    """Fringing length extension [m] (Hammerstad, Balanis 14-2)."""
    return 0.412 * h * (eps_eff + 0.3) * (W / h + 0.264) / ((eps_eff - 0.258) * (W / h + 0.8))


def _slot_kernel(k0: float, W: float, th: float) -> float:
    c = math.cos(th)
    s = math.sin(th)
    if abs(c) < 1e-12:  # limit sin(a c)/c -> a
        return (k0 * W / 2) ** 2 * s**3
    return (math.sin(k0 * W / 2 * c) / c) ** 2 * s**3


def slot_conductance(f0: float, W: float) -> float:
    """Single radiating slot conductance G1 [S] (Balanis 14-12 integral form)."""
    k0 = 2 * math.pi * f0 / C0
    return _simpson(lambda t: _slot_kernel(k0, W, t), 0.0, math.pi) / (120 * math.pi**2)


def mutual_conductance(f0: float, W: float, L: float) -> float:
    """Mutual conductance G12 [S] between the two slots (Balanis 14-18a)."""
    k0 = 2 * math.pi * f0 / C0
    return _simpson(
        lambda t: _slot_kernel(k0, W, t) * bessel_j0(k0 * L * math.sin(t)), 0.0, math.pi, 600
    ) / (120 * math.pi**2)


def microstrip_z0(w: float, h: float, er: float) -> tuple[float, float]:
    """(Z0 [ohm], eps_eff) of a zero-thickness microstrip (Hammerstad)."""
    u = w / h
    ee = eps_effective(er, h, w) if u >= 1 else (er + 1) / 2 + (er - 1) / 2 * (
        (1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2
    )
    if u <= 1:
        z0 = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        z0 = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0, ee


def microstrip_width(z0: float, h: float, er: float) -> float:
    """Synthesis: width [m] for target Z0 (Wheeler/Hammerstad), refined by bisection on microstrip_z0."""
    a = z0 / 60 * math.sqrt((er + 1) / 2) + (er - 1) / (er + 1) * (0.23 + 0.11 / er)
    u = 8 * math.exp(a) / (math.exp(2 * a) - 2)
    if u > 2:
        b = 377 * math.pi / (2 * z0 * math.sqrt(er))
        u = 2 / math.pi * (b - 1 - math.log(2 * b - 1) + (er - 1) / (2 * er) * (math.log(b - 1) + 0.39 - 0.61 / er))
    lo, hi = u * 0.5, u * 2.0  # Z0 is monotonically decreasing in w
    for _ in range(80):
        mid = (lo + hi) / 2
        if microstrip_z0(mid * h, h, er)[0] > z0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * h


def inset_depth(L: float, rin_edge: float, z0: float) -> float:
    """y0 such that Rin_edge * cos^2(pi y0 / L) = z0 (Balanis 14-20a)."""
    if z0 >= rin_edge:
        return 0.0
    return L / math.pi * math.acos(math.sqrt(z0 / rin_edge))


def design_patch(f0_ghz: float, er: float, h_mm: float, z0_ohm: float = 50.0) -> PatchDesign:
    if f0_ghz <= 0 or er < 1 or h_mm <= 0:
        raise ValueError("need f0>0, er>=1, h>0")
    f0 = f0_ghz * 1e9
    h = h_mm * 1e-3
    W = patch_width(f0, er)
    ee = eps_effective(er, h, W)
    dL = delta_l(h, W, ee)
    L = C0 / (2 * f0 * math.sqrt(ee)) - 2 * dL
    g1 = slot_conductance(f0, W)
    g12 = mutual_conductance(f0, W, L)
    rin = 1 / (2 * (g1 + g12))
    lam0 = C0 / f0
    bw = 3.77 * (er - 1) / er**2 * (W / L) * (h / lam0) * 100
    return PatchDesign(
        f0_ghz=f0_ghz,
        er=er,
        h_mm=h_mm,
        W_mm=W * 1e3,
        eps_eff=ee,
        dL_mm=dL * 1e3,
        L_mm=L * 1e3,
        G1_S=g1,
        G12_S=g12,
        Rin_edge_ohm=rin,
        Rin_edge_noG12_ohm=1 / (2 * g1),
        y0_mm=inset_depth(L, rin, z0_ohm) * 1e3,
        Wf_mm=microstrip_width(z0_ohm, h, er) * 1e3,
        z0_ohm=z0_ohm,
        bw_vswr2_pct=bw,
    )


def resonant_frequency(L_mm: float, W_mm: float, er: float, h_mm: float) -> float:
    """Inverse model: TM010 resonance [GHz] of a patch of length L (for comparing against HFSS)."""
    h, W, L = h_mm * 1e-3, W_mm * 1e-3, L_mm * 1e-3
    ee = eps_effective(er, h, W)
    return C0 / (2 * (L + 2 * delta_l(h, W, ee)) * math.sqrt(ee)) / 1e9


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Transmission-line-model patch design (Balanis)")
    ap.add_argument("--f0", type=float, required=True, help="GHz")
    ap.add_argument("--er", type=float, required=True)
    ap.add_argument("--h", type=float, required=True, help="substrate height, mm")
    ap.add_argument("--z0", type=float, default=50.0)
    a = ap.parse_args(argv)
    print(json.dumps(design_patch(a.f0, a.er, a.h, a.z0).as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
