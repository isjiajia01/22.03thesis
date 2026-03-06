#!/usr/bin/env python3
"""Run all MVT cases and persist artifacts for auditing."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_INDEX = ROOT / "data" / "audits" / "mvt_configs" / "mvt_case_index.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts  # noqa: F401
from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def derive_strategy_name(cfg: Dict[str, Any]) -> str:
    mode = str(cfg.get("mode", "proactive_quota")).lower()
    if mode == "greedy":
        return "Greedy"
    if bool(cfg.get("use_risk_model", False)):
        return "ProactiveRisk"
    return "Proactive"


def run_single(case: Dict[str, Any], seed: int, run_serial: int, ts: str) -> Dict[str, Any]:
    case_name = case["case_name"]
    cfg = dict(case.get("sim_config", {}))
    repeat_runs = int(cfg.pop("repeat_runs", 1))

    data_path = ROOT / case["data_path"]
    data = read_json(data_path)

    run_dir = ROOT / "data" / "results" / "MVT" / case_name / f"Seed_{seed}"
    if repeat_runs > 1:
        run_dir = run_dir / f"Run_{run_serial}"
    run_dir.mkdir(parents=True, exist_ok=True)

    scenario = case.get("scenario_name", case_name)
    strategy = case.get("strategy_name") or derive_strategy_name(cfg)

    source_run_dir = case.get("source_run_dir")
    if source_run_dir:
        src = ROOT / source_run_dir
        if not src.exists():
            raise FileNotFoundError(f"source_run_dir not found: {src}")
        src_cfg = read_json(src / "config_dump.json") if (src / "config_dump.json").exists() else {}
        src_params = src_cfg.get("parameters", {})
        for name in ["config_dump.json", "simulation_results.json", "summary_final.json"]:
            shutil.copy2(src / name, run_dir / name)

        sim_payload = read_json(run_dir / "simulation_results.json")
        daily = sim_payload.get("daily_stats", [])
        if daily:
            pd.DataFrame(daily).to_csv(run_dir / "daily_stats.csv", index=False)
        else:
            pd.DataFrame([]).to_csv(run_dir / "daily_stats.csv", index=False)

        # Preserve source provenance in wrapped config.
        wrapped_cfg = {
            "case_name": case_name,
            "seed": seed,
            "run_serial": run_serial,
            "timestamp": ts,
            "expected_days": int(case.get("expected_days", 0)),
            "purpose": case.get("purpose"),
            "sim_config": {**src_params, **cfg},
            "checks": case.get("checks", {}),
            "dataset_path": case.get("data_path"),
            "source_run_dir": str(Path(source_run_dir)),
            "scenario_name": scenario,
            "strategy_name": strategy,
        }
        write_json(run_dir / "config_dump.json", wrapped_cfg)
        return {
            "case_name": case_name,
            "seed": seed,
            "run_serial": run_serial,
            "expected_days": int(case.get("expected_days", 0)),
            "run_dir": str(run_dir.relative_to(ROOT)),
            "config_path": str((run_dir / "config_dump.json").relative_to(ROOT)),
            "simulation_results_path": str((run_dir / "simulation_results.json").relative_to(ROOT)),
            "summary_path": str((run_dir / "summary_final.json").relative_to(ROOT)),
            "daily_stats_path": str((run_dir / "daily_stats.csv").relative_to(ROOT)),
        }

    # Keep env knobs explicit and minimal for reproducibility.
    import os

    os.environ["VRP_TIME_LIMIT_SECONDS"] = str(int(cfg.get("base_compute", 1)))
    os.environ["VRP_HIGH_COMPUTE_LIMIT"] = str(int(cfg.get("high_compute", cfg.get("base_compute", 1))))
    os.environ["VRP_MAX_TRIPS_PER_VEHICLE"] = str(int(cfg.get("max_trips", 2)))

    sim = RollingHorizonIntegrated(
        data_source=data,
        strategy_config=cfg,
        seed=seed,
        verbose=False,
        run_context={"scenario": scenario, "strategy": strategy},
        base_dir=str(run_dir / "_engine_output"),
    )

    expected_days = int(case.get("expected_days", 0))
    if expected_days > 0:
        sim.end_date = sim.start_date + timedelta(days=expected_days - 1)

    summary = sim.run_simulation()

    simulation_results = {
        "case_name": case_name,
        "seed": seed,
        "run_serial": run_serial,
        "timestamp": ts,
        "daily_stats": sim.daily_stats,
        "vrp_audit_traces": sim.vrp_audit_traces,
    }

    config_dump = {
        "case_name": case_name,
        "seed": seed,
        "run_serial": run_serial,
        "timestamp": ts,
        "expected_days": expected_days,
        "purpose": case.get("purpose"),
        "sim_config": cfg,
        "checks": case.get("checks", {}),
        "dataset_path": str(data_path.relative_to(ROOT)),
        "dataset_metadata": data.get("metadata", {}),
    }

    write_json(run_dir / "config_dump.json", config_dump)
    write_json(run_dir / "simulation_results.json", simulation_results)
    write_json(run_dir / "summary_final.json", summary)
    pd.DataFrame(sim.daily_stats).to_csv(run_dir / "daily_stats.csv", index=False)

    return {
        "case_name": case_name,
        "seed": seed,
        "run_serial": run_serial,
        "expected_days": expected_days,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "config_path": str((run_dir / "config_dump.json").relative_to(ROOT)),
        "simulation_results_path": str((run_dir / "simulation_results.json").relative_to(ROOT)),
        "summary_path": str((run_dir / "summary_final.json").relative_to(ROOT)),
        "daily_stats_path": str((run_dir / "daily_stats.csv").relative_to(ROOT)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Run minimal verifiable tests (MVT)")
    ap.add_argument("--index", type=Path, default=DEFAULT_CONFIG_INDEX)
    args = ap.parse_args()

    index_payload = read_json(args.index)
    cases = []
    for item in index_payload.get("cases", []):
        case_cfg = read_json(ROOT / item["config_path"])
        cases.append(case_cfg)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows: List[Dict[str, Any]] = []

    for case in cases:
        cfg = case.get("sim_config", {})
        repeats = int(cfg.get("repeat_runs", 1))
        for seed in case.get("seeds", [1]):
            for run_serial in range(1, repeats + 1):
                rows.append(run_single(case, int(seed), run_serial, ts))

    index_csv = ROOT / "data" / "audits" / f"mvt_index_{ts}.csv"
    index_csv.parent.mkdir(parents=True, exist_ok=True)
    with index_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_name",
                "seed",
                "run_serial",
                "expected_days",
                "run_dir",
                "config_path",
                "simulation_results_path",
                "summary_path",
                "daily_stats_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"MVT runs complete. Index: {index_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
