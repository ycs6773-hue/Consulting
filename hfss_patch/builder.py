"""PyAEDT HFSS pipeline: model -> boundaries/port -> setup/sweep -> solve -> export.

Session note: PyAEDT >= 0.18 talks to AEDT over gRPC, not win32com, so no
pythoncom.CoInitialize is required here. The Desktop session is always released
in `run_job`'s finally block (close_projects=True, close_desktop=True) so a failed
solve never leaves an orphaned ansysedt.exe holding a license.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from .config import JobConfig
from .geometry import Model, build_model, check_model, with_units

if TYPE_CHECKING:  # pragma: no cover
    from ansys.aedt.core import Hfss

logger = logging.getLogger(__name__)

SETUP = "Setup1"
SWEEP = "Sweep1"
SPHERE = "FF3D"
S11 = "S(P1,P1)"


class HfssJobError(RuntimeError):
    """A pipeline stage failed; message names the stage for reproducible triage."""


@contextmanager
def stage(name: str) -> Iterator[None]:
    t0 = time.perf_counter()
    logger.info("[%s] start", name)
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - wrap with stage context, keep traceback
        logger.exception("[%s] failed", name)
        raise HfssJobError(f"stage '{name}' failed: {exc}") from exc
    logger.info("[%s] done in %.1f s", name, time.perf_counter() - t0)


def _require(ok: Any, what: str) -> Any:
    """PyAEDT reports many failures as False/None instead of raising."""
    if ok is False or ok is None:
        raise HfssJobError(f"{what} returned {ok!r}")
    return ok


def _point(p: tuple[str, str, str]) -> list[str]:
    return [with_units(c) for c in p]


# --- stages ----------------------------------------------------------------------------


def define_variables(hfss: "Hfss", model: Model) -> None:
    for name, val in model.variables.items():
        hfss[name] = f"{val}mm"


def define_material(hfss: "Hfss", cfg: JobConfig) -> None:
    s = cfg.substrate
    mat = _require(hfss.materials.add_material(s.material), f"add_material({s.material})")
    mat.permittivity = s.er
    mat.dielectric_loss_tangent = s.tand


def create_geometry(hfss: "Hfss", model: Model) -> None:
    m = hfss.modeler
    for box in (model.substrate, model.airbox):
        _require(m.create_box(_point(box.origin), _point(box.sizes), name=box.name, material=box.material), box.name)
    for r in (model.gnd, model.patch, model.notch, model.feed):
        _require(m.create_rectangle("XY", _point(r.origin), [with_units(x) for x in r.sizes], name=r.name), r.name)
    _require(m.subtract(model.patch.name, [model.notch.name], keep_originals=False), "subtract notch")
    _require(m.unite([model.patch.name, model.feed.name]), "unite patch+feed")
    _require(
        m.create_polyline(
            [_point(p) for p in model.port_sheet.points],
            cover_surface=True,
            close_surface=True,
            name=model.port_sheet.name,
        ),
        "port sheet",
    )
    hfss.modeler["AirBox"].transparency = 0.9


def assign_boundaries(hfss: "Hfss", model: Model) -> None:
    _require(hfss.assign_perfecte_to_sheets([model.gnd.name], name="PerfE_GND"), "PerfE GND")
    _require(hfss.assign_perfecte_to_sheets([model.conductor_name], name="PerfE_Patch"), "PerfE patch")
    _require(hfss.assign_radiation_boundary_to_objects(model.airbox.name, name="Rad1"), "radiation boundary")
    _require(
        hfss.wave_port(
            model.port_sheet.name,
            integration_line=[_point(model.port_int_line[0]), _point(model.port_int_line[1])],
            modes=1,
            impedance=50,
            renormalize=True,
            name=model.port_name,
        ),
        "wave port",
    )


def create_setup(hfss: "Hfss", cfg: JobConfig) -> None:
    st = cfg.setup
    setup = _require(hfss.create_setup(name=SETUP), "create_setup")
    setup.props["Frequency"] = f"{st.f0}GHz"
    setup.props["MaximumPasses"] = st.max_passes
    setup.props["MaxDeltaS"] = st.max_delta_s
    _require(setup.update(), "setup.update")
    _require(
        hfss.create_linear_step_sweep(
            setup=SETUP,
            unit="GHz",
            start_frequency=st.sweep_start,
            stop_frequency=st.sweep_stop,
            step_size=st.sweep_step,
            name=SWEEP,
            save_fields=False,
            sweep_type=st.sweep_type,
        ),
        "frequency sweep",
    )
    ff = cfg.farfield
    _require(
        hfss.insert_infinite_sphere(
            phi_start=0,
            phi_stop=360,
            phi_step=ff.phi_step,
            theta_start=0,
            theta_stop=180,
            theta_step=ff.theta_step,
            name=SPHERE,
        ),
        "infinite sphere",
    )


def create_parametrics(hfss: "Hfss", cfg: JobConfig) -> list[Any]:
    out = []
    for pc in cfg.parametrics:
        ps = _require(
            hfss.parametrics.add(
                pc.variable,
                f"{pc.start}mm",
                f"{pc.stop}mm",
                f"{pc.step}mm",
                variation_type="LinearStep",
                solution=f"{SETUP} : {SWEEP}",
                name=pc.name,
            ),
            f"parametric {pc.name}",
        )
        out.append(ps)
    return out


def _export_solution(hfss: "Hfss", out: Path, fname: str, **kwargs: Any) -> str:
    data = _require(hfss.post.get_solution_data(**kwargs), f"get_solution_data({fname})")
    path = out / fname
    _require(data.export_data_to_csv(str(path)), f"export {fname}")
    return str(path)


def export_results(hfss: "Hfss", cfg: JobConfig, out: Path, param_vars: list[str]) -> dict[str, str]:
    """Each export is independent: one failure is logged and recorded, not fatal."""
    f0 = f"{cfg.setup.f0}GHz"
    jobs: dict[str, dict[str, Any]] = {
        "s11.csv": dict(
            expressions=[f"dB({S11})", "re(Z(P1,P1))", "im(Z(P1,P1))", "VSWR(P1)"],
            setup_sweep_name=f"{SETUP} : {SWEEP}",
            primary_sweep_variable="Freq",
        ),
        "farfield_cuts.csv": dict(
            expressions=["dB(GainTotal)", "dB(GainL3Y)", "dB(GainL3X)"],
            setup_sweep_name=f"{SETUP} : LastAdaptive",
            report_category="Far Fields",
            context=SPHERE,
            primary_sweep_variable="Theta",
            # theta 0..180 per phi; phi+180 gives the other half of each full cut (H: 0/180, E: 90/270)
            variations={"Freq": [f0], "Phi": ["0deg", "90deg", "180deg", "270deg"], "Theta": ["All"]},
        ),
        "farfield_3d.csv": dict(
            expressions=["dB(GainTotal)"],
            setup_sweep_name=f"{SETUP} : LastAdaptive",
            report_category="Far Fields",
            context=SPHERE,
            primary_sweep_variable="Theta",
            variations={"Freq": [f0], "Phi": ["All"], "Theta": ["All"]},
        ),
        "antenna_params.csv": dict(
            expressions=["PeakGain", "PeakDirectivity", "RadiationEfficiency", "PeakRealizedGain"],
            setup_sweep_name=f"{SETUP} : LastAdaptive",
            report_category="Antenna Parameters",
            context=SPHERE,
            variations={"Freq": [f0]},
        ),
    }
    for var in param_vars:
        jobs[f"s11_param_{var}.csv"] = dict(
            expressions=[f"dB({S11})"],
            setup_sweep_name=f"{SETUP} : {SWEEP}",
            primary_sweep_variable="Freq",
            variations={"Freq": ["All"], var: ["All"]},
        )

    manifest: dict[str, str] = {}
    for fname, kwargs in jobs.items():
        try:
            manifest[fname] = _export_solution(hfss, out, fname, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("export %s failed", fname)
            manifest[fname] = f"FAILED: {exc}"

    for fname, fn in (("convergence.prop", hfss.export_convergence), ("mesh_stats.ms", hfss.export_mesh_stats)):
        try:
            manifest[fname] = str(_require(fn(SETUP, output_file=str(out / fname)), fname))
        except Exception as exc:  # noqa: BLE001
            logger.exception("export %s failed", fname)
            manifest[fname] = f"FAILED: {exc}"
    return manifest


# --- orchestration ---------------------------------------------------------------------


def run_job(cfg: JobConfig, run_parametric: bool = True, solve: bool = True) -> dict[str, Any]:
    """Build, solve and export. Always releases AEDT. Returns the run summary dict."""
    model = build_model(cfg)
    errs = check_model(model)
    if errs:
        raise HfssJobError("geometry check failed: " + "; ".join(errs))

    out = Path(cfg.project.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_file = out / f"{cfg.project.name}.aedt"
    summary: dict[str, Any] = {
        "config": cfg.source_path,
        "config_sha256": cfg.sha256,
        "aedt_version": cfg.project.aedt_version,
        "project": str(project_file),
        "variables_mm": model.variables,
        "status": "started",
    }

    from ansys.aedt.core import Hfss  # deferred: keeps config/geometry usable without PyAEDT

    hfss = None
    try:
        with stage("launch"):
            hfss = Hfss(
                project=str(project_file),
                design=cfg.project.design,
                solution_type="Modal",
                version=cfg.project.aedt_version,
                non_graphical=cfg.project.non_graphical,
                new_desktop=True,
                close_on_exit=False,
            )
            hfss.modeler.model_units = "mm"
        with stage("variables+material"):
            define_variables(hfss, model)
            define_material(hfss, cfg)
        with stage("geometry"):
            create_geometry(hfss, model)
        with stage("boundaries+port"):
            assign_boundaries(hfss, model)
        with stage("setup+sweep"):
            create_setup(hfss, cfg)
        params = []
        if run_parametric and cfg.parametrics:
            with stage("parametrics"):
                params = create_parametrics(hfss, cfg)
        with stage("validate"):
            ok = hfss.validate_simple()  # AEDT ValidateDesign: 1 = pass, 0 = fail
            summary["validate"] = bool(ok)
            _require(ok or None, "design validation")
        hfss.save_project()

        if solve:
            with stage("solve nominal"):
                _require(hfss.analyze_setup(SETUP, cores=cfg.project.cores), "analyze_setup")
            for ps in params:
                with stage(f"solve {ps.name}"):
                    _require(ps.analyze(cores=cfg.project.cores), f"analyze {ps.name}")
            hfss.save_project()
            with stage("export"):
                summary["exports"] = export_results(
                    hfss, cfg, out, [pc.variable for pc in cfg.parametrics] if params else []
                )
        summary["status"] = "ok"
        return summary
    except Exception as exc:
        summary["status"] = f"failed: {exc}"
        raise
    finally:
        if hfss is not None:
            try:
                hfss.save_project()
            except Exception:  # noqa: BLE001
                logger.warning("save_project during cleanup failed", exc_info=True)
            try:
                hfss.release_desktop(close_projects=True, close_desktop=True)
                logger.info("AEDT desktop released")
            except Exception:  # noqa: BLE001
                logger.error("release_desktop failed - check for orphan ansysedt process", exc_info=True)
        # Never let summary writing mask the original exception.
        try:
            (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.error("writing run_summary.json failed", exc_info=True)
