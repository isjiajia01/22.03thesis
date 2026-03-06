#!/usr/bin/env python3
"""Docker-friendly mover CLI wrappers around existing thesis scripts."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_cmd(cmd: Sequence[str], label: str, log_dir: Path) -> None:
    ensure_dir(log_dir)
    log_path = log_dir / f"{label}_{now_ts()}.log"
    with log_path.open("w", encoding="utf-8") as lf:
        lf.write(f"$ {' '.join(cmd)}\n\n")
        proc = subprocess.run(
            list(cmd),
            cwd=ROOT,
            stdout=lf,
            stderr=subprocess.STDOUT,
            check=False,
            env=os.environ.copy(),
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {proc.returncode}. "
            f"See log: {log_path.relative_to(ROOT)}"
        )
    print(f"{label}: OK ({log_path.relative_to(ROOT)})")


def newest(paths: Iterable[Path]) -> Path:
    items = list(paths)
    if not items:
        raise FileNotFoundError("No matching files found.")
    return max(items, key=lambda p: p.stat().st_mtime)


def copy_newest(glob_pattern: str, out_dir: Path) -> Path:
    files = list((ROOT / "data" / "audits").glob(glob_pattern))
    path = newest(files)
    ensure_dir(out_dir)
    dst = out_dir / path.name
    shutil.copy2(path, dst)
    return dst


def infer_master_runner_output(exp: str, seed: int, overrides: Sequence[str]) -> Path:
    out = ROOT / "data" / "results" / f"EXP_{exp.upper()}"
    if overrides:
        parsed = {}
        for ov in overrides:
            if "=" not in ov:
                continue
            k, v = ov.split("=", 1)
            parsed[k] = v
        suffix_parts = []
        for key in ["ratio", "max_trips", "risk_threshold_on", "use_risk_model", "base_compute", "mode"]:
            if key in parsed:
                short_key = {
                    "ratio": "ratio",
                    "max_trips": "max_trips",
                    "risk_threshold_on": "delta",
                    "use_risk_model": "risk",
                    "base_compute": "tl",
                    "mode": "mode",
                }[key]
                suffix_parts.append(f"{short_key}_{parsed[key]}")
        if suffix_parts:
            out = out / "_".join(suffix_parts)
    return out / f"Seed_{seed}"


def cmd_run_one(args: argparse.Namespace) -> int:
    log_dir = ROOT / "data" / "audits" / "docker_logs"
    cmd: List[str] = [
        sys.executable,
        "-m",
        "scripts.runner.master_runner",
        "--exp",
        args.exp.upper(),
        "--seed",
        str(args.seed),
    ]
    for ov in args.override:
        cmd.extend(["--override", ov])
    if args.override_json:
        cmd.extend(["--override_json", args.override_json])
    run_cmd(cmd, "run_one", log_dir)

    src_dir = infer_master_runner_output(args.exp, args.seed, args.override)
    required = ["config_dump.json", "simulation_results.json", "summary_final.json"]
    missing = [name for name in required if not (src_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Run completed but missing artifacts in {src_dir}: {missing}")

    out_dir = ROOT / args.out
    ensure_dir(out_dir)
    for name in required:
        shutil.copy2(src_dir / name, out_dir / name)
    print(f"artifacts: OK ({out_dir.relative_to(ROOT)})")
    return 0


def cmd_mvt(args: argparse.Namespace) -> int:
    log_dir = ROOT / "data" / "audits" / "docker_logs"
    # Main-run spotcheck prerequisite consumed by scripts/mvt/spot_checks.py.
    run_cmd(
        [
            sys.executable,
            "-m",
            "scripts.runner.master_runner",
            "--exp",
            "EXP04",
            "--seed",
            "1",
        ],
        "mvt_mainrun_spotcheck_exp04_seed1",
        log_dir,
    )
    run_cmd([sys.executable, "scripts/mvt/generate_mvt_configs.py"], "mvt_generate", log_dir)
    run_cmd([sys.executable, "scripts/mvt/run_mvt.py"], "mvt_run", log_dir)
    run_cmd([sys.executable, "scripts/mvt/audit_mvt.py"], "mvt_audit", log_dir)
    run_cmd([sys.executable, "scripts/mvt/spot_checks.py"], "mvt_spotchecks", log_dir)

    out_dir = ROOT / args.out
    ensure_dir(out_dir)
    copied = []
    for pat in [
        "mvt_traffic_light_*.csv",
        "mvt_report_*.md",
        "mvt_one_page_summary_*.md",
        "mvt_spotcheck_traffic_light_*.csv",
        "mvt_spotcheck_report_*.md",
        "mvt_index_*.csv",
    ]:
        copied.append(copy_newest(pat, out_dir))

    tl = newest((ROOT / "data" / "audits").glob("mvt_traffic_light_*.csv"))
    fail_count = 0
    with tl.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "FAIL":
                fail_count += 1
    verdict = "PASS" if fail_count == 0 else f"FAIL ({fail_count} checks)"
    print(f"mvt verdict: {verdict}")
    print(f"mvt outputs copied: {len(copied)} files -> {out_dir.relative_to(ROOT)}")
    return 0 if fail_count == 0 else 1


def cmd_audit(args: argparse.Namespace) -> int:
    if args.scope != "all":
        raise RuntimeError("Only --scope all is supported.")
    log_dir = ROOT / "data" / "audits" / "docker_logs"
    run_cmd([sys.executable, "scripts/completion_audit.py"], "audit_completion", log_dir)
    run_cmd([sys.executable, "scripts/analysis/analysis_pack.py"], "audit_analysis_pack", log_dir)

    out_dir = ROOT / args.out
    ensure_dir(out_dir)
    copied = []
    for pat in [
        "completion_summary_*.txt",
        "completion_gap_report_*.csv",
        "completion_expected_matrix_*.csv",
        "completion_actual_artifacts_*.csv",
        "traffic_light_all_*.csv",
        "traffic_light_all_*.txt",
        "paired_stats_cross_exp_*.txt",
        "one_page_summary_*.txt",
    ]:
        copied.append(copy_newest(pat, out_dir))
    print(f"audit outputs copied: {len(copied)} files -> {out_dir.relative_to(ROOT)}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    app = ROOT / "apps" / "interactive_demo" / "app.py"
    if not app.exists():
        raise RuntimeError(f"Demo app not found: {app}")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
    ]
    os.chdir(ROOT)
    return subprocess.call(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mover", description="MOVER Docker CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-one", help="Run one experiment endpoint")
    p_run.add_argument("--exp", required=True, help="Experiment ID, e.g., EXP04")
    p_run.add_argument("--seed", type=int, required=True, help="Seed, e.g., 1")
    p_run.add_argument("--override", action="append", default=[], help="Optional key=value override")
    p_run.add_argument("--override-json", help="Optional JSON overrides file")
    p_run.add_argument("--out", required=True, help="Output directory for artifact triple")
    p_run.set_defaults(func=cmd_run_one)

    p_audit = sub.add_parser("audit", help="Run audit bundle")
    p_audit.add_argument("--scope", default="all", choices=["all"])
    p_audit.add_argument("--out", required=True, help="Output directory for audit summaries")
    p_audit.set_defaults(func=cmd_audit)

    p_mvt = sub.add_parser("mvt", help="Run MVT suite")
    p_mvt.add_argument("--out", required=True, help="Output directory for MVT summaries")
    p_mvt.set_defaults(func=cmd_mvt)

    p_demo = sub.add_parser("demo", help="Run Streamlit demo")
    p_demo.add_argument("--host", default="0.0.0.0")
    p_demo.add_argument("--port", type=int, default=8501)
    p_demo.set_defaults(func=cmd_demo)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
