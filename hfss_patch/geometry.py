"""Parametric geometry definition (pure Python, no AEDT).

Coordinates: patch centred on origin, GND sheet at z=0, patch/feed at z=h,
microstrip feed enters from the -y board edge where the wave port sits.
All primitives are written as AEDT design-variable expressions so Optimetrics
sweeps of W/L/y0/gap/Wf regenerate the model; `evaluate` resolves them
numerically so the same definitions can be checked without AEDT.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from .config import JobConfig

Vec3 = tuple[str, str, str]


@dataclass(frozen=True)
class Box:
    name: str
    origin: Vec3
    sizes: Vec3
    material: str


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in the XY plane (unambiguous origin/size order)."""

    name: str
    origin: Vec3
    sizes: tuple[str, str]


@dataclass(frozen=True)
class Polygon:
    """Closed, covered polyline — used where XZ/YZ rectangle axis order would be ambiguous."""

    name: str
    points: tuple[Vec3, ...]


@dataclass(frozen=True)
class Model:
    variables: dict[str, float]  # name -> value in mm (dimensionless for factors)
    substrate: Box
    airbox: Box
    gnd: Rect
    patch: Rect
    notch: Rect
    feed: Rect
    port_sheet: Polygon
    port_int_line: tuple[Vec3, Vec3]
    conductor_name: str = "Patch"
    port_name: str = "P1"


def variables(cfg: JobConfig) -> dict[str, float]:
    p, b, s = cfg.patch, cfg.board, cfg.substrate
    return {
        "W": p.W,
        "L": p.L,
        "y0": p.y0,
        "gap": p.gap,
        "Wf": p.Wf,
        "h": s.h,
        "Wsub": b.Wsub,
        "Lsub": b.Lsub,
        "air": cfg.air,
        "port_w": cfg.port.w_factor * p.Wf,
        "port_h": cfg.port.h_factor * s.h,
    }


def build_model(cfg: JobConfig) -> Model:
    return Model(
        variables=variables(cfg),
        substrate=Box("Substrate", ("-Wsub/2", "-Lsub/2", "0"), ("Wsub", "Lsub", "h"), cfg.substrate.material),
        # Port face (y=-Lsub/2) is flush with the air box so the wave port lies on the outer boundary.
        airbox=Box("AirBox", ("-Wsub/2-air", "-Lsub/2", "-air"), ("Wsub+2*air", "Lsub+air", "h+2*air"), "vacuum"),
        gnd=Rect("GND", ("-Wsub/2", "-Lsub/2", "0"), ("Wsub", "Lsub")),
        patch=Rect("Patch", ("-W/2", "-L/2", "h"), ("W", "L")),
        notch=Rect("Notch", ("-(Wf/2+gap)", "-L/2", "h"), ("Wf+2*gap", "y0")),
        feed=Rect("Feed", ("-Wf/2", "-Lsub/2", "h"), ("Wf", "Lsub/2-L/2+y0")),
        port_sheet=Polygon(
            "P1_sheet",
            (
                ("-port_w/2", "-Lsub/2", "0"),
                ("port_w/2", "-Lsub/2", "0"),
                ("port_w/2", "-Lsub/2", "port_h"),
                ("-port_w/2", "-Lsub/2", "port_h"),
            ),
        ),
        port_int_line=(("0", "-Lsub/2", "0"), ("0", "-Lsub/2", "h")),
    )


# --- safe numeric evaluation of variable expressions --------------------------------

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluate(expr: str, env: dict[str, float]) -> float:
    """Evaluate an AEDT-style arithmetic expression (+-*/, parentheses, names) in mm."""

    def _ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise KeyError(f"undefined variable {node.id!r} in {expr!r}")
            return env[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
            return _UNOPS[type(node.op)](_ev(node.operand))
        raise ValueError(f"unsupported expression element in {expr!r}")

    return _ev(ast.parse(expr, mode="eval"))


def with_units(expr: str, unit: str = "mm") -> str:
    """Plain numbers need explicit units for AEDT; variable expressions already carry them."""
    try:
        return f"{float(expr)}{unit}"
    except ValueError:
        return expr


def bbox(prim: Box | Rect, env: dict[str, float]) -> tuple[tuple[float, float], ...]:
    """Numeric (min, max) per axis; Rect is treated as zero-thickness in z."""
    o = [evaluate(e, env) for e in prim.origin]
    sz = [evaluate(e, env) for e in prim.sizes] + ([0.0] if isinstance(prim, Rect) else [])
    return tuple((min(a, a + d), max(a, a + d)) for a, d in zip(o, sz))



def check_model(model: Model, tol: float = 1e-9) -> list[str]:
    """Topology checks that AEDT would only reveal as a failed/meaningless solve."""
    env = model.variables
    errs: list[str] = []
    sub = bbox(model.substrate, env)
    air = bbox(model.airbox, env)
    patch = bbox(model.patch, env)
    notch = bbox(model.notch, env)
    feed = bbox(model.feed, env)

    def inside(inner, outer, axes=(0, 1, 2)) -> bool:
        return all(outer[a][0] - tol <= inner[a][0] and inner[a][1] <= outer[a][1] + tol for a in axes)

    if not inside(patch, sub, (0, 1)):
        errs.append("patch exceeds substrate")
    if not inside(notch, patch, (0, 1)):
        errs.append("inset notch exceeds patch")
    if not inside(sub, air):
        errs.append("substrate exceeds air box")
    if abs(feed[1][0] - sub[1][0]) > tol or abs(air[1][0] - sub[1][0]) > tol:
        errs.append("feed start, substrate edge and air-box face must coincide at the port plane")
    if abs(feed[1][1] - notch[1][1]) > tol:
        errs.append("feed must end at the inset depth (closed end of the notch)")
    if feed[0][1] - feed[0][0] >= notch[0][1] - notch[0][0]:
        errs.append("feed must be narrower than notch")

    pts = [[evaluate(e, env) for e in p] for p in model.port_sheet.points]
    xs, ys, zs = zip(*pts)
    if max(ys) - min(ys) > tol or abs(ys[0] - sub[1][0]) > tol:
        errs.append("port sheet must lie in the y=-Lsub/2 plane")
    if min(xs) < air[0][0] - tol or max(xs) > air[0][1] + tol or max(zs) > air[2][1] + tol:
        errs.append("port sheet exceeds air-box face")
    if abs(min(zs)) > tol:
        errs.append("port sheet must touch GND (z=0)")
    if min(xs) > feed[0][0] or max(xs) < feed[0][1] or max(zs) <= env["h"]:
        errs.append("port sheet must enclose the feed line cross-section")
    return errs
