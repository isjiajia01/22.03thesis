#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared utilities for storyline experiments.

Design goals:
- Each experiment is runnable standalone.
- Consistent output structure:
    <runs_dir>/<run_id>/<scenario>/<strategy>/(daily_stats.csv, failed_orders.csv, ...)
    <runs_dir>/<run_id>/_analysis/(summary.csv, plots...)
- Minimal assumptions about your solver & simulator.
"""

from __future__ import annotations

import os
import sys
import json
import copy
import math
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------
# Project paths
# ------------------------------------------------------------
def project_root() -> str:
    """Return the repository root (contains both 'src/' and 'data/').

    This makes the experiment scripts portable: copy/clone the repo anywhere and
    the default paths still resolve without editing absolute directories.
    """
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "src").is_dir() and (p / "data").is_dir():
            return str(p)
    # Fallback: assume experiments live in <root>/src/experiments
    return str(here.parents[2])

PROJECT_ROOT = project_root()

DEFAULT_DATA_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "multiday_benchmark_herlev.json")
DEFAULT_RUNS_DIR  = os.path.join(PROJECT_ROOT, "data", "results", "thesis_runs")


def ensure_import_path():
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def timestamp_id(suffix: str) -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + suffix


# ------------------------------------------------------------
# Data helpers
# ------------------------------------------------------------

def _ensure_release_date(data: dict) -> dict:
    """Ensure each order has release_date; fall back to order_date or horizon_start."""
    default_date = data.get("metadata", {}).get("horizon_start", None)
    for o in data.get("orders", []):
        if "release_date" not in o:
            o["release_date"] = o.get("order_date", default_date)
    return data


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _ensure_release_date(data)


def save_json(obj: dict, path: str):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def build_bau(base_data: dict, horizon_days: int = 12) -> dict:
    """
    Build BAU baseline with EXPLICIT uniform capacity (no inherited stress).

    CRITICAL: This function MUST set capacity_profile to 1.0 for all days
    to ensure BAU is a true baseline without any capacity constraints.
    """
    d = copy.deepcopy(base_data)
    d.setdefault("metadata", {})

    # EXPLICIT: Set uniform capacity profile (no stress)
    d["metadata"]["capacity_profile"] = {str(i): 1.0 for i in range(horizon_days)}

    d["metadata"]["scenario_spec"] = {
        "scenario_name": "BAU_Daily",
        "description": "BAU daily dataset (uniform capacity=1.0, no stress).",
        "capacity_uniform": True,
    }
    return d


def build_capacity_crunch(
    base_data: dict,
    crunch_ratio: float,
    crunch_start: int = 5,
    crunch_end: int = 8,
    horizon_days: int = 12,
) -> dict:
    d = copy.deepcopy(base_data)
    d.setdefault("metadata", {})
    profile = {}
    for i in range(int(horizon_days)):
        profile[str(i)] = float(crunch_ratio) if (crunch_start <= i <= crunch_end) else 1.0
    d["metadata"]["capacity_profile"] = profile
    d["metadata"]["scenario_spec"] = {
        "scenario_name": "Capacity_Crunch",
        "description": f"Capacity reduced to {crunch_ratio:.2f} on days {crunch_start}-{crunch_end}",
        "crunch_days": list(range(int(crunch_start), int(crunch_end) + 1)),
        "crunch_ratio": float(crunch_ratio),
    }
    return d


def relax_time_windows(base_data: dict, tw_start: int = 360, tw_end: int = 1020) -> dict:
    """
    Set every order's time_window to [tw_start, tw_end] if present.
    Keeps per-order service_time intact.
    """
    d = copy.deepcopy(base_data)
    for o in d.get("orders", []):
        # common key choices in datasets
        if "time_window" in o:
            o["time_window"] = [int(tw_start), int(tw_end)]
        elif "time_windows" in o:
            o["time_windows"] = [[int(tw_start), int(tw_end)]]
    d.setdefault("metadata", {})
    d["metadata"]["scenario_spec"] = {
        **(d["metadata"].get("scenario_spec", {}) or {}),
        "relax_time_windows": True,
        "tw_start": int(tw_start),
        "tw_end": int(tw_end),
    }
    return d


def scale_capacity_profile(base_data: dict, scale: float, horizon_days: int = 12) -> dict:
    """
    Soft stress: scale capacity uniformly via capacity_profile day_idx -> scale.
    If dataset already has a profile, we multiply it by scale.
    """
    d = copy.deepcopy(base_data)
    d.setdefault("metadata", {})

    base_profile = d.get("metadata", {}).get("capacity_profile", {}) or {}
    profile = {}
    for i in range(int(horizon_days)):
        base_r = float(base_profile.get(str(i), 1.0))
        profile[str(i)] = float(base_r * float(scale))

    d["metadata"]["capacity_profile"] = profile
    d["metadata"]["scenario_spec"] = {
        "scenario_name": f"CapScale_{float(scale):.2f}",
        "description": f"Capacity scaled by {float(scale):.2f} for all days (soft stress).",
        "capacity_scale": float(scale),
    }
    return d


def fleet_variant_same_total_capacity(
    base_data: dict,
    ratio: float,
    active_target: int,
    vehicle_type_name: str = "Lift",
) -> dict:
    """
    Create a fleet variant where at the crunch ratio 'ratio' the *active* number of vehicles
    becomes 'active_target', while keeping the *active total colli capacity* roughly the same
    as the baseline fleet at that ratio.

    This mirrors your Experiment F (parallelism ablation).
    """
    d = copy.deepcopy(base_data)
    vehicles = d.get("vehicles", [])

    v = None
    for vv in vehicles:
        if vv.get("type_name") == vehicle_type_name:
            v = vv
            break
    if v is None:
        raise ValueError(f"Vehicle type {vehicle_type_name} not found in data['vehicles'].")

    base_count = int(v.get("count", 0))
    base_cap = float(v.get("capacity", {}).get("colli", 0.0))

    baseline_active = int(base_count * float(ratio))
    baseline_active_cap = baseline_active * base_cap

    if active_target <= 0:
        raise ValueError("active_target must be > 0.")
    new_cap = baseline_active_cap / float(active_target)

    # choose a count so that int(count*ratio) == active_target (or as close as possible)
    # we pick the minimal count meeting it.
    count = int(math.ceil(active_target / float(ratio)))
    while int(count * float(ratio)) < active_target:
        count += 1

    v["count"] = int(count)
    v.setdefault("capacity", {})
    v["capacity"]["colli"] = float(new_cap)

    d.setdefault("metadata", {})
    d["metadata"]["scenario_spec"] = {
        **(d["metadata"].get("scenario_spec", {}) or {}),
        "fleet_variant": f"{vehicle_type_name}_active{active_target}",
        "fleet_ratio": float(ratio),
        "fleet_active_target": int(active_target),
        "fleet_new_count": int(count),
        "fleet_new_vehicle_colli": float(new_cap),
        "fleet_baseline_active": int(baseline_active),
        "fleet_baseline_active_colli_total": float(baseline_active_cap),
    }
    return d


# ------------------------------------------------------------
# Strategy configs (keep it aligned with your thesis story)
# ------------------------------------------------------------

def strategy_greedy(penalty_per_fail: float) -> Dict[str, Any]:
    return {"mode": "greedy", "penalty_per_fail": float(penalty_per_fail)}


def strategy_proactive_smooth(
    penalty_per_fail: float,
    buffer_ratio: float = 0.75,
    lookahead_days: int = 3,
    crunch_aware: bool = True,
    crunch_threshold: float = 0.7,
    pressure_lookahead: int = 7,
    # Deadline guardrail: force include near-deadline orders
    deadline_guardrail_days: int = 1,
) -> Dict[str, Any]:
    return {
        "mode": "proactive_quota",
        "buffer_ratio": float(buffer_ratio),
        "lookahead_days": int(lookahead_days),

        # pressure-aware knobs (consumed by policies.py)
        "crunch_aware": bool(crunch_aware),
        "crunch_threshold": float(crunch_threshold),
        "pressure_lookahead": int(pressure_lookahead),

        # Guardrail knobs (consumed by policies.py)
        "deadline_guardrail_days": int(deadline_guardrail_days),

        "penalty_per_fail": float(penalty_per_fail),
    }


# ------------------------------------------------------------
# Env vars for solver knobs (time limit, multi-trip)
# ------------------------------------------------------------

@contextlib.contextmanager
def temporary_env(env: Dict[str, str]):
    old = {}
    try:
        for k, v in env.items():
            old[k] = os.environ.get(k)
            os.environ[k] = str(v)
        yield
    finally:
        for k, oldv in old.items():
            if oldv is None:
                if k in os.environ:
                    del os.environ[k]
            else:
                os.environ[k] = oldv


# ------------------------------------------------------------
# Simulation runner wrapper
# ------------------------------------------------------------

@dataclass
class RunSpec:
    scenario: str
    strategy: str
    seed: int
    vrp_time_limit_s: int
    max_trips: int
    notes: str = ""


def run_batch(
    data_variant: dict,
    run_id: str,
    runs_dir: str,
    scenario_name: str,
    seeds: Iterable[int],
    penalty_per_fail: float,
    vrp_time_limit_s: int,
    max_trips: int,
    proactive_buffer_ratio: float = 0.75,
    proactive_guardrail_days: int = 1,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Run 2 strategies (Greedy vs Proactive_Smooth) over seeds.
    Returns a DataFrame summary for this experiment.
    """
    ensure_import_path()
    from src.simulation.rolling_horizon_integrated import RollingHorizonIntegrated  # type: ignore

    strategies = [
        ("Greedy", strategy_greedy(penalty_per_fail)),
        ("Proactive_Smooth", strategy_proactive_smooth(
            penalty_per_fail=penalty_per_fail,
            buffer_ratio=proactive_buffer_ratio,
            deadline_guardrail_days=proactive_guardrail_days,
        )),
    ]

    records: List[Dict[str, Any]] = []

    env = {
        "VRP_TIME_LIMIT_SECONDS": str(int(vrp_time_limit_s)),
        "VRP_MAX_TRIPS_PER_VEHICLE": str(int(max_trips)),
    }

    with temporary_env(env):
        for seed in seeds:
            for st_name, st_cfg in strategies:
                sim = RollingHorizonIntegrated(
                    data_source=data_variant,
                    strategy_config=st_cfg,
                    seed=int(seed),
                    run_context={
                        "run_id": run_id,
                        "scenario": scenario_name,
                        "strategy": st_name,
                        "seed": int(seed),
                    },
                    results_dir=runs_dir,
                    run_id=run_id,
                    verbose=bool(verbose),
                )
                summary = sim.run_simulation()

                records.append({
                    "run_id": run_id,
                    "scenario": scenario_name,
                    "seed": int(seed),
                    "strategy": st_name,
                    "vrp_time_limit_s": int(vrp_time_limit_s),
                    "max_trips": int(max_trips),
                    "penalty_per_fail": float(penalty_per_fail),

                    # metrics
                    "cost_raw": float(summary.get("cost_raw", 0.0)),
                    "penalized_cost": float(summary.get("penalized_cost", 0.0)),
                    "failed_orders": int(summary.get("failed_orders", 0)),
                    "service_rate": float(summary.get("service_rate", 0.0)),
                    "plan_churn": float(summary.get("plan_churn", 0.0)),
                    "load_mse": float(summary.get("load_mse", 0.0)),

                    # pass-through debug if present
                    "future_pressure_min": summary.get("future_pressure_min", None),
                    "pressure_k_star": summary.get("pressure_k_star", None),
                })

    return pd.DataFrame(records)


def save_summary(df: pd.DataFrame, out_dir: str, fname: str) -> str:
    ensure_dir(out_dir)
    path = os.path.join(out_dir, fname)
    df.to_csv(path, index=False)
    return path
