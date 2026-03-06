#!/usr/bin/env python3
"""Aggregate EXP15c results across seeds for each (variant, ratio, shift) combination."""

import os
import json
from pathlib import Path
from collections import defaultdict
import statistics

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "results" / "EXP15" / "EXP15c"

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
records = []

for combo_dir in sorted(os.listdir(BASE)):
    combo_path = os.path.join(BASE, combo_dir)
    if not os.path.isdir(combo_path):
        continue

    for seed_dir in sorted(os.listdir(combo_path)):
        seed_path = os.path.join(combo_path, seed_dir)
        if not os.path.isdir(seed_path):
            continue

        summary_path = os.path.join(seed_path, "DEFAULT", "EXP15c", "summary_final.json")
        ood_path = os.path.join(seed_path, "DEFAULT", "EXP15c", "ood_labels.json")

        if not os.path.isfile(summary_path) or not os.path.isfile(ood_path):
            print(f"  [WARN] missing files in {seed_path}")
            continue

        with open(summary_path) as f:
            summary = json.load(f)
        with open(ood_path) as f:
            ood = json.load(f)

        rec = {
            "variant": ood["feature_variant"],
            "ratio": ood["crunch_ratio_setting"],
            "shift": ood["crunch_window_shift_setting"],
            "seed_dir": seed_dir,
        }
        for m in METRICS:
            rec[m] = summary[m]
        records.append(rec)

print(f"Total records loaded: {len(records)}")
print()

# ── Group by (variant, ratio, shift) ────────────────────────────────
grouped = defaultdict(list)
for r in records:
    grouped[(r["variant"], r["ratio"], r["shift"])].append(r)

variants = sorted(set(k[0] for k in grouped))
conditions = sorted(set((k[1], k[2]) for k in grouped))

print(f"Variants   : {variants}")
print(f"Conditions : {conditions}")
print(f"Cells with data: {len(grouped)}")
print()


# ── Helper ───────────────────────────────────────────────────────────
def agg(values):
    """Return (mean, std, n)."""
    n = len(values)
    mu = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    return mu, sd, n


# ══════════════════════════════════════════════════════════════════════
# TABLE 1 — Service Rate by variant per condition
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 1: Service Rate Within Window  (mean +/- std)")
print("  Rows = (ratio, shift), Columns = variant")
print("=" * 100)

header = f"{'condition':>16s}" + "".join(f"{v:>24s}" for v in variants)
print(header)
print("-" * len(header))

for ratio, shift in conditions:
    row = f"{'r='+str(ratio)+' s='+str(shift):>16s}"
    for v in variants:
        recs = grouped.get((v, ratio, shift), [])
        if recs:
            mu, sd, n = agg([r["service_rate_within_window"] for r in recs])
            row += f"  {mu:.4f}+/-{sd:.4f} ({n:>2})"
        else:
            row += f"{'---':>24s}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 2 — Penalized Cost by variant per condition
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 2: Penalized Cost  (mean +/- std)")
print("  Rows = (ratio, shift), Columns = variant")
print("=" * 100)

header = f"{'condition':>16s}" + "".join(f"{v:>28s}" for v in variants)
print(header)
print("-" * len(header))

for ratio, shift in conditions:
    row = f"{'r='+str(ratio)+' s='+str(shift):>16s}"
    for v in variants:
        recs = grouped.get((v, ratio, shift), [])
        if recs:
            mu, sd, n = agg([r["penalized_cost"] for r in recs])
            row += f"  {mu:>10.1f}+/-{sd:>8.1f} ({n:>2})"
        else:
            row += f"{'---':>28s}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 3 — Deadline Failure Count by variant per condition
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 3: Deadline Failure Count  (mean +/- std)")
print("  Rows = (ratio, shift), Columns = variant")
print("=" * 100)

header = f"{'condition':>16s}" + "".join(f"{v:>24s}" for v in variants)
print(header)
print("-" * len(header))

for ratio, shift in conditions:
    row = f"{'r='+str(ratio)+' s='+str(shift):>16s}"
    for v in variants:
        recs = grouped.get((v, ratio, shift), [])
        if recs:
            mu, sd, n = agg([r["deadline_failure_count"] for r in recs])
            row += f"  {mu:>8.1f}+/-{sd:>5.1f} ({n:>2})"
        else:
            row += f"{'---':>24s}"
    print(row)

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 4 — Full metric summary per (variant, ratio, shift)
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("TABLE 4: Full Metric Summary per (variant, ratio, shift)")
print("=" * 100)

for v in variants:
    for ratio, shift in conditions:
        recs = grouped.get((v, ratio, shift), [])
        if not recs:
            continue
        n = len(recs)
        print(f"\n  variant={v}, ratio={ratio}, shift={shift}  (n={n} seeds)")
        print(f"  {'metric':<35s} {'mean':>12s} {'std':>12s} {'min':>12s} {'max':>12s}")
        print(f"  {'-'*35} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        for metric in METRICS:
            vals = [r[metric] for r in recs]
            mu, sd, _ = agg(vals)
            lo, hi = min(vals), max(vals)
            print(f"  {metric:<35s} {mu:>12.4f} {sd:>12.4f} {lo:>12.4f} {hi:>12.4f}")

print()

# ══════════════════════════════════════════════════════════════════════
# TABLE 5 — CSV-like raw dump
# ══════════════════════════════════════════════════════════════════════
print("=" * 100)
print("RAW DATA (CSV format)")
print("=" * 100)

csv_cols = ["variant", "ratio", "shift", "seed_dir"] + METRICS
print(",".join(csv_cols))
for r in sorted(records, key=lambda x: (x["variant"], x["ratio"], x["shift"], x["seed_dir"])):
    print(",".join(str(r[c]) for c in csv_cols))

print()
print("Done.")
