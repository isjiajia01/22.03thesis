#!/usr/bin/env python3
"""
Full audit of EXP15c (EXP16b3 batch) results.
Checklist: completeness, config consistency, result sanity, aggregation, paired tests.
"""

import os, json, csv, re, sys, statistics
from collections import defaultdict
from pathlib import Path
from itertools import product

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "results" / "EXP15" / "EXP15c"
LOG_BASE = ROOT / "hpc_logs" / "exp16"
OUT_DIR = BASE / "_audit"
OUT_DIR.mkdir(exist_ok=True)

# ── Expected grid ────────────────────────────────────────────────────
VARIANTS_FULL_GRID = ["full", "no_calendar", "no_calendar_aug"]
RATIOS = [0.45, 0.50, 0.55, 0.59, 0.60, 0.62, 0.65, 0.70]
SHIFTS = [-2, -1, 0, 1, 2]
SEEDS = list(range(1, 11))
EXPECTED_PER_VARIANT = len(RATIOS) * len(SHIFTS) * len(SEEDS)  # 400

# no_ratio only had 5 conditions from original EXP15c
NO_RATIO_CONDITIONS = [
    (0.59, 0), (0.59, -2), (0.55, -2), (0.50, -1), (0.65, -2)
]

METRICS = [
    "service_rate_within_window",
    "penalized_cost",
    "cost_raw",
    "cost_per_order",
    "deadline_failure_count",
    "eligible_count",
    "delivered_within_window_count",
]

REQUIRED_FILES = ["summary_final.json", "ood_labels.json"]
OPTIONAL_FILES = ["allocator_config_dump.json", "daily_stats.csv", "failed_orders.csv"]

EXPECTED_MODEL_PATHS = {
    "full": "allocator_Q_lambda_0.05_hgb.joblib",
    "no_ratio": "allocator_Q_lambda_0.05_hgb_no_ratio.joblib",
    "no_calendar": "allocator_Q_lambda_0.05_hgb_no_calendar.joblib",
    "no_calendar_aug": "allocator_Q_lambda_0.05_hgb_no_calendar_aug.joblib",
}


# =====================================================================
# 0) HELPERS
# =====================================================================
def extract_seed_num(dirname):
    m = re.match(r"seed_(\d+)_", dirname)
    return int(m.group(1)) if m else None


def has_required_files(d):
    inner = d / "DEFAULT" / "EXP15c"
    return all((inner / rf).is_file() for rf in REQUIRED_FILES)


def pick_best_seed_dir(seed_dirs):
    """Among duplicate seed dirs for the same seed number, prefer one with
    actual data; among those, pick the latest mtime."""
    by_seed = defaultdict(list)
    for d in seed_dirs:
        sn = extract_seed_num(d.name)
        if sn is not None:
            by_seed[sn].append(d)
    best = {}
    for sn, dirs in by_seed.items():
        with_data = [d for d in dirs if has_required_files(d)]
        candidates = with_data if with_data else dirs
        best[sn] = max(candidates, key=lambda d: d.stat().st_mtime)
    return best  # {seed_num: Path}


# =====================================================================
# 1) JOB LOG SCAN
# =====================================================================
print("=" * 80)
print("SECTION 1: HPC Job Log Scan")
print("=" * 80)

err_files = sorted(LOG_BASE.glob("EXP16b3_*.err"))
non_empty_errs = []
for ef in err_files:
    if ef.stat().st_size > 0:
        non_empty_errs.append(ef)

print(f"Total .err files found: {len(err_files)}")
print(f"Non-empty .err files:   {len(non_empty_errs)}")

err_details = []
for ef in non_empty_errs[:20]:  # sample first 20
    with open(ef) as f:
        content = f.read(2000)
    # Check for real errors vs just warnings
    has_error = any(kw in content.lower() for kw in ["error", "traceback", "exit", "failed", "killed", "oom"])
    err_details.append({"file": ef.name, "size": ef.stat().st_size, "has_error_kw": has_error, "snippet": content[:300]})

real_errors = [e for e in err_details if e["has_error_kw"]]
print(f"Sampled {len(err_details)} non-empty .err files; {len(real_errors)} contain error keywords")
if real_errors:
    for e in real_errors[:5]:
        print(f"  ERROR: {e['file']} ({e['size']}B): {e['snippet'][:200]}")
else:
    print("  No error keywords found in sampled .err files.")

# Also check .out files for "Run time" (LSF completion marker)
out_files = sorted(LOG_BASE.glob("EXP16b3_*.out"))
print(f"Total .out files found: {len(out_files)}")

# Count by job type
for prefix in ["EXP16b3_full", "EXP16b3_nocal_", "EXP16b3_aug"]:
    outs = [f for f in out_files if prefix in f.name]
    errs = [f for f in err_files if prefix in f.name]
    print(f"  {prefix:25s}: {len(outs)} .out, {len(errs)} .err")

print()


# =====================================================================
# 2) RUN DIRECTORY INVENTORY & FILE COMPLETENESS
# =====================================================================
print("=" * 80)
print("SECTION 2: Run Directory Inventory & File Completeness")
print("=" * 80)

all_records = []
fail_list = []
traffic_light = {}  # (variant, ratio, shift, seed) -> PASS/FAIL

# Scan all condition directories
for combo_dir in sorted(BASE.iterdir()):
    if not combo_dir.is_dir() or combo_dir.name.startswith("_"):
        continue

    # Parse variant from directory name
    # e.g. "full_ratio_0.59_shift_0", "no_calendar_aug_ratio_0.59_shift_0"
    name = combo_dir.name
    m = re.match(r"(.+?)_ratio_([\d.]+)_shift_(-?\d+)", name)
    if not m:
        continue
    variant = m.group(1)
    ratio = float(m.group(2))
    shift = int(m.group(3))

    # Get all seed directories, deduplicate
    seed_dirs = [d for d in combo_dir.iterdir() if d.is_dir() and d.name.startswith("seed_")]
    deduped = pick_best_seed_dir(seed_dirs)

    for seed_num, seed_path in sorted(deduped.items()):
        inner = seed_path / "DEFAULT" / "EXP15c"
        key = (variant, ratio, shift, seed_num)

        # Check required files
        missing_req = []
        for rf in REQUIRED_FILES:
            if not (inner / rf).is_file():
                missing_req.append(rf)

        missing_opt = []
        for of in OPTIONAL_FILES:
            if not (inner / of).is_file():
                missing_opt.append(of)

        if missing_req:
            traffic_light[key] = "FAIL"
            fail_list.append({"variant": variant, "ratio": ratio, "shift": shift,
                              "seed": seed_num, "dir": str(seed_path),
                              "missing": missing_req})
            continue

        # Load data
        try:
            with open(inner / "summary_final.json") as f:
                summary = json.load(f)
            with open(inner / "ood_labels.json") as f:
                ood = json.load(f)
        except Exception as e:
            traffic_light[key] = "FAIL"
            fail_list.append({"variant": variant, "ratio": ratio, "shift": shift,
                              "seed": seed_num, "dir": str(seed_path),
                              "missing": [f"JSON parse error: {e}"]})
            continue

        # Validate ood_labels fields
        config_issues = []
        if ood.get("feature_variant") != variant:
            config_issues.append(f"variant mismatch: dir={variant} ood={ood.get('feature_variant')}")
        if abs(ood.get("crunch_ratio_setting", -1) - ratio) > 0.001:
            config_issues.append(f"ratio mismatch: dir={ratio} ood={ood.get('crunch_ratio_setting')}")
        if ood.get("crunch_window_shift_setting") != shift:
            config_issues.append(f"shift mismatch: dir={shift} ood={ood.get('crunch_window_shift_setting')}")

        # Validate model path
        q_path = ood.get("q_model_path", "")
        expected_model = EXPECTED_MODEL_PATHS.get(variant, "")
        if expected_model and expected_model not in q_path:
            config_issues.append(f"model path wrong: expected *{expected_model}, got {q_path}")

        if config_issues:
            traffic_light[key] = "FAIL"
            fail_list.append({"variant": variant, "ratio": ratio, "shift": shift,
                              "seed": seed_num, "dir": str(seed_path),
                              "missing": config_issues})
            continue

        # Check all metrics present
        missing_metrics = [m for m in METRICS if m not in summary]
        if missing_metrics:
            traffic_light[key] = "FAIL"
            fail_list.append({"variant": variant, "ratio": ratio, "shift": shift,
                              "seed": seed_num, "dir": str(seed_path),
                              "missing": [f"missing metrics: {missing_metrics}"]})
            continue

        traffic_light[key] = "PASS"
        rec = {
            "variant": variant, "ratio": ratio, "shift": shift, "seed": seed_num,
            "seed_dir": seed_path.name,
        }
        for metric in METRICS:
            rec[metric] = summary[metric]

        # Also grab allocator config if present
        cfg_path = inner / "allocator_config_dump.json"
        if cfg_path.is_file():
            try:
                with open(cfg_path) as f:
                    acfg = json.load(f)
                eps_sched = acfg.get("epsilon_schedule", {})
                rec["_alloc_eps_start"] = eps_sched.get("eps_start")
                rec["_alloc_eps_end"] = eps_sched.get("eps_end")
                rec["_alloc_eps_kind"] = eps_sched.get("kind")
                rec["_alloc_warmup_days"] = eps_sched.get("warmup_days")
                guardrails = acfg.get("guardrails", {})
                rec["_alloc_guardrail_enabled"] = guardrails.get("enabled")
                rec["_alloc_lambda"] = acfg.get("lambda_compute")
                rec["_alloc_policy"] = acfg.get("policy")
                rec["_alloc_q_model"] = acfg.get("q_model_path")
            except:
                pass

        all_records.append(rec)

# ── Summary counts ──
print(f"\nTotal PASS records: {len(all_records)}")
print(f"Total FAIL records: {len(fail_list)}")

# Count by variant
for v in VARIANTS_FULL_GRID + ["no_ratio"]:
    n = sum(1 for r in all_records if r["variant"] == v)
    expected = EXPECTED_PER_VARIANT if v in VARIANTS_FULL_GRID else len(NO_RATIO_CONDITIONS) * len(SEEDS)
    status = "OK" if n == expected else "INCOMPLETE"
    print(f"  {v:20s}: {n:4d} / {expected:4d}  [{status}]")

# Missing conditions
print("\nMissing conditions per variant:")
for v in VARIANTS_FULL_GRID:
    found = set((r["ratio"], r["shift"]) for r in all_records if r["variant"] == v)
    expected = set(product(RATIOS, SHIFTS))
    missing = expected - found
    if missing:
        print(f"  {v}: MISSING {len(missing)} conditions: {sorted(missing)}")
    else:
        print(f"  {v}: all 40 conditions present")

# Missing seeds
print("\nConditions with < 10 seeds:")
grouped_counts = defaultdict(int)
for r in all_records:
    grouped_counts[(r["variant"], r["ratio"], r["shift"])] += 1
for key, cnt in sorted(grouped_counts.items()):
    if cnt < 10:
        print(f"  {key}: only {cnt} seeds")

print()


# =====================================================================
# 3) CONFIG CONSISTENCY (allocator params)
# =====================================================================
print("=" * 80)
print("SECTION 3: Allocator Config Consistency")
print("=" * 80)

eps_start_vals = set()
eps_end_vals = set()
eps_kind_vals = set()
warmup_vals = set()
gr_vals = set()
lambda_vals = set()
policy_vals = set()
model_mismatch = []
for r in all_records:
    if "_alloc_eps_start" in r:
        eps_start_vals.add(r["_alloc_eps_start"])
    if "_alloc_eps_end" in r:
        eps_end_vals.add(r["_alloc_eps_end"])
    if "_alloc_eps_kind" in r:
        eps_kind_vals.add(r["_alloc_eps_kind"])
    if "_alloc_warmup_days" in r:
        warmup_vals.add(r["_alloc_warmup_days"])
    if "_alloc_guardrail_enabled" in r:
        gr_vals.add(r["_alloc_guardrail_enabled"])
    if "_alloc_lambda" in r:
        lambda_vals.add(r["_alloc_lambda"])
    if "_alloc_policy" in r:
        policy_vals.add(r["_alloc_policy"])
    if "_alloc_q_model" in r:
        expected_model = EXPECTED_MODEL_PATHS.get(r["variant"], "")
        if expected_model and expected_model not in r["_alloc_q_model"]:
            model_mismatch.append((r["variant"], r["ratio"], r["shift"], r["seed"], r["_alloc_q_model"]))

n_with_cfg = sum(1 for r in all_records if "_alloc_eps_start" in r)
print(f"Runs with allocator config dump: {n_with_cfg} / {len(all_records)}")
print(f"  epsilon_schedule.kind:       {eps_kind_vals}")
print(f"  epsilon_schedule.eps_start:  {eps_start_vals}")
print(f"  epsilon_schedule.eps_end:    {eps_end_vals}")
print(f"  epsilon_schedule.warmup_days:{warmup_vals}")
print(f"  guardrails.enabled:          {gr_vals}")
print(f"  lambda_compute:              {lambda_vals}")
print(f"  policy:                      {policy_vals}")
print(f"  q_model_path mismatches:     {len(model_mismatch)}")
if model_mismatch:
    for mm in model_mismatch[:5]:
        print(f"    {mm}")
print()


# =====================================================================
# 4) RESULT SANITY CHECKS
# =====================================================================
print("=" * 80)
print("SECTION 4: Result Sanity Checks")
print("=" * 80)

grouped = defaultdict(list)
for r in all_records:
    grouped[(r["variant"], r["ratio"], r["shift"])].append(r)


def agg(vals):
    n = len(vals)
    mu = statistics.mean(vals) if n else 0
    sd = statistics.stdev(vals) if n > 1 else 0
    return mu, sd, n


# 4a) ID condition (r=0.59, s=0) — should be similar across variants
print("\n4a) ID condition (ratio=0.59, shift=0) — cross-variant comparison:")
print(f"  {'variant':20s} {'SR mean':>10s} {'SR std':>10s} {'pen_cost':>12s} {'failures':>10s}  n")
for v in VARIANTS_FULL_GRID + ["no_ratio"]:
    recs = grouped.get((v, 0.59, 0), [])
    if not recs:
        print(f"  {v:20s}  --- no data ---")
        continue
    sr_mu, sr_sd, n = agg([r["service_rate_within_window"] for r in recs])
    pc_mu, _, _ = agg([r["penalized_cost"] for r in recs])
    fc_mu, _, _ = agg([r["deadline_failure_count"] for r in recs])
    print(f"  {v:20s} {sr_mu:10.4f} {sr_sd:10.4f} {pc_mu:12.1f} {fc_mu:10.1f}  {n}")

# 4b) OOD trend: shift=-2 should be worse than shift=0
print("\n4b) OOD trend: shift effect at ratio=0.59 (full variant)")
print(f"  {'shift':>6s} {'SR mean':>10s} {'failures':>10s}  n")
for s in SHIFTS:
    recs = grouped.get(("full", 0.59, s), [])
    if not recs:
        continue
    sr_mu, _, n = agg([r["service_rate_within_window"] for r in recs])
    fc_mu, _, _ = agg([r["deadline_failure_count"] for r in recs])
    print(f"  {s:6d} {sr_mu:10.4f} {fc_mu:10.1f}  {n}")

# 4c) OOD trend: higher ratio → higher SR
print("\n4c) OOD trend: ratio effect at shift=0 (full variant)")
print(f"  {'ratio':>6s} {'SR mean':>10s} {'failures':>10s}  n")
for r_val in RATIOS:
    recs = grouped.get(("full", r_val, 0), [])
    if not recs:
        continue
    sr_mu, _, n = agg([r["service_rate_within_window"] for r in recs])
    fc_mu, _, _ = agg([r["deadline_failure_count"] for r in recs])
    print(f"  {r_val:6.2f} {sr_mu:10.4f} {fc_mu:10.1f}  {n}")

print()


# =====================================================================
# 5) AGGREGATION TABLE (CSV)
# =====================================================================
print("=" * 80)
print("SECTION 5: Generating Aggregation Tables")
print("=" * 80)

agg_rows = []
for (v, ratio, shift), recs in sorted(grouped.items()):
    row = {"variant": v, "ratio": ratio, "shift": shift, "n_seeds": len(recs)}
    for m in METRICS:
        vals = [r[m] for r in recs]
        mu, sd, _ = agg(vals)
        row[f"{m}_mean"] = round(mu, 6)
        row[f"{m}_std"] = round(sd, 6)
    agg_rows.append(row)

agg_csv = OUT_DIR / "aggregated_by_variant_ratio_shift.csv"
fieldnames = ["variant", "ratio", "shift", "n_seeds"]
for m in METRICS:
    fieldnames += [f"{m}_mean", f"{m}_std"]

with open(agg_csv, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(agg_rows)
print(f"  Wrote: {agg_csv}")


# =====================================================================
# 6) PAIRED-BY-SEED COMPARISON: full vs no_calendar, full vs no_calendar_aug
# =====================================================================
print("\n" + "=" * 80)
print("SECTION 6: Paired-by-Seed Comparisons")
print("=" * 80)

import math


def paired_t_test(diffs):
    """Two-sided paired t-test. Returns (mean_diff, se, t_stat, p_value, ci_lo, ci_hi)."""
    n = len(diffs)
    if n < 2:
        return (0, 0, 0, 1.0, 0, 0)
    mu = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    se = sd / math.sqrt(n)
    if se == 0:
        return (mu, 0, float('inf'), 0.0, mu, mu)
    t_stat = mu / se
    # Approximate two-sided p-value using normal (n>=10 so reasonable)
    # For proper t-distribution, would need scipy, but this is a sanity check
    from math import erf
    z = abs(t_stat)
    p_approx = 2 * (1 - 0.5 * (1 + erf(z / math.sqrt(2))))
    ci_lo = mu - 1.96 * se
    ci_hi = mu + 1.96 * se
    return (mu, se, t_stat, p_approx, ci_lo, ci_hi)


# Build seed-indexed lookup: (variant, ratio, shift, seed) -> record
seed_lookup = {}
for r in all_records:
    seed_lookup[(r["variant"], r["ratio"], r["shift"], r["seed"])] = r

comparisons = [
    ("full", "no_calendar"),
    ("full", "no_calendar_aug"),
]

paired_rows = []
for v_base, v_ablated in comparisons:
    print(f"\n  Comparison: {v_base} vs {v_ablated}")
    print(f"  {'condition':>16s} {'metric':>35s} {'delta_mean':>12s} {'CI_lo':>10s} {'CI_hi':>10s} {'p_value':>10s}  n")

    for ratio in RATIOS:
        for shift in SHIFTS:
            # Find paired seeds
            paired_seeds = []
            for s in SEEDS:
                base_rec = seed_lookup.get((v_base, ratio, shift, s))
                abl_rec = seed_lookup.get((v_ablated, ratio, shift, s))
                if base_rec and abl_rec:
                    paired_seeds.append((base_rec, abl_rec))

            if len(paired_seeds) < 2:
                continue

            for m in ["service_rate_within_window", "penalized_cost", "deadline_failure_count"]:
                diffs = [b[m] - a[m] for b, a in paired_seeds]
                mu_d, se_d, t_stat, p_val, ci_lo, ci_hi = paired_t_test(diffs)
                cond_str = f"r={ratio} s={shift}"
                print(f"  {cond_str:>16s} {m:>35s} {mu_d:12.4f} {ci_lo:10.4f} {ci_hi:10.4f} {p_val:10.4f}  {len(paired_seeds)}")

                paired_rows.append({
                    "comparison": f"{v_base}_vs_{v_ablated}",
                    "ratio": ratio, "shift": shift,
                    "metric": m,
                    "n_pairs": len(paired_seeds),
                    "delta_mean": round(mu_d, 6),
                    "delta_se": round(se_d, 6),
                    "ci_lo": round(ci_lo, 6),
                    "ci_hi": round(ci_hi, 6),
                    "t_stat": round(t_stat, 4),
                    "p_value": round(p_val, 6),
                })

paired_csv = OUT_DIR / "paired_comparisons.csv"
if paired_rows:
    with open(paired_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=paired_rows[0].keys())
        w.writeheader()
        w.writerows(paired_rows)
    print(f"\n  Wrote: {paired_csv}")


# =====================================================================
# 7) WRITE AUDIT INDEX & TRAFFIC LIGHT
# =====================================================================
print("\n" + "=" * 80)
print("SECTION 7: Audit Index & Traffic Light")
print("=" * 80)

# Traffic light summary
tl_pass = sum(1 for v in traffic_light.values() if v == "PASS")
tl_fail = sum(1 for v in traffic_light.values() if v == "FAIL")
print(f"  PASS: {tl_pass}")
print(f"  FAIL: {tl_fail}")

# Write traffic light
tl_path = OUT_DIR / "traffic_light_all.json"
tl_data = {
    "summary": {"PASS": tl_pass, "FAIL": tl_fail, "total": tl_pass + tl_fail},
    "details": {f"{v}|r={r}|s={s}|seed={sd}": status
                for (v, r, s, sd), status in sorted(traffic_light.items())}
}
with open(tl_path, "w") as f:
    json.dump(tl_data, f, indent=2)
print(f"  Wrote: {tl_path}")

# Write fail list
fail_path = OUT_DIR / "fail_list.json"
with open(fail_path, "w") as f:
    json.dump(fail_list, f, indent=2, default=str)
print(f"  Wrote: {fail_path}")

# Write audit index
audit_index = {
    "experiment": "EXP15c (EXP16b3 batch)",
    "variants_audited": VARIANTS_FULL_GRID + ["no_ratio"],
    "expected_grid": {
        "ratios": RATIOS,
        "shifts": SHIFTS,
        "seeds": SEEDS,
    },
    "counts": {},
    "traffic_light_summary": {"PASS": tl_pass, "FAIL": tl_fail},
    "config_frozen": {
        "epsilon_schedule_kind": list(eps_kind_vals),
        "epsilon_start": list(eps_start_vals),
        "epsilon_end": list(eps_end_vals),
        "warmup_days": list(warmup_vals),
        "guardrails_enabled": list(gr_vals),
        "lambda_compute": list(lambda_vals),
        "policy": list(policy_vals),
        "q_model_mismatches": len(model_mismatch),
    },
    "output_files": {
        "aggregated_csv": str(agg_csv),
        "paired_csv": str(paired_csv),
        "traffic_light": str(tl_path),
        "fail_list": str(fail_path),
    }
}
for v in VARIANTS_FULL_GRID + ["no_ratio"]:
    n = sum(1 for r in all_records if r["variant"] == v)
    expected = EXPECTED_PER_VARIANT if v in VARIANTS_FULL_GRID else len(NO_RATIO_CONDITIONS) * len(SEEDS)
    audit_index["counts"][v] = {"found": n, "expected": expected, "complete": n == expected}

idx_path = OUT_DIR / "audit_index.json"
with open(idx_path, "w") as f:
    json.dump(audit_index, f, indent=2)
print(f"  Wrote: {idx_path}")

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
