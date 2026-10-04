"""CLI: python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml [--dry-run]."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config
from .geometry import build_model, bbox, check_model

logger = logging.getLogger("hfss_patch")


def setup_logging(log_dir: Path, verbose: bool) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=fmt,
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        force=True,
    )
    return log_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HFSS 2.4 GHz inset patch antenna pipeline")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true", help="validate config/geometry only, no AEDT")
    ap.add_argument("--no-parametric", action="store_true", help="skip Optimetrics sweeps")
    ap.add_argument("--no-solve", action="store_true", help="build and save the project without solving")
    ap.add_argument("--version", dest="aedt_version", help="override AEDT version, e.g. 2025.1")
    ap.add_argument("--cores", type=int, help="override solver cores")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    if args.aedt_version or args.cores:
        from dataclasses import replace

        cfg = replace(
            cfg,
            project=replace(
                cfg.project,
                aedt_version=args.aedt_version or cfg.project.aedt_version,
                cores=args.cores or cfg.project.cores,
            ),
        )

    log_file = setup_logging(Path(cfg.project.output_dir) / "logs", args.verbose)
    logger.info("log file: %s", log_file)

    model = build_model(cfg)
    errs = check_model(model)
    if errs:
        logger.error("geometry check failed: %s", errs)
        return 2

    if args.dry_run:
        env = model.variables
        report = {
            "variables_mm": env,
            "lambda0_at_sweep_start_mm": round(cfg.lambda0_mm, 2),
            "bbox_mm": {
                p.name: bbox(p, env)
                for p in (model.substrate, model.airbox, model.gnd, model.patch, model.notch, model.feed)
            },
            "parametrics": [vars(p) for p in cfg.parametrics],
        }
        print(json.dumps(report, indent=2))
        logger.info("dry run OK")
        return 0

    from .builder import HfssJobError, run_job

    try:
        summary = run_job(cfg, run_parametric=not args.no_parametric, solve=not args.no_solve)
    except HfssJobError as exc:
        logger.error("job failed: %s", exc)
        return 1
    except ImportError as exc:
        logger.error("PyAEDT not available (pip install ansys-aedt-core): %s", exc)
        return 3
    logger.info("job finished: %s", summary["status"])
    failed = [k for k, v in summary.get("exports", {}).items() if str(v).startswith("FAILED")]
    if failed:
        logger.warning("exports failed: %s", failed)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
