"""YAML job configuration: load, type, and validate before AEDT is ever launched."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

C0 = 299_792_458.0  # m/s


class ConfigError(ValueError):
    """Raised when the job configuration is missing keys or physically inconsistent."""


@dataclass(frozen=True)
class ProjectCfg:
    name: str
    design: str
    aedt_version: str
    non_graphical: bool
    cores: int
    output_dir: str


@dataclass(frozen=True)
class SubstrateCfg:
    material: str
    er: float
    tand: float
    h: float


@dataclass(frozen=True)
class PatchCfg:
    W: float
    L: float
    y0: float
    gap: float
    Wf: float


@dataclass(frozen=True)
class BoardCfg:
    Wsub: float
    Lsub: float


@dataclass(frozen=True)
class PortCfg:
    w_factor: float
    h_factor: float


@dataclass(frozen=True)
class SetupCfg:
    f0: float
    max_passes: int
    max_delta_s: float
    sweep_start: float
    sweep_stop: float
    sweep_step: float
    sweep_type: str


@dataclass(frozen=True)
class FarfieldCfg:
    theta_step: float
    phi_step: float


@dataclass(frozen=True)
class ParametricCfg:
    name: str
    variable: str
    start: float
    stop: float
    step: float


@dataclass(frozen=True)
class JobConfig:
    project: ProjectCfg
    substrate: SubstrateCfg
    patch: PatchCfg
    board: BoardCfg
    port: PortCfg
    air: float
    setup: SetupCfg
    farfield: FarfieldCfg
    parametrics: tuple[ParametricCfg, ...] = field(default_factory=tuple)
    source_path: str = ""
    sha256: str = ""

    @property
    def lambda0_mm(self) -> float:
        """Free-space wavelength at the lowest swept frequency (worst case for clearance)."""
        return C0 / (self.setup.sweep_start * 1e9) * 1e3


_SECTIONS: dict[str, type] = {
    "project": ProjectCfg,
    "substrate": SubstrateCfg,
    "patch": PatchCfg,
    "board": BoardCfg,
    "port": PortCfg,
    "setup": SetupCfg,
    "farfield": FarfieldCfg,
}

SWEEP_TYPES = ("Interpolating", "Discrete", "Fast")


def _build(cls: type, raw: Any, section: str) -> Any:
    if not isinstance(raw, dict):
        raise ConfigError(f"[{section}] must be a mapping, got {type(raw).__name__}")
    expected = set(cls.__dataclass_fields__)
    missing = expected - raw.keys()
    unknown = raw.keys() - expected
    if missing:
        raise ConfigError(f"[{section}] missing keys: {sorted(missing)}")
    if unknown:
        raise ConfigError(f"[{section}] unknown keys: {sorted(unknown)}")
    # YAML may parse e.g. aedt_version 2025.1 as float; coerce str-typed fields explicitly.
    values = {k: str(v) if cls.__dataclass_fields__[k].type == "str" else v for k, v in raw.items()}
    try:
        return cls(**values)
    except TypeError as exc:
        raise ConfigError(f"[{section}] {exc}") from exc


def load_config(path: str | Path) -> JobConfig:
    """Load and validate a job YAML. Raises ConfigError on any problem."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"top level of {path} must be a mapping")

    parts = {name: _build(cls, raw.get(name), name) for name, cls in _SECTIONS.items()}
    if "air" not in raw:
        raise ConfigError("missing key: air")
    params = tuple(_build(ParametricCfg, p, f"parametrics[{i}]") for i, p in enumerate(raw.get("parametrics") or []))

    cfg = JobConfig(
        **parts,
        air=float(raw["air"]),
        parametrics=params,
        source_path=str(path.resolve()),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    validate(cfg)
    logger.info("Loaded config %s (sha256=%s)", path, cfg.sha256[:12])
    return cfg


def validate(cfg: JobConfig) -> None:
    """Physical/geometric sanity checks. Collects every problem before raising."""
    errs: list[str] = []
    p, b, s, st = cfg.patch, cfg.board, cfg.substrate, cfg.setup

    for name, val in {**vars(p), **vars(b), "h": s.h, "air": cfg.air, "er": s.er}.items():
        if not isinstance(val, (int, float)) or val <= 0:
            errs.append(f"{name} must be a positive number (got {val!r})")
    if errs:
        raise ConfigError("; ".join(errs))

    if s.er < 1.0:
        errs.append(f"er={s.er} < 1")
    if not 0 <= s.tand < 1:
        errs.append(f"tand={s.tand} out of range [0, 1)")
    if p.y0 >= p.L:
        errs.append(f"inset depth y0={p.y0} must be < L={p.L}")
    if p.Wf + 2 * p.gap >= p.W:
        errs.append(f"inset notch (Wf+2*gap={p.Wf + 2 * p.gap}) must be narrower than W={p.W}")
    if p.W >= b.Wsub or p.L >= b.Lsub:
        errs.append(f"patch {p.W}x{p.L} does not fit board {b.Wsub}x{b.Lsub}")
    port_w = cfg.port.w_factor * p.Wf
    port_h = cfg.port.h_factor * s.h
    if port_w >= b.Wsub:
        errs.append(f"port width {port_w} must be < Wsub={b.Wsub}")
    if port_h >= s.h + cfg.air:
        errs.append(f"port height {port_h} must be < h+air={s.h + cfg.air}")
    if cfg.air < cfg.lambda0_mm / 4:
        errs.append(f"air clearance {cfg.air} mm < lambda0/4={cfg.lambda0_mm / 4:.2f} mm at {st.sweep_start} GHz")
    if not st.sweep_start < st.f0 < st.sweep_stop:
        errs.append(f"f0={st.f0} must lie inside sweep [{st.sweep_start}, {st.sweep_stop}]")
    if st.sweep_step <= 0 or st.sweep_step > st.sweep_stop - st.sweep_start:
        errs.append(f"sweep_step={st.sweep_step} invalid")
    if st.sweep_type not in SWEEP_TYPES:
        errs.append(f"sweep_type={st.sweep_type!r} not in {SWEEP_TYPES}")
    if st.max_passes < 1 or not 0 < st.max_delta_s < 1:
        errs.append("max_passes must be >=1 and 0<max_delta_s<1")
    if cfg.project.cores < 1:
        errs.append("cores must be >= 1")

    sweepable = set(vars(p))
    names: set[str] = set()
    for pc in cfg.parametrics:
        if pc.variable not in sweepable:
            errs.append(f"parametric {pc.name}: variable {pc.variable!r} not in {sorted(sweepable)}")
        if not 0 < pc.start < pc.stop or pc.step <= 0:
            errs.append(f"parametric {pc.name}: need 0<start<stop and step>0")
        if pc.name in names:
            errs.append(f"duplicate parametric name {pc.name}")
        names.add(pc.name)

    if errs:
        raise ConfigError("; ".join(errs))
