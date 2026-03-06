#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EXP02 — Feasibility Boundary (volumetric upper bound)

Story role:
- Provide a *theoretical* upper bound: compare daily colli capacity vs. daily due-by-deadline colli.
- This is a volume-based necessary condition only (routing feasibility may still fail).

Outputs:
- <runs_dir>/<run_id>/_analysis/exp02_feasibility_boundary.csv
- Plots:
  - exp02_daily_capacity_vs_deadline_due.png
  - exp02_daily_gap.png
  - exp02_cumulative_capacity_vs_deadline_due.png
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import os
from datetime import datetime, timedelta

import pandas as pd

from src.experiments.exp_utils import (
    DEFAULT_DATA_FILE, DEFAULT_RUNS_DIR, ensure_dir, timestamp_id,
    load_json, build_capacity_crunch, save_summary,
)
from src.experiments.plot_utils import plot_lines


def _horizon_dates(meta: dict, horizon_days: int) -> list[str]:
    """
    Returns ISO dates for day_idx in [0, horizon_days-1].
    Prefers metadata.horizon_start.
    """
    start = meta.get("horizon_start")
    if not start:
        raise ValueError("metadata.horizon_start missing in dataset; EXP02 needs a horizon start date.")
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    return [(d0 + timedelta(days=i)).isoformat() for i in range(int(horizon_days))]


def _vehicle_colli_capacity(v: dict) -> float:
    """
    Robustly extract vehicle colli capacity from the dataset schema.
    """
    cap = v.get("capacity", {}) or {}
    for k in ("colli", "Colli", "COLLI"):
        if k in cap:
            return float(cap[k])
    # fallback common variants
    for k in ("capacity_colli", "colli_capacity"):
        if k in v:
            return float(v[k])
    return 0.0


def _daily_capacity_colli(data: dict, capacity_profile: dict, day_idx: int) -> float:
    """
    Daily active fleet colli capacity under capacity_profile[day_idx] ratio.
    This matches the common "int(count * ratio)" convention used elsewhere in the project.
    """
    r = float((capacity_profile or {}).get(str(day_idx), 1.0))
    total = 0.0
    for v in data.get("vehicles", []) or []:
        count = int(v.get("count", 0))
        cap = _vehicle_colli_capacity(v)
        active = int(count * r)
        total += float(active) * float(cap)
    return float(total)


def _order_colli(o: dict) -> float:
    dem = o.get("demand", {}) or {}
    for k in ("colli", "Colli", "COLLI"):
        if k in dem:
            return float(dem[k])
    # fallback
    for k in ("demand_colli", "colli_demand"):
        if k in o:
            return float(o[k])
    return 0.0


def _deadline_for_order(o: dict) -> str | None:
    """
    Return the 'deadline date' for an order, as ISO string, or None if unavailable.

    Preferred: feasible_dates[-1] (your benchmark format)
    Fallbacks: due_date / deadline / latest_delivery_date
    """
    fds = o.get("feasible_dates") or []
    if isinstance(fds, list) and len(fds) > 0:
        return str(fds[-1])

    for k in ("due_date", "deadline", "latest_delivery_date", "latest_service_date"):
        if k in o and o[k]:
            return str(o[k])
    return None


def _deadline_due_colli(data: dict, date_str: str) -> float:
    """
    Sum colli of orders whose last feasible date (deadline) is exactly date_str.
    """
    s = 0.0
    for o in data.get("orders", []) or []:
        dl = _deadline_for_order(o)
        if dl == date_str:
            s += _order_colli(o)
    return float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA_FILE)
    ap.add_argument("--runs_dir", default=DEFAULT_RUNS_DIR)
    ap.add_argument("--run_id", default=None, help="Reuse an existing run_id folder if provided.")

    ap.add_argument("--ratio", type=float, default=0.40)
    ap.add_argument("--crunch_start", type=int, default=5)
    ap.add_argument("--crunch_end", type=int, default=8)
    ap.add_argument("--horizon_days", type=int, default=12)
    args = ap.parse_args()

    base = load_json(args.data)
    variant = build_capacity_crunch(base, args.ratio, args.crunch_start, args.crunch_end, args.horizon_days)

    run_id = args.run_id or timestamp_id("exp02_feasibility")
    analysis_dir = ensure_dir(os.path.join(args.runs_dir, run_id, "_analysis"))

    meta = variant.get("metadata", {}) or {}
    cap_profile = meta.get("capacity_profile", {}) or {}

    dates = _horizon_dates(meta, args.horizon_days)

    rows = []
    for i, d in enumerate(dates):
        cap = _daily_capacity_colli(variant, cap_profile, i)
        due = _deadline_due_colli(variant, d)
        gap = max(0.0, due - cap)

        # effective ratio for reporting
        base_total = _daily_capacity_colli(variant, {str(i): 1.0}, i)
        ratio_eff = (cap / base_total) if base_total > 0 else 0.0

        rows.append({
            "date": d,
            "day_idx": i,
            "capacity_colli": float(cap),
            "deadline_due_colli": float(due),
            "infeasible_gap_colli": float(gap),
            "capacity_ratio": float(ratio_eff),
        })

    df = pd.DataFrame(rows)
    df["capacity_colli_cum"] = df["capacity_colli"].cumsum()
    df["deadline_due_colli_cum"] = df["deadline_due_colli"].cumsum()
    df["gap_colli_cum"] = (df["deadline_due_colli_cum"] - df["capacity_colli_cum"]).clip(lower=0.0)

    save_summary(df, analysis_dir, "exp02_feasibility_boundary.csv")

    # --- PLOTS (use plot_utils.plot_lines) ---
    daily_melt = df.melt(
        id_vars=["date"],
        value_vars=["capacity_colli", "deadline_due_colli"],
        var_name="metric",
        value_name="colli",
    )
    plot_lines(
        daily_melt, x="date", y="colli", group="metric",
        title=f"EXP02 Daily capacity vs deadline-due (r={args.ratio:.2f})",
        out_path=os.path.join(analysis_dir, "exp02_daily_capacity_vs_deadline_due.png"),
        xlabel="date", ylabel="colli",
    )

    gap_df = df[["date", "infeasible_gap_colli"]].copy()
    plot_lines(
        gap_df, x="date", y="infeasible_gap_colli", group=None,
        title=f"EXP02 Daily infeasible gap (r={args.ratio:.2f})",
        out_path=os.path.join(analysis_dir, "exp02_daily_gap.png"),
        xlabel="date", ylabel="gap colli",
    )

    cum_melt = df.melt(
        id_vars=["date"],
        value_vars=["capacity_colli_cum", "deadline_due_colli_cum", "gap_colli_cum"],
        var_name="metric",
        value_name="colli",
    )
    plot_lines(
        cum_melt, x="date", y="colli", group="metric",
        title=f"EXP02 Cumulative boundary (r={args.ratio:.2f})",
        out_path=os.path.join(analysis_dir, "exp02_cumulative_capacity_vs_deadline_due.png"),
        xlabel="date", ylabel="colli (cumulative)",
    )

    print("\n=== EXP02 Feasibility Boundary ===")
    print(df.to_string(index=False))
    print(f"\nSaved under: {os.path.join(args.runs_dir, run_id)}")
    print(f"Analysis under: {analysis_dir}")


if __name__ == "__main__":
    main()
