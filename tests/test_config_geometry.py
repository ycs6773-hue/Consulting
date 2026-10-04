"""AEDT-free tests: config validation and parametric geometry consistency."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from hfss_patch.config import ConfigError, load_config, validate
from hfss_patch.geometry import bbox, build_model, check_model, evaluate, with_units
from hfss_patch.run import main

CFG = Path(__file__).resolve().parents[1] / "hfss_patch" / "configs" / "patch_2g4_fr4.yaml"


@pytest.fixture()
def cfg():
    return load_config(CFG)


def write_cfg(tmp_path: Path, mutate) -> Path:
    raw = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    mutate(raw)
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return p


def test_default_config_loads(cfg):
    assert cfg.patch.W == pytest.approx(38.0)
    assert cfg.project.aedt_version == "2025.1"
    assert len(cfg.sha256) == 64


def test_version_float_coerced_to_str(tmp_path):
    p = write_cfg(tmp_path, lambda r: r["project"].__setitem__("aedt_version", 2025.1))
    assert load_config(p).project.aedt_version == "2025.1"


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda r: r["patch"].__setitem__("y0", 30.0), "y0"),
        (lambda r: r["patch"].__setitem__("gap", 20.0), "notch"),
        (lambda r: r.__setitem__("air", 10.0), "lambda0/4"),
        (lambda r: r["setup"].__setitem__("f0", 3.0), "f0"),
        (lambda r: r["setup"].__setitem__("sweep_type", "Magic"), "sweep_type"),
        (lambda r: r["parametrics"][0].__setitem__("variable", "h"), "variable"),
        (lambda r: r["patch"].pop("Wf"), "missing"),
        (lambda r: r["patch"].__setitem__("foo", 1), "unknown"),
        (lambda r: r["board"].__setitem__("Wsub", 35.0), "fit"),
    ],
)
def test_invalid_configs_rejected(tmp_path, mutate, msg):
    with pytest.raises(ConfigError, match=msg):
        load_config(write_cfg(tmp_path, mutate))


def test_evaluate_expressions():
    env = {"W": 38.0, "gap": 1.0, "Wf": 3.0}
    assert evaluate("-(Wf/2+gap)", env) == pytest.approx(-2.5)
    assert evaluate("W-2*gap", env) == pytest.approx(36.0)
    with pytest.raises(KeyError):
        evaluate("X+1", env)
    with pytest.raises(ValueError):
        evaluate("__import__('os')", env)


def test_with_units():
    assert with_units("0") == "0.0mm"
    assert with_units("-Lsub/2") == "-Lsub/2"


def test_default_geometry_is_consistent(cfg):
    model = build_model(cfg)
    assert check_model(model) == []
    env = model.variables
    # feed runs from the port plane to the inset depth
    feed = bbox(model.feed, env)
    assert feed[1] == pytest.approx((-40.0, -14.7 + 10.9))
    # air clearance on the open sides
    air = bbox(model.airbox, env)
    assert air[0] == pytest.approx((-73.0, 73.0))
    assert air[2] == pytest.approx((-38.0, 39.6))


@pytest.mark.parametrize("var", ["L", "y0", "gap"])
def test_geometry_valid_across_parametric_range(cfg, var):
    pc = next(p for p in cfg.parametrics if p.variable == var)
    v = pc.start
    while v <= pc.stop + 1e-9:
        c = replace(cfg, patch=replace(cfg.patch, **{var: v}))
        validate(c)
        assert check_model(build_model(c)) == [], f"{var}={v}"
        v += pc.step


def test_cli_dry_run(tmp_path, capsys):
    p = write_cfg(tmp_path, lambda r: r["project"].__setitem__("output_dir", str(tmp_path / "out")))
    assert main(["--config", str(p), "--dry-run"]) == 0
    assert '"W": 38.0' in capsys.readouterr().out
    assert list((tmp_path / "out" / "logs").glob("run_*.log"))


def test_cli_bad_config_exit_code(tmp_path):
    p = write_cfg(tmp_path, lambda r: r["patch"].__setitem__("y0", 99.0))
    assert main(["--config", str(p), "--dry-run"]) == 2
