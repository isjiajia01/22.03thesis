#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP00 — BAU baseline (Greedy vs Proactive_Smooth) + analysis plots

What it does:
- Runs BAU_Daily (no synthetic stress) for Greedy and Proactive_Smooth
- Supports multiple seeds for robustness
- Writes:
  <runs_dir>/<run_id>/... simulator outputs (daily_stats.csv, failed_orders.csv, summary_final.json)
  <runs_dir>/<run_id>/_analysis/exp00_bau_summary_per_seed.csv
  <runs_dir>/<run_id>/_analysis/exp00_bau_summary_agg.csv
  <runs_dir>/<run_id>/_analysis/exp00_bau_{service_rate,failed_orders,plan_churn,load_mse}.png

Notes to avoid "plotting hangs":
- Forces matplotlib backend to Agg (no GUI).
- Uses a local MPLCONFIGDIR under the run folder to avoid weird cache permissions.

Run examples:
  # minimal
  python src/experiments/exp00_bau_baseline.py

  # robust (3 seeds), mt=2, 60s solver
  python src/experiments/exp00_bau_baseline.py --seeds 123 456 789 --time_limit 60 --max_trips 2

  # if you want to group many experiments under one shared run_id folder:
  python src/experiments/exp00_bau_baseline.py --run_id 20260111_storyline --seeds 123 456 789
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# -----------------------------
# Repo root detection (portable)
# -----------------------------
def find_repo_root(start: Path) -> Path:
    """Walk upwards to find a directory that contains BOTH src/ and data/."""
    cur = start.resolve()
    for _ in range(12):  # enough for nested folders
        if (cur / "src").is_dir() and (cur / "data").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        f"Cannot find repo root from {start}. Expected a parent directory containing src/ and data/."
    )

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = find_repo_root(THIS_FILE)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# -----------------------------
# Imports that need repo root
# -----------------------------
from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated  # noqa: E402

try:
    import pandas as pd  # type: ignore
except Exception as e:
    raise SystemExit(
        "pandas is required for this experiment script.\n"
        "If you see 'No module named pandas' but you already installed it, you are likely using the WRONG python.\n"
        "Use your venv python:\n"
        "  which python\n"
        "  python -m pip install pandas\n"
        "  python src/experiments/exp00_bau_baseline.py\n"
        f"Original import error: {e}"
    )

# matplotlib: force non-interactive backend early
import matplotlib
matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_DATA_FILE = REPO_ROOT / "data" / "processed" / "multiday_benchmark_herlev.json"
DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "results" / "thesis_runs"


def timestamp_id(suffix: str) -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{suffix}"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        # Try to auto-detect a reasonable JSON under data/processed/
        processed = REPO_ROOT / "data" / "processed"
        candidates = []
        if processed.is_dir():
            candidates = sorted(processed.glob("*.json"))
        msg = f"Data file not found: {path}\n"
        if candidates:
            msg += "Available JSONs under data/processed:\n" + "\n".join([f"  - {c.name}" for c in candidates])
        msg += "\nTip: pass --data <path-to-json>"
        raise FileNotFoundError(msg)

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_release_date(data: Dict[str, Any]) -> Dict[str, Any]:
    default_date = (data.get("metadata") or {}).get("horizon_start", None)
    for o in data.get("orders", []):
        if "release_date" not in o:
            o["release_date"] = o.get("order_date", default_date)
    return data


def build_bau(base_data: Dict[str, Any]) -> Dict[str, Any]:
    d = copy.deepcopy(base_data)
    d.setdefault("metadata", {})
    d["metadata"]["scenario_spec"] = {
        "scenario_name": "BAU_Daily",
        "description": "BAU daily dataset (no synthetic stress).",
    }
    # Keep existing capacity_profile if present (or none)
    return d


def strategies(penalty_per_fail: float, buffer_ratio: float, guardrail_days: int) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Two-strategy comparison aligned with your story.

    Important:
    - penalty_per_fail is used by the simulation cost aggregation, not necessarily by OR-Tools directly.
    """
    return [
        ("Greedy", {
            "mode": "greedy",
            "penalty_per_fail": float(penalty_per_fail),
        }),
        ("Proactive_Smooth", {
            "mode": "proactive_quota",
            "buffer_ratio": float(buffer_ratio),
            "lookahead_days": 3,
            # Guardrail: make near-deadline orders mandatory in policy (if implemented in your policies.py)
            "guardrail_days": int(guardrail_days),
            # pressure knobs are harmless in BAU but keep config consistent
            "crunch_aware": True,
            "crunch_threshold": 0.7,
            "pressure_lookahead": 7,
            "penalty_per_fail": float(penalty_per_fail),
        }),
    ]


def plot_bars(df: "pd.DataFrame", value_col: str, out_png: Path, title: str) -> None:
    """
    Bar chart: strategy on x, mean value on y; if multiple seeds, show error bars (std).
    """
    # aggregate by strategy
    g = (df.groupby("strategy")[value_col]
           .agg(["mean", "std"])
           .reset_index()
           .sort_values("strategy"))
    x = list(g["strategy"])
    y = list(g["mean"])
    yerr = list(g["std"].fillna(0.0))

    fig = plt.figure(figsize=(8, 4.5))
    ax = fig.add_subplot(111)
    ax.bar(x, y, yerr=yerr, capsize=4)
    ax.set_title(title)
    ax.set_ylabel(value_col)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA_FILE))
    ap.add_argument("--runs_dir", default=str(DEFAULT_RUNS_DIR))

    ap.add_argument("--run_id", default=None, help="If set, write into <runs_dir>/<run_id>/ (useful to group experiments).")
    ap.add_argument("--seeds", nargs="+", type=int, default=[123, 456, 789])

    ap.add_argument("--time_limit", type=int, default=60, help="OR-Tools time limit per day (seconds).")
    ap.add_argument("--max_trips", type=int, default=2, help="Max trips per vehicle per day (ops-aware).")

    ap.add_argument("--penalty", type=float, default=150.0, help="Penalty per failed order for *evaluation* (BAU default ~150).")

    # Policy knobs
    ap.add_argument("--buffer_ratio", type=float, default=0.75)
    ap.add_argument("--guardrail_days", type=int, default=1)

    args = ap.parse_args()

    run_id = args.run_id or timestamp_id("exp00_bau")
    runs_dir = Path(args.runs_dir).expanduser().resolve()
    out_root = runs_dir / run_id
    analysis_dir = out_root / "_analysis"
    ensure_dir(analysis_dir)

    # Make matplotlib cache local to avoid permission/cache weirdness + reduce hangs
    mpl_cfg = analysis_dir / "_mplconfig"
    ensure_dir(mpl_cfg)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cfg))

    # Pass solver knobs via environment (works with your current pipeline)
    os.environ["VRP_TIME_LIMIT_SECONDS"] = str(int(args.time_limit))
    os.environ["VRP_MAX_TRIPS_PER_VEHICLE"] = str(int(args.max_trips))

    base = ensure_release_date(load_json(Path(args.data)))
    variant = build_bau(base)

    # record run spec
    spec = {
        "experiment": "EXP00_BAU_BASELINE",
        "run_id": run_id,
        "data": str(Path(args.data).resolve()),
        "seeds": args.seeds,
        "time_limit": args.time_limit,
        "max_trips": args.max_trips,
        "penalty_per_fail": args.penalty,
        "buffer_ratio": args.buffer_ratio,
        "guardrail_days": args.guardrail_days,
        "env": {
            "VRP_TIME_LIMIT_SECONDS": os.environ.get("VRP_TIME_LIMIT_SECONDS"),
            "VRP_MAX_TRIPS_PER_VEHICLE": os.environ.get("VRP_MAX_TRIPS_PER_VEHICLE"),
        },
    }
    with (analysis_dir / "exp00_run_spec.json").open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    records: List[Dict[str, Any]] = []
    st_list = strategies(args.penalty, args.buffer_ratio, args.guardrail_days)

    for seed in args.seeds:
        for st_name, st_cfg in st_list:
            print(f"\nRunning BAU_Daily | seed={seed} :: {st_name}  (t={args.time_limit}s, mt={args.max_trips})")
            sim = RollingHorizonIntegrated(
                data_source=variant,
                strategy_config=st_cfg,
                seed=int(seed),
                run_context={"scenario": "BAU_Daily", "strategy": st_name, "seed": int(seed)},
                results_dir=str(runs_dir),
                run_id=run_id,
                verbose=False,
            )
            summary = sim.run_simulation()

            records.append({
                "scenario": "BAU_Daily",
                "seed": int(seed),
                "strategy": st_name,
                "cost_raw": float(summary.get("cost_raw", 0.0)),
                "penalized_cost": float(summary.get("penalized_cost", summary.get("cost_raw", 0.0))),
                "failed_orders": int(summary.get("failed_orders", 0)),
                "service_rate": float(summary.get("service_rate", summary.get("service_rate_raw", 0.0))),
                "plan_churn": float(summary.get("plan_churn", summary.get("plan_churn_avg", 0.0))),
                "load_mse": float(summary.get("load_mse", summary.get("load_mse_raw", 0.0))),
            })

    df = pd.DataFrame(records).sort_values(["seed", "strategy"]).reset_index(drop=True)
    per_seed_csv = analysis_dir / "exp00_bau_summary_per_seed.csv"
    df.to_csv(per_seed_csv, index=False)

    agg = (df.groupby(["scenario", "strategy"])
             .agg(
                 cost_raw_mean=("cost_raw", "mean"),
                 penalized_cost_mean=("penalized_cost", "mean"),
                 failed_orders_mean=("failed_orders", "mean"),
                 service_rate_mean=("service_rate", "mean"),
                 plan_churn_mean=("plan_churn", "mean"),
                 load_mse_mean=("load_mse", "mean"),
                 failed_orders_std=("failed_orders", "std"),
                 service_rate_std=("service_rate", "std"),
                 plan_churn_std=("plan_churn", "std"),
             )
             .reset_index()
             .sort_values(["scenario", "strategy"]))
    agg_csv = analysis_dir / "exp00_bau_summary_agg.csv"
    agg.to_csv(agg_csv, index=False)

    print("\n=== EXP00 BAU summary (per seed) ===")
    print(df.to_string(index=False))
    print("\n=== EXP00 BAU summary (mean/std) ===")
    print(agg.to_string(index=False))

    # Plots (simple and robust)
    plot_bars(df, "service_rate", analysis_dir / "exp00_bau_service_rate.png", "BAU: Service Rate (mean±std)")
    plot_bars(df, "failed_orders", analysis_dir / "exp00_bau_failed_orders.png", "BAU: Failed Orders (mean±std)")
    plot_bars(df, "plan_churn", analysis_dir / "exp00_bau_plan_churn.png", "BAU: Plan Churn (mean±std)")
    plot_bars(df, "load_mse", analysis_dir / "exp00_bau_load_mse.png", "BAU: Load MSE (mean±std)")

    print(f"\n✅ Done.")
    print(f"Outputs under: {out_root}")
    print(f"Analysis under: {analysis_dir}")
    print(f"  - {per_seed_csv.name}")
    print(f"  - {agg_csv.name}")
    print("  - exp00_bau_*.png")


if __name__ == "__main__":
    main()
