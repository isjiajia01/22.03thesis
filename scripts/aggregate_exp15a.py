#!/usr/bin/env python3
"""Aggregate EXP15a results across seeds for each (ratio, shift) combination."""

import os
import json
import glob
from collections import defaultdict
import statistics

BASE = "/zhome/2a/1/202283/22.01 thesis/data/results/EXP15/EXP15a"

METRICS = [
    "service_rate_within_window",
    "penalized_cost",
    "cost_raw",
    "cost_per_order",
    "deadline_failure_count",
    "eligible_count",
    "delivered_within_window_count",
]

# ── Collect raw data ────────────────────────────────────────────────
records = []  # list of dicts

for ratio_shift_dir in sorted(os.listdir(BASE)):
    rsd_path = os.path.join(BASE, ratio_shift_dir)
    if not os.path.isdir(rsd_path):
        continue

    for seed_dir in sorted(os.listdir(rsd_path)):
        sd_path = os.path.join(rsd_path, seed_dir)
        if not os.path.isdir(sd_path):
            continue

        summary_path = os.path.join(sd_path, "DEFAULT", "EXP15a", "summary_final.json")
        ood_path     = os.path.join(sd_path, "DEFAULT", "EXP15a", "ood_labels.json")

        if not os.path.isfile(summary_path) or not os.path.isfile(ood_path):
            continue

        with open(summary_path) as f:
            summary = json.load(f)
        with open(ood_path) as f:
            ood = json.load(f)

        ratio = ood["crunch_ratio_setting"]
        shift = ood["crunch_window_shift_setting"]

        rec = {"ratio": ratio, "shift": shift, "seed_dir": seed_dir}
        for m in METRICS:
            rec[m] = summary[m]
        records.append(rec)

print(f"Total records loaded: {len(records)}")

# ── Group by (ratio, shift) ────────────────────────────────────────
groups = defaultdict(list)
for r in records:
    groups[(r["ratio"], r["shift"])].append(r)

ratios = sorted(set(k[0] for k in groups))
shifts = sorted(set(k[1] for k in groups))

print(f"Ratios : {ratios}")
print(f"Shifts : {shifts}")
print(f"Grid   : {len(ratios)} ratios x {len(shifts)} shifts = {len(ratios)*len(shifts)} cells")
print(f"Cells with data: {len(groups)}")
print()

# ── Helper ──────────────────────────────────────────────────────────
def agg(vals):
    """Return (mean, std, n)."""
    n = len(vals)
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if n > 1 else 0.0
    return m, s, n


# ══════════════════════════════════════════════════════════════════════
# TABLE 1 — Service Rate (mean +/- std)
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 1: Mean Service Rate Within Window  (mean +/- std, n seeds)")
print("=" * 100)

header = f"{'ratio':>8}" + "".join(f"{'shift='+str(s):>22}" for s in shifts)
print(header)
print("-" * len(header))

for ratio in ratios:
    row = f"{ratio:>8.2f}"
    for shift in shifts:
        key = (ratio, shift)
        if key in groups:
            vals = [r["service_rate_within_window"] for r in groups[key]]
            m, s, n = agg(vals)
            row += f"  {m:.4f}+/-{s:.4f} ({n:>2})"
        else:
            row += f"{'---':>22}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 2 — Penalized Cost (mean +/- std)
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 2: Mean Penalized Cost  (mean +/- std, n seeds)")
print("=" * 100)

header = f"{'ratio':>8}" + "".join(f"{'shift='+str(s):>26}" for s in shifts)
print(header)
print("-" * len(header))

for ratio in ratios:
    row = f"{ratio:>8.2f}"
    for shift in shifts:
        key = (ratio, shift)
        if key in groups:
            vals = [r["penalized_cost"] for r in groups[key]]
            m, s, n = agg(vals)
            row += f"  {m:>9.1f}+/-{s:>7.1f} ({n:>2})"
        else:
            row += f"{'---':>26}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 3 — Full CSV-like dump (all metrics, per cell)
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 3: Full aggregated data (CSV format)")
print("=" * 100)

csv_header = ",".join([
    "ratio", "shift", "n_seeds",
] + [f"{m}_mean" for m in METRICS]
  + [f"{m}_std"  for m in METRICS])
print(csv_header)

for ratio in ratios:
    for shift in shifts:
        key = (ratio, shift)
        if key not in groups:
            continue
        g = groups[key]
        n = len(g)
        means = []
        stds  = []
        for m in METRICS:
            vals = [r[m] for r in g]
            mv, sv, _ = agg(vals)
            means.append(mv)
            stds.append(sv)
        parts = [f"{ratio}", f"{shift}", f"{n}"]
        parts += [f"{v:.6f}" for v in means]
        parts += [f"{v:.6f}" for v in stds]
        print(",".join(parts))

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 4 — Compact summary: cost_raw and cost_per_order
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 4: Mean Cost Raw  (mean +/- std)")
print("=" * 100)

header = f"{'ratio':>8}" + "".join(f"{'shift='+str(s):>26}" for s in shifts)
print(header)
print("-" * len(header))

for ratio in ratios:
    row = f"{ratio:>8.2f}"
    for shift in shifts:
        key = (ratio, shift)
        if key in groups:
            vals = [r["cost_raw"] for r in groups[key]]
            m, s, n = agg(vals)
            row += f"  {m:>9.1f}+/-{s:>7.1f} ({n:>2})"
        else:
            row += f"{'---':>26}"
    print(row)

print()
print("=" * 100)
print("TABLE 5: Mean Deadline Failure Count  (mean +/- std)")
print("=" * 100)

header = f"{'ratio':>8}" + "".join(f"{'shift='+str(s):>22}" for s in shifts)
print(header)
print("-" * len(header))

for ratio in ratios:
    row = f"{ratio:>8.2f}"
    for shift in shifts:
        key = (ratio, shift)
        if key in groups:
            vals = [r["deadline_failure_count"] for r in groups[key]]
            m, s, n = agg(vals)
            row += f"  {m:>7.1f}+/-{s:>5.1f} ({n:>2})"
        else:
            row += f"{'---':>22}"
    print(row)

print()
print("Done.")
