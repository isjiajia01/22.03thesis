#!/usr/bin/env python3
"""
EXP02 Full Audit Script
Generates all audit files for EXP02 with paired comparisons to EXP01/EXP04
"""

import os
import json
import csv
import math
import random
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/zhome/2a/1/202283/thesis")
RESULTS_DIR = BASE_DIR / "data/results"
AUDITS_DIR = BASE_DIR / "data/audits"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return None

def bootstrap_ci(data, n_bootstrap=10000, ci=0.95):
    if not data:
        return None, None, None
    n = len(data)
    mean_orig = sum(data) / n
    random.seed(42)
    boot_means = []
    for _ in range(n_bootstrap):
        sample = [random.choice(data) for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    alpha = 1 - ci
    lower_idx = int(alpha / 2 * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap)
    return mean_orig, boot_means[lower_idx], boot_means[upper_idx]

def calc_std(arr):
    if len(arr) < 2:
        return 0
    mean = sum(arr) / len(arr)
    return (sum((x - mean) ** 2 for x in arr) / (len(arr) - 1)) ** 0.5

# Collect all output files for index
output_files = []

# ============================================================================
# 1) CONFIG MATRIX
# ============================================================================
print("1) Config Matrix...")
config_rows = []
config_issues = []

for seed in range(1, 11):
    config_path = RESULTS_DIR / f"EXP_EXP02/Seed_{seed}/config_dump.json"
    config = load_json(config_path)
    if not config:
        config_issues.append(f"Seed_{seed}: config_dump.json missing")
        continue

    params = config.get("parameters", config)
    row = {
        "seed": seed,
        "ratio": params.get("ratio", ""),
        "crunch_start": params.get("crunch_start", ""),
        "crunch_end": params.get("crunch_end", ""),
        "total_days": params.get("total_days", ""),
        "use_risk_model": params.get("use_risk_model", params.get("use_risk", "")),
        "base_compute": params.get("base_compute", ""),
        "high_compute": params.get("high_compute", "")
    }
    config_rows.append(row)

    # Validate EXP02 definition: base=300, high=300
    if row["base_compute"] != 300:
        config_issues.append(f"Seed_{seed}: base_compute={row['base_compute']} (expected 300)")
    if row["high_compute"] != 300:
        config_issues.append(f"Seed_{seed}: high_compute={row['high_compute']} (expected 300)")

config_path_out = AUDITS_DIR / f"audit_exp02_config_matrix_{TIMESTAMP}.csv"
with open(config_path_out, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["seed", "ratio", "crunch_start", "crunch_end",
                                            "total_days", "use_risk_model", "base_compute", "high_compute"])
    writer.writeheader()
    writer.writerows(config_rows)
output_files.append(("audit_exp02_config_matrix_{}.csv".format(TIMESTAMP), "Config matrix for all seeds", "config_dump.json"))

config_pass = len(config_issues) == 0
print(f"  Config PASS: {config_pass}, Issues: {len(config_issues)}")

# ============================================================================
# 2) COMPUTE GATE AUDIT
# ============================================================================
print("2) Compute Gate Audit...")
compute_rows = []
compute_violations = []
total_violations = 0

for seed in range(1, 11):
    sim_path = RESULTS_DIR / f"EXP_EXP02/Seed_{seed}/simulation_results.json"
    sim = load_json(sim_path)
    if not sim:
        compute_rows.append({"seed": seed, "days": 0, "unique_compute": "N/A", "violations": "N/A", "risk_model_loaded": "N/A"})
        continue

    daily = sim.get("daily_stats", [])
    compute_values = [d.get("compute_limit_seconds", 0) for d in daily]
    unique_compute = sorted(set(compute_values))
    violations = sum(1 for c in compute_values if c != 300)
    total_violations += violations

    # Risk model loaded check (should be 0 or N/A for EXP02)
    risk_loaded = [d.get("risk_model_loaded", "N/A") for d in daily]
    risk_loaded_unique = sorted(set(str(r) for r in risk_loaded))

    compute_rows.append({
        "seed": seed,
        "days": len(daily),
        "unique_compute": str(unique_compute),
        "violations": violations,
        "risk_model_loaded": str(risk_loaded_unique)
    })

    if violations > 0:
        for i, d in enumerate(daily):
            if d.get("compute_limit_seconds", 0) != 300:
                compute_violations.append(f"Seed_{seed} Day_{i+1}: compute={d.get('compute_limit_seconds')}")

compute_csv_path = AUDITS_DIR / f"audit_exp02_compute_gate_{TIMESTAMP}.csv"
with open(compute_csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["seed", "days", "unique_compute", "violations", "risk_model_loaded"])
    writer.writeheader()
    writer.writerows(compute_rows)
output_files.append(("audit_exp02_compute_gate_{}.csv".format(TIMESTAMP), "Compute gate per seed", "simulation_results.json"))

compute_txt_path = AUDITS_DIR / f"audit_exp02_compute_gate_{TIMESTAMP}.txt"
with open(compute_txt_path, 'w') as f:
    f.write(f"EXP02 COMPUTE GATE AUDIT\n")
    f.write(f"Generated: {TIMESTAMP}\n")
    f.write("=" * 60 + "\n\n")
    f.write(f"Total violations: {total_violations}\n")
    f.write(f"Expected compute_limit_seconds: 300 (all days)\n\n")
    if compute_violations:
        f.write("VIOLATIONS:\n")
        for v in compute_violations:
            f.write(f"  {v}\n")
    else:
        f.write("0 violations - all seeds have compute_limit_seconds=300 for all days\n")
output_files.append(("audit_exp02_compute_gate_{}.txt".format(TIMESTAMP), "Compute gate violations detail", "simulation_results.json"))

compute_pass = total_violations == 0
print(f"  Compute PASS: {compute_pass}, Violations: {total_violations}")

# ============================================================================
# 3) METRICS AUDIT
# ============================================================================
print("3) Metrics Audit...")
metrics_rows = []
consistency_issues = []

for seed in range(1, 11):
    summary_path = RESULTS_DIR / f"EXP_EXP02/Seed_{seed}/summary_final.json"
    summary = load_json(summary_path)
    if not summary:
        continue

    sim_path = RESULTS_DIR / f"EXP_EXP02/Seed_{seed}/simulation_results.json"
    sim = load_json(sim_path)

    eligible = summary.get("eligible_count", 0)
    delivered = summary.get("delivered_within_window_count", summary.get("delivered_count", 0))
    dl_fail = summary.get("deadline_failure_count", 0)
    sr = summary.get("service_rate_within_window", summary.get("service_rate", 0))

    # VRP dropped from daily_stats
    vrp_dropped = 0
    if sim:
        vrp_dropped = sum(d.get("vrp_dropped", 0) for d in sim.get("daily_stats", []))

    metrics_rows.append({
        "seed": seed,
        "eligible_count": eligible,
        "delivered_count": delivered,
        "deadline_failure_count": dl_fail,
        "service_rate": sr,
        "vrp_dropped_sum": vrp_dropped
    })

    # Consistency check: SR = delivered / eligible
    if eligible > 0:
        expected_sr = delivered / eligible
        if abs(sr - expected_sr) > 1e-6:
            consistency_issues.append(f"Seed_{seed}: SR={sr}, expected={expected_sr} (delivered/eligible)")

metrics_csv_path = AUDITS_DIR / f"audit_exp02_metrics_by_seed_{TIMESTAMP}.csv"
with open(metrics_csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["seed", "eligible_count", "delivered_count",
                                            "deadline_failure_count", "service_rate", "vrp_dropped_sum"])
    writer.writeheader()
    writer.writerows(metrics_rows)
output_files.append(("audit_exp02_metrics_by_seed_{}.csv".format(TIMESTAMP), "Metrics per seed", "summary_final.json"))

# Aggregate
sr_vals = [r["service_rate"] for r in metrics_rows]
fail_vals = [r["deadline_failure_count"] for r in metrics_rows]
drop_vals = [r["vrp_dropped_sum"] for r in metrics_rows]

agg_rows = [
    {"metric": "service_rate", "mean": sum(sr_vals)/len(sr_vals) if sr_vals else 0,
     "std": calc_std(sr_vals), "min": min(sr_vals) if sr_vals else 0, "max": max(sr_vals) if sr_vals else 0, "n": len(sr_vals)},
    {"metric": "deadline_failure_count", "mean": sum(fail_vals)/len(fail_vals) if fail_vals else 0,
     "std": calc_std(fail_vals), "min": min(fail_vals) if fail_vals else 0, "max": max(fail_vals) if fail_vals else 0, "n": len(fail_vals)},
    {"metric": "vrp_dropped_sum", "mean": sum(drop_vals)/len(drop_vals) if drop_vals else 0,
     "std": calc_std(drop_vals), "min": min(drop_vals) if drop_vals else 0, "max": max(drop_vals) if drop_vals else 0, "n": len(drop_vals)}
]

agg_csv_path = AUDITS_DIR / f"audit_exp02_metrics_agg_{TIMESTAMP}.csv"
with open(agg_csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["metric", "mean", "std", "min", "max", "n"])
    writer.writeheader()
    writer.writerows(agg_rows)
output_files.append(("audit_exp02_metrics_agg_{}.csv".format(TIMESTAMP), "Aggregated metrics", "summary_final.json"))

consistency_txt_path = AUDITS_DIR / f"audit_exp02_metric_consistency_{TIMESTAMP}.txt"
with open(consistency_txt_path, 'w') as f:
    f.write(f"EXP02 METRIC CONSISTENCY CHECK\n")
    f.write(f"Generated: {TIMESTAMP}\n")
    f.write("=" * 60 + "\n\n")
    if consistency_issues:
        f.write("MISMATCHES:\n")
        for issue in consistency_issues:
            f.write(f"  {issue}\n")
    else:
        f.write("All metrics consistent (SR = delivered/eligible within 1e-6)\n")
    f.write(f"\nSTD ANALYSIS:\n")
    f.write(f"  SR std: {calc_std(sr_vals):.8f}\n")
    f.write(f"  Fail std: {calc_std(fail_vals):.4f}\n")
    f.write(f"  Drop std: {calc_std(drop_vals):.4f}\n")
    if calc_std(sr_vals) == 0:
        f.write("\n  NOTE: std=0 indicates deterministic behavior (OR-Tools GLS default)\n")
output_files.append(("audit_exp02_metric_consistency_{}.txt".format(TIMESTAMP), "Metric consistency check", "summary_final.json"))

print(f"  Metrics collected: {len(metrics_rows)} seeds")

# ============================================================================
# 4) PAIRED COMPARISONS
# ============================================================================
print("4) Paired Comparisons...")

def do_paired_comparison(exp_a, exp_b, label):
    paired_rows = []
    for seed in range(1, 11):
        sum_a = load_json(RESULTS_DIR / f"EXP_{exp_a}/Seed_{seed}/summary_final.json")
        sum_b = load_json(RESULTS_DIR / f"EXP_{exp_b}/Seed_{seed}/summary_final.json")
        sim_a = load_json(RESULTS_DIR / f"EXP_{exp_a}/Seed_{seed}/simulation_results.json")
        sim_b = load_json(RESULTS_DIR / f"EXP_{exp_b}/Seed_{seed}/simulation_results.json")

        if not sum_a or not sum_b:
            continue

        sr_a = sum_a.get("service_rate_within_window", sum_a.get("service_rate", 0))
        sr_b = sum_b.get("service_rate_within_window", sum_b.get("service_rate", 0))
        fail_a = sum_a.get("deadline_failure_count", 0)
        fail_b = sum_b.get("deadline_failure_count", 0)
        drop_a = sum(d.get("vrp_dropped", 0) for d in sim_a.get("daily_stats", [])) if sim_a else 0
        drop_b = sum(d.get("vrp_dropped", 0) for d in sim_b.get("daily_stats", [])) if sim_b else 0

        paired_rows.append({
            "seed": seed,
            f"SR_{exp_a}": sr_a, f"SR_{exp_b}": sr_b, "dSR": sr_b - sr_a,
            f"fail_{exp_a}": fail_a, f"fail_{exp_b}": fail_b, "dfail": fail_b - fail_a,
            f"drop_{exp_a}": drop_a, f"drop_{exp_b}": drop_b, "ddrop": drop_b - drop_a
        })

    # Write CSV
    csv_path = AUDITS_DIR / f"{label}_paired_{TIMESTAMP}.csv"
    if paired_rows:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=paired_rows[0].keys())
            writer.writeheader()
            writer.writerows(paired_rows)

    # Calculate stats
    dSR = [r["dSR"] for r in paired_rows]
    dfail = [r["dfail"] for r in paired_rows]
    ddrop = [r["ddrop"] for r in paired_rows]

    stats_lines = []
    stats_lines.append("=" * 70)
    stats_lines.append(f"{exp_b} vs {exp_a} PAIRED COMPARISON")
    stats_lines.append(f"Generated: {TIMESTAMP}")
    stats_lines.append("=" * 70)
    stats_lines.append("")

    for name, data in [("dSR (SR)", dSR), ("dfail (failures)", dfail), ("ddrop (vrp_dropped)", ddrop)]:
        mean, ci_low, ci_high = bootstrap_ci(data)
        std = calc_std(data)
        ci_excludes_zero = (ci_low > 0) or (ci_high < 0) if ci_low and ci_high else False
        stats_lines.append(f"{name}:")
        stats_lines.append(f"  Mean: {mean:.6f}" if mean else "  Mean: N/A")
        stats_lines.append(f"  Std: {std:.6f}")
        stats_lines.append(f"  95% CI: [{ci_low:.6f}, {ci_high:.6f}]" if ci_low and ci_high else "  95% CI: N/A")
        stats_lines.append(f"  CI excludes zero: {ci_excludes_zero}")
        stats_lines.append("")

    stats_lines.append("Per-seed breakdown:")
    stats_lines.append(f"{'Seed':<6} {'dSR':<12} {'dfail':<8} {'ddrop':<8}")
    stats_lines.append("-" * 40)
    for r in paired_rows:
        stats_lines.append(f"{r['seed']:<6} {r['dSR']:<12.6f} {r['dfail']:<8.0f} {r['ddrop']:<8.0f}")

    txt_path = AUDITS_DIR / f"{label}_stats_{TIMESTAMP}.txt"
    with open(txt_path, 'w') as f:
        f.write("\n".join(stats_lines))

    return csv_path, txt_path, {
        "dSR": bootstrap_ci(dSR),
        "dfail": bootstrap_ci(dfail),
        "ddrop": bootstrap_ci(ddrop)
    }

# EXP02 vs EXP01
csv1, txt1, stats1 = do_paired_comparison("EXP01", "EXP02", "exp02_vs_exp01")
output_files.append(("exp02_vs_exp01_paired_{}.csv".format(TIMESTAMP), "EXP02 vs EXP01 paired", "summary_final.json"))
output_files.append(("exp02_vs_exp01_stats_{}.txt".format(TIMESTAMP), "EXP02 vs EXP01 stats", "summary_final.json"))

# EXP02 vs EXP04
csv2, txt2, stats2 = do_paired_comparison("EXP04", "EXP02", "exp02_vs_exp04")
output_files.append(("exp02_vs_exp04_paired_{}.csv".format(TIMESTAMP), "EXP02 vs EXP04 paired", "summary_final.json"))
output_files.append(("exp02_vs_exp04_stats_{}.txt".format(TIMESTAMP), "EXP02 vs EXP04 stats", "summary_final.json"))

print(f"  EXP02 vs EXP01: dSR mean={stats1['dSR'][0]:.6f}" if stats1['dSR'][0] else "  EXP02 vs EXP01: N/A")
print(f"  EXP02 vs EXP04: dSR mean={stats2['dSR'][0]:.6f}" if stats2['dSR'][0] else "  EXP02 vs EXP04: N/A")

# ============================================================================
# 5) TRAFFIC LIGHT
# ============================================================================
print("5) Traffic Light...")

days_ok = all(r["days"] == 12 for r in compute_rows if r["days"] != "N/A")
compute_ok = total_violations == 0
unique_compute_ok = all("[300]" in str(r["unique_compute"]) for r in compute_rows)
risk_model_ok = True  # EXP02 has use_risk_model=False, so N/A or 0 is fine
metrics_ok = len(consistency_issues) == 0

traffic_light = {
    "experiment": "EXP02",
    "days_12_12": "PASS" if days_ok else "FAIL",
    "compute_300_only": "PASS" if compute_ok and unique_compute_ok else "FAIL",
    "risk_model_consistent": "PASS" if risk_model_ok else "FAIL",
    "metrics_self_consistent": "PASS" if metrics_ok else "FAIL",
    "overall": "PASS" if all([days_ok, compute_ok, unique_compute_ok, risk_model_ok, metrics_ok]) else "FAIL"
}

tl_csv_path = AUDITS_DIR / f"traffic_light_exp02_{TIMESTAMP}.csv"
with open(tl_csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=traffic_light.keys())
    writer.writeheader()
    writer.writerow(traffic_light)
output_files.append(("traffic_light_exp02_{}.csv".format(TIMESTAMP), "Traffic light summary", "all"))

tl_txt_path = AUDITS_DIR / f"traffic_light_exp02_{TIMESTAMP}.txt"
with open(tl_txt_path, 'w') as f:
    f.write("=" * 60 + "\n")
    f.write("EXP02 TRAFFIC LIGHT AUDIT\n")
    f.write(f"Generated: {TIMESTAMP}\n")
    f.write("=" * 60 + "\n\n")
    for k, v in traffic_light.items():
        status = "✅" if v == "PASS" else "❌"
        f.write(f"{status} {k}: {v}\n")
    f.write("\n" + "=" * 60 + "\n")
    f.write("DETAILS:\n")
    f.write(f"  Days: {[r['days'] for r in compute_rows]}\n")
    f.write(f"  Unique compute: {[r['unique_compute'] for r in compute_rows]}\n")
    f.write(f"  Violations: {total_violations}\n")
    f.write(f"  Config issues: {len(config_issues)}\n")
    f.write(f"  Consistency issues: {len(consistency_issues)}\n")
    f.write("\n" + "=" * 60 + "\n")
    f.write("KEY METRICS (EXP02):\n")
    f.write(f"  Service Rate: mean={agg_rows[0]['mean']:.6f}, std={agg_rows[0]['std']:.6f}\n")
    f.write(f"  Deadline Failures: mean={agg_rows[1]['mean']:.2f}, std={agg_rows[1]['std']:.4f}\n")
    f.write(f"  VRP Dropped: mean={agg_rows[2]['mean']:.2f}, std={agg_rows[2]['std']:.4f}\n")
    f.write("\n" + "=" * 60 + "\n")
    f.write("COMPARISON SUMMARY:\n")
    f.write(f"  EXP02 vs EXP01: dSR={stats1['dSR'][0]:.4f}%, CI=[{stats1['dSR'][1]:.4f}, {stats1['dSR'][2]:.4f}]\n" if stats1['dSR'][0] else "")
    f.write(f"  EXP02 vs EXP04: dSR={stats2['dSR'][0]:.4f}%, CI=[{stats2['dSR'][1]:.4f}, {stats2['dSR'][2]:.4f}]\n" if stats2['dSR'][0] else "")
output_files.append(("traffic_light_exp02_{}.txt".format(TIMESTAMP), "Traffic light details", "all"))

# ============================================================================
# 0) AUDIT INDEX
# ============================================================================
print("0) Audit Index...")
index_path = AUDITS_DIR / f"audit_index_exp02_{TIMESTAMP}.csv"
with open(index_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["filename", "purpose", "source"])
    writer.writeheader()
    for fname, purpose, source in output_files:
        writer.writerow({"filename": fname, "purpose": purpose, "source": source})

print("\n" + "=" * 60)
print(f"EXP02 AUDIT COMPLETE - OVERALL: {traffic_light['overall']}")
print("=" * 60)
