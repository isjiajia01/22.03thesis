#!/usr/bin/env python3
"""Run A4_REAL rerun with full dataset and route traces."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    data_path = root / "data" / "processed" / "multiday_benchmark_herlev.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    profile = {str(i): (0.59 if 5 <= i <= 10 else 1.0) for i in range(12)}
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["capacity_profile"] = profile

    out = root / "data" / "results" / "MVT" / "A4_REAL_RERUN_TRACE" / "Seed_1"
    out.mkdir(parents=True, exist_ok=True)

    cfg = {
        "mode": "proactive_quota",
        "use_risk_model": True,
        "risk_model_path": str(root / "models" / "risk_model.joblib"),
        "risk_threshold_on": 0.826,
        "risk_threshold_off": 0.496,
        "base_compute": 60,
        "high_compute": 300,
        "max_trips": 2,
        "ratio": 0.59,
        "crunch_start": 5,
        "crunch_end": 10,
    }

    os.environ["VRP_TIME_LIMIT_SECONDS"] = "60"
    os.environ["VRP_HIGH_COMPUTE_LIMIT"] = "300"
    os.environ["VRP_MAX_TRIPS_PER_VEHICLE"] = "2"

    sim = RollingHorizonIntegrated(
        data_source=data,
        strategy_config=cfg,
        seed=1,
        verbose=False,
        run_context={"scenario": "MVT_A4_REAL_RERUN", "strategy": "ProactiveRisk"},
        base_dir=str(out / "_engine_output"),
    )
    sim.end_date = sim.start_date + timedelta(days=11)
    summary = sim.run_simulation()

    config_dump = {
        "case_name": "A4_REAL_RERUN_TRACE",
        "seed": 1,
        "expected_days": 12,
        "sim_config": cfg,
        "dataset_path": "data/processed/multiday_benchmark_herlev.json",
    }
    results = {
        "daily_stats": sim.daily_stats,
        "vrp_audit_traces": sim.vrp_audit_traces,
        "summary": summary,
    }

    (out / "config_dump.json").write_text(json.dumps(config_dump, indent=2), encoding="utf-8")
    (out / "simulation_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / "summary_final.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    risk_days = sum(int(d.get("risk_mode_on", 0)) for d in sim.daily_stats)
    routes_max = max(int(d.get("vrp_routes", 0)) for d in sim.daily_stats) if sim.daily_stats else 0
    print(f"[A4_REAL_RERUN_TRACE] done: out={out}")
    print(f"[A4_REAL_RERUN_TRACE] days={len(sim.daily_stats)} risk_days={risk_days} routes_max={routes_max}")


if __name__ == "__main__":
    main()
