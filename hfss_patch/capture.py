"""AEDT screen captures for the report — separate graphical session after the solve.

Why separate: `export_model_picture` / field-plot image export need AEDT in graphical
mode (PyAEDT docstring), while the solve runs non-graphical. This stage reopens the
saved, solved project with `non_graphical=False`, captures, and always releases the
desktop. Every capture is isolated: one failure is logged and recorded in
captures/captures.json, never fatal to the job or the report.

Caveat: graphical export over a locked/minimised RDP session can produce black images.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .builder import SETUP, SPHERE, SWEEP, S11, HfssJobError, _require, stage
from .config import JobConfig

if TYPE_CHECKING:  # pragma: no cover
    from ansys.aedt.core import Hfss

logger = logging.getLogger(__name__)

CAPTURE_DIR = "captures"
MANIFEST = "captures.json"
CUT_PLANE = "Cut_SubMid"

# name -> (file name, report caption). Order is the report order.
CAPTURES: dict[str, tuple[str, str]] = {
    "model_iso": ("model_iso.jpg", "HFSS 해석 모델 (isometric)"),
    "model_top": ("model_top.jpg", "HFSS 해석 모델 (top view)"),
    "jsurf": ("jsurf.jpg", "표면 전류 밀도 |Jsurf| @ f0 (patch/GND)"),
    "efield_cut": ("efield_cut.jpg", "기판 중간면 전계 |E| @ f0"),
    "pattern3d": ("pattern3d.jpg", "3D 방사 패턴 (Total Gain, AEDT)"),
    "s11_report": ("s11_report.jpg", "AEDT |S11| 리포트 화면"),
}


def _intrinsics(cfg: JobConfig) -> dict[str, str]:
    return {"Freq": f"{cfg.setup.f0}GHz", "Phase": "0deg"}


def _view_kwargs() -> dict[str, Any]:
    return dict(show_axis=True, show_grid=False, show_ruler=False)


def cap_model(hfss: "Hfss", cfg: JobConfig, path: Path, orientation: str) -> str:
    return _require(
        hfss.post.export_model_picture(
            full_name=str(path),
            show_region="False",
            orientation=orientation,
            width=cfg.capture.width,
            height=cfg.capture.height,
            **_view_kwargs(),
        ),
        f"export_model_picture({orientation})",
    )


def cap_jsurf(hfss: "Hfss", cfg: JobConfig, path: Path) -> str:
    plot = _require(
        hfss.post.create_fieldplot_surface(
            ["Patch", "GND"], "Mag_Jsurf", setup=f"{SETUP} : LastAdaptive", intrinsics=_intrinsics(cfg),
            plot_name="Cap_Jsurf",
        ),
        "create_fieldplot_surface(Mag_Jsurf)",
    )
    return _require(
        plot.export_image(str(path), width=cfg.capture.width, height=cfg.capture.height, orientation="top",
                          display_wireframe=False, show_region=False, **_view_kwargs()),
        "export Jsurf image",
    )


def cap_efield(hfss: "Hfss", cfg: JobConfig, path: Path) -> str:
    if CUT_PLANE not in hfss.modeler.planes:
        _require(hfss.modeler.create_plane(CUT_PLANE, "0mm", "0mm", "h/2", "0mm", "0mm", "1mm"), "create_plane")
    plot = _require(
        hfss.post.create_fieldplot_cutplane(
            [CUT_PLANE], "Mag_E", setup=f"{SETUP} : LastAdaptive", intrinsics=_intrinsics(cfg),
            plot_name="Cap_Efield", filter_objects=["Substrate"],
        ),
        "create_fieldplot_cutplane(Mag_E)",
    )
    return _require(
        plot.export_image(str(path), width=cfg.capture.width, height=cfg.capture.height, orientation="top",
                          display_wireframe=False, show_region=False, **_view_kwargs()),
        "export E-field image",
    )


def cap_report(hfss: "Hfss", cfg: JobConfig, path: Path, which: str) -> str:
    if which == "s11":
        kwargs: dict[str, Any] = dict(
            expressions=[f"dB({S11})"], setup_sweep_name=f"{SETUP} : {SWEEP}", primary_sweep_variable="Freq",
            plot_name="Cap_S11",
        )
    else:
        kwargs = dict(
            expressions=["dB(GainTotal)"], setup_sweep_name=f"{SETUP} : LastAdaptive", report_category="Far Fields",
            context=SPHERE, plot_type="3D Polar Plot", primary_sweep_variable="Phi", secondary_sweep_variable="Theta",
            variations={"Freq": [f"{cfg.setup.f0}GHz"], "Theta": ["All"], "Phi": ["All"]}, plot_name="Cap_Pattern3D",
        )
    _require(hfss.post.create_report(**kwargs), f"create_report({kwargs['plot_name']})")
    _require(
        hfss.post.export_report_to_jpg(str(path), kwargs["plot_name"], width=cfg.capture.width,
                                       height=cfg.capture.height),
        f"export_report_to_jpg({kwargs['plot_name']})",
    )
    return str(path)


def _jobs(cfg: JobConfig, d: Path) -> dict[str, Callable[["Hfss"], str]]:
    f = {k: d / v[0] for k, v in CAPTURES.items()}
    return {
        "model_iso": lambda h: cap_model(h, cfg, f["model_iso"], "isometric"),
        "model_top": lambda h: cap_model(h, cfg, f["model_top"], "top"),
        "jsurf": lambda h: cap_jsurf(h, cfg, f["jsurf"]),
        "efield_cut": lambda h: cap_efield(h, cfg, f["efield_cut"]),
        "pattern3d": lambda h: cap_report(h, cfg, f["pattern3d"], "pattern3d"),
        "s11_report": lambda h: cap_report(h, cfg, f["s11_report"], "s11"),
    }


def run_capture(cfg: JobConfig) -> dict[str, str]:
    """Reopen the solved project in graphical mode and export images. Always releases AEDT.

    Returns the manifest {name: path | "FAILED: ..."}; also written to captures/captures.json.
    Raises HfssJobError only if the project cannot be opened at all.
    """
    out = Path(cfg.project.output_dir).resolve()
    project_file = out / f"{cfg.project.name}.aedt"
    cap_dir = out / CAPTURE_DIR
    cap_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    if not project_file.exists():
        raise HfssJobError(f"capture: project not found {project_file} (run the solve first)")

    from ansys.aedt.core import Hfss  # deferred import, see builder.run_job

    hfss = None
    try:
        with stage("capture: open graphical"):
            hfss = Hfss(
                project=str(project_file),
                design=cfg.project.design,
                version=cfg.project.aedt_version,
                non_graphical=False,
                new_desktop=True,
                close_on_exit=False,
                remove_lock=True,  # a crashed earlier session may have left a .lock behind
            )
        for name, job in _jobs(cfg, cap_dir).items():
            try:
                with stage(f"capture: {name}"):
                    path = Path(str(job(hfss)))
                    if not path.exists() or path.stat().st_size == 0:
                        raise HfssJobError(f"image not written: {path}")
                    manifest[name] = str(path)
            except Exception as exc:  # noqa: BLE001 - isolate each capture
                manifest[name] = f"FAILED: {exc}"
        return manifest
    finally:
        if hfss is not None:
            try:
                hfss.release_desktop(close_projects=True, close_desktop=True)
                logger.info("AEDT desktop released (capture)")
            except Exception:  # noqa: BLE001
                logger.error("release_desktop failed after capture - check for orphan ansysedt", exc_info=True)
        try:
            (cap_dir / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.error("writing %s failed", MANIFEST, exc_info=True)


def load_manifest(results_dir: Path) -> dict[str, Path]:
    """Successful captures that exist on disk, keyed by capture name (report side)."""
    p = results_dir / CAPTURE_DIR / MANIFEST
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Path] = {}
    for name, val in raw.items():
        if name in CAPTURES and not str(val).startswith("FAILED"):
            path = Path(val)
            if not path.is_absolute():
                path = results_dir / CAPTURE_DIR / path
            if path.exists() and path.stat().st_size > 0:
                out[name] = path
    return out
