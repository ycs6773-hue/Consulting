"""Exercise builder.run_job against a fake PyAEDT to verify stage order and session release."""

from __future__ import annotations

import json
import sys
import types
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hfss_patch.builder import HfssJobError, run_job
from hfss_patch.config import load_config

CFG = Path(__file__).resolve().parents[1] / "hfss_patch" / "configs" / "patch_2g4_fr4.yaml"


@pytest.fixture()
def fake_aedt(monkeypatch):
    instances: list[MagicMock] = []

    def factory(**kwargs):
        h = MagicMock(name="Hfss")
        h.init_kwargs = kwargs
        h.validate_simple.return_value = 1
        instances.append(h)
        return h

    mod = types.ModuleType("ansys.aedt.core")
    mod.Hfss = factory
    for name in ("ansys", "ansys.aedt"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "ansys.aedt.core", mod)
    return instances


@pytest.fixture()
def cfg(tmp_path):
    c = load_config(CFG)
    return replace(c, project=replace(c.project, output_dir=str(tmp_path)))


def test_full_run_releases_desktop(fake_aedt, cfg, tmp_path):
    summary = run_job(cfg)
    h = fake_aedt[0]
    assert summary["status"] == "ok"
    assert h.init_kwargs["non_graphical"] is True and h.init_kwargs["new_desktop"] is True
    h.wave_port.assert_called_once()
    assert h.parametrics.add.call_count == len(cfg.parametrics)
    h.analyze_setup.assert_called_once_with("Setup1", cores=cfg.project.cores)
    h.release_desktop.assert_called_once_with(close_projects=True, close_desktop=True)
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"] == "ok"


def test_failed_solve_still_releases(fake_aedt, cfg, tmp_path):
    def factory_fail(**kwargs):
        h = MagicMock(name="Hfss")
        h.validate_simple.return_value = 1
        h.analyze_setup.return_value = False
        fake_aedt.append(h)
        return h

    sys.modules["ansys.aedt.core"].Hfss = factory_fail
    with pytest.raises(HfssJobError, match="solve nominal"):
        run_job(cfg, run_parametric=False)
    fake_aedt[0].release_desktop.assert_called_once()
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"].startswith("failed")


def test_validation_failure_stops_before_solve(fake_aedt, cfg):
    def factory_invalid(**kwargs):
        h = MagicMock(name="Hfss")
        h.validate_simple.return_value = 0
        fake_aedt.append(h)
        return h

    sys.modules["ansys.aedt.core"].Hfss = factory_invalid
    with pytest.raises(HfssJobError, match="validate"):
        run_job(cfg)
    fake_aedt[0].analyze_setup.assert_not_called()
    fake_aedt[0].release_desktop.assert_called_once()


def test_export_failure_is_isolated(fake_aedt, cfg):
    def factory(**kwargs):
        h = MagicMock(name="Hfss")
        h.validate_simple.return_value = 1
        h.post.get_solution_data.side_effect = [None] + [MagicMock()] * 20
        fake_aedt.append(h)
        return h

    sys.modules["ansys.aedt.core"].Hfss = factory
    summary = run_job(cfg, run_parametric=False)
    assert summary["exports"]["s11.csv"].startswith("FAILED")
    assert not summary["exports"]["farfield_cuts.csv"].startswith("FAILED")
