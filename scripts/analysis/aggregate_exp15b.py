#!/usr/bin/env python3
"""Aggregate EXP15b results across seeds for each (multiplier, jitter) combination."""

import os
import json
from collections import defaultdict
import statistics

BASE = "/zhome/2a/1/202283/22.01 thesis/data/results/EXP15/EXP15b"

METRICS = [
    "service_rate_within_window",
    "penalized_cost",
    "cost_raw",
    "cost_per_order",
    "deadline_failure_count",
    "eligible_count",
    "delivered_within_window_count",
]

# ── Collect raw records ──────────────────────────────────────────────
records = []  # list of flat dicts

for combo_dir in sorted(os.listdir(BASE)):
    combo_path = os.path.join(BASE, combo_dir)
    if not os.path.isdir(combo_path):
        continue

    for seed_dir in sorted(os.listdir(combo_path)):
        seed_path = os.path.join(combo_path, seed_dir)
        if not os.path.isdir(seed_path):
            continue

        summary_path = os.path.join(seed_path, "DEFAULT", "EXP15b", "summary_final.json")
        ood_path = os.path.join(seed_path, "DEFAULT", "EXP15b", "ood_labels.json")

        if not os.path.isfile(summary_path) or not os.path.isfile(ood_path):
            print(f"  [WARN] missing files in {seed_path}")
            continue

        with open(summary_path) as f:
            summary = json.load(f)
        with open(ood_path) as f:
            ood = json.load(f)

        rec = {
            "multiplier": ood["order_count_multiplier"],
            "jitter": ood["spatial_jitter_km"],
            "seed_dir": seed_dir,
        }
        for m in METRICS:
            rec[m] = summary[m]
        records.append(rec)

print(f"Total records loaded: {len(records)}")
print()

# ── Group by (multiplier, jitter) ───────────────────────────────────
grouped = defaultdict(list)  # key = (mult, jitter) -> list of rec dicts
for r in records:
    grouped[(r["multiplier"], r["jitter"])].append(r)

multipliers = sorted(set(k[0] for k in grouped))
jitters = sorted(set(k[1] for k in grouped))


# ── Helper ───────────────────────────────────────────────────────────
def agg(values):
    """Return (mean, std, n)."""
    n = len(values)
    mu = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    return mu, sd, n


# ══════════════════════════════════════════════════════════════════════
# TABLE 1 — Service Rate (mean +/- std)
# ══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("TABLE 1: Mean Service Rate Within Window  (mean +/- std)")
print("=" * 80)

header = "mult \\\\ jitter".rjust(16) + "".join(f"{'j=' + str(j):>20s}" for j in jitters)
print(header)
print("-" * len(header))

for m in multipliers:
    row = f"{'m=' + str(m):>16s}"
    for j in jitters:
        recs = grouped.get((m, j), [])
        if recs:
            mu, sd, n = agg([r["service_rate_within_window"] for r in recs])
            row += f"{mu:>12.4f} +/-{sd:.4f}"
        else:
            row += f"{'N/A':>20s}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 2 — Penalized Cost (mean +/- std)
# ══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("TABLE 2: Mean Penalized Cost  (mean +/- std)")
print("=" * 80)

header = "mult \\\\ jitter".rjust(16) + "".join(f"{'j=' + str(j):>24s}" for j in jitters)
print(header)
print("-" * len(header))

for m in multipliers:
    row = f"{'m=' + str(m):>16s}"
    for j in jitters:
        recs = grouped.get((m, j), [])
        if recs:
            mu, sd, n = agg([r["penalized_cost"] for r in recs])
            row += f"{mu:>14.2f} +/-{sd:>7.2f}"
        else:
            row += f"{'N/A':>24s}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 3 — All metrics summary per (mult, jitter)
# ══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("TABLE 3: Full Metric Summary per (multiplier, jitter)")
print("=" * 80)

for m in multipliers:
    for j in jitters:
        recs = grouped.get((m, j), [])
        if not recs:
            continue
        n = len(recs)
        print(f"\n  mult={m}, jitter={j}  (n={n} seeds)")
        print(f"  {'metric':<35s} {'mean':>12s} {'std':>12s} {'min':>12s} {'max':>12s}")
        print(f"  {'-'*35} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        for metric in METRICS:
            vals = [r[metric] for r in recs]
            mu, sd, _ = agg(vals)
            lo, hi = min(vals), max(vals)
            print(f"  {metric:<35s} {mu:>12.4f} {sd:>12.4f} {lo:>12.4f} {hi:>12.4f}")

print()

# ══════════════════════════════════════════════════════════════════════
# CSV-like raw dump
# ══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("RAW DATA (CSV format)")
print("=" * 80)

csv_cols = ["multiplier", "jitter", "seed_dir"] + METRICS
print(",".join(csv_cols))
for r in sorted(records, key=lambda x: (x["multiplier"], x["jitter"], x["seed_dir"])):
    print(",".join(str(r[c]) for c in csv_cols))

print()
print("Done.")
