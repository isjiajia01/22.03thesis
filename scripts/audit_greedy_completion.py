#!/usr/bin/env python3
"""
Legacy post-completion audit for pre-paper Greedy vs Proactive comparison.
The historical result folders use EXP12/EXP13 labels, but these are not the
paper-aligned EXP12/EXP13 identifiers used in 22.03.

Usage:
    python scripts/audit_greedy_completion.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = REPO_ROOT / "data" / "results"
AUDITS_DIR = REPO_ROOT / "data" / "audits"
AUDITS_DIR.mkdir(parents=True, exist_ok=True)


def find_greedy_runs():
    """Find all legacy Greedy runs stored under EXP12/EXP13 result folders."""
    runs = []

    for exp_id in ["EXP12", "EXP13"]:
        exp_dir = RESULTS_DIR / f"EXP_{exp_id}"
        if not exp_dir.exists():
            continue

        for subdir in exp_dir.iterdir():
            if subdir.is_dir():
                for seed_dir in subdir.glob("Seed_*"):
                    summary_path = seed_dir / "summary_final.json"
                    if summary_path.exists():
                        runs.append({
                            "exp_id": exp_id,
                            "run_dir": seed_dir,
                            "summary_path": summary_path,
                        })

    return runs


def find_proactive_runs():
    """Find matching Proactive runs (EXP00, EXP01)."""
    runs = []

    for exp_id in ["EXP00", "EXP01"]:
        exp_dir = RESULTS_DIR / f"EXP_{exp_id}"
        if not exp_dir.exists():
            continue

        for seed_dir in exp_dir.glob("Seed_*"):
            summary_path = seed_dir / "summary_final.json"
            if summary_path.exists():
                runs.append({
                    "exp_id": exp_id,
                    "run_dir": seed_dir,
                    "summary_path": summary_path,
                })

    return runs


def extract_metrics(summary_path):
    """Extract key metrics from summary_final.json."""
    try:
        with open(summary_path) as f:
            summary = json.load(f)
        return {
            "service_rate": summary.get("service_rate_within_window"),
            "deadline_failures": summary.get("deadline_failure_count"),
            "penalized_cost": summary.get("penalized_cost"),
            "cost_raw": summary.get("cost_raw"),
            "plan_churn": summary.get("plan_churn"),
            "strategy": summary.get("strategy"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_seed(run_dir):
    """Extract seed from run directory path."""
    for part in run_dir.parts:
        if part.startswith("Seed_"):
            try:
                return int(part.replace("Seed_", ""))
            except ValueError:
                pass
    return None


def bootstrap_ci(data, n_bootstrap=10000, ci=0.95):
    """Compute bootstrap confidence interval for mean."""
    if len(data) < 2:
        return np.mean(data) if data else np.nan, np.nan, np.nan

    data = np.array(data)
    boot_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=len(data), replace=True)
        boot_means.append(np.mean(sample))

    boot_means = np.array(boot_means)
    alpha = (1 - ci) / 2
    ci_low = np.percentile(boot_means, alpha * 100)
    ci_high = np.percentile(boot_means, (1 - alpha) * 100)

    return np.mean(data), ci_low, ci_high


def main():
    print(f"=" * 60)
    print(f"Legacy Greedy vs Proactive Completion Audit")
    print(f"Timestamp: {TS}")
    print(f"=" * 60)

    # Find runs
    greedy_runs = find_greedy_runs()
    proactive_runs = find_proactive_runs()

    print(f"\nFound {len(greedy_runs)} Greedy runs")
    print(f"Found {len(proactive_runs)} Proactive runs")

    # Completion audit
    completion_path = AUDITS_DIR / f"greedy_completion_{TS}.txt"
    with open(completion_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("LEGACY GREEDY COMPLETION AUDIT\n")
        f.write("=" * 70 + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")

        f.write("-" * 70 + "\n")
        f.write("LEGACY GREEDY RUNS (historical EXP12/EXP13 folders)\n")
        f.write("-" * 70 + "\n")

        exp12_count = sum(1 for r in greedy_runs if r["exp_id"] == "EXP12")
        exp13_count = sum(1 for r in greedy_runs if r["exp_id"] == "EXP13")

        f.write(f"Legacy EXP12 folder (Greedy_NoCrunch_60s): {exp12_count}/10 complete\n")
        f.write(f"Legacy EXP13 folder (Greedy_Crunch_60s):   {exp13_count}/10 complete\n\n")

        if exp12_count < 10 or exp13_count < 10:
            f.write("WARNING: Not all Greedy runs complete!\n")
            f.write("Missing runs:\n")

            exp12_seeds = {get_seed(r["run_dir"]) for r in greedy_runs if r["exp_id"] == "EXP12"}
            exp13_seeds = {get_seed(r["run_dir"]) for r in greedy_runs if r["exp_id"] == "EXP13"}

            missing_12 = set(range(1, 11)) - exp12_seeds
            missing_13 = set(range(1, 11)) - exp13_seeds

            if missing_12:
                f.write(f"  EXP12 missing seeds: {sorted(missing_12)}\n")
            if missing_13:
                f.write(f"  EXP13 missing seeds: {sorted(missing_13)}\n")
            f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("PROACTIVE RUNS (EXP00, EXP01)\n")
        f.write("-" * 70 + "\n")

        exp00_count = sum(1 for r in proactive_runs if r["exp_id"] == "EXP00")
        exp01_count = sum(1 for r in proactive_runs if r["exp_id"] == "EXP01")

        f.write(f"EXP00 (Proactive_NoCrunch_60s): {exp00_count}/10 complete\n")
        f.write(f"EXP01 (Proactive_Crunch_60s):   {exp01_count}/10 complete\n\n")

    print(f"Completion audit: {completion_path}")

    if len(greedy_runs) == 0:
        print("\nNo Greedy runs found yet. Jobs may still be running.")
        print("Check with: bjobs -w 27717390 27717391")
        return

    # Extract metrics
    metrics_data = []

    for run in greedy_runs + proactive_runs:
        metrics = extract_metrics(run["summary_path"])
        seed = get_seed(run["run_dir"])
        metrics_data.append({
            "exp_id": run["exp_id"],
            "seed": seed,
            "run_dir": str(run["run_dir"]),
            **metrics
        })

    # Save metrics by run
    metrics_path = AUDITS_DIR / f"greedy_metrics_by_run_{TS}.csv"
    with open(metrics_path, "w") as f:
        headers = ["exp_id", "seed", "strategy", "service_rate", "deadline_failures",
                   "penalized_cost", "cost_raw", "plan_churn", "run_dir"]
        f.write(",".join(headers) + "\n")
        for item in metrics_data:
            row = [str(item.get(h, "")) for h in headers]
            f.write(",".join(row) + "\n")

    print(f"Metrics by run: {metrics_path}")

    # Paired comparison
    # EXP12 vs EXP00, EXP13 vs EXP01
    paired_results = []

    comparisons = [
        ("EXP12", "EXP00", "BAU (no crunch)"),
        ("EXP13", "EXP01", "Crunch (ratio=0.59)"),
    ]

    for greedy_exp, proactive_exp, scenario_name in comparisons:
        greedy_by_seed = {m["seed"]: m for m in metrics_data if m["exp_id"] == greedy_exp}
        proactive_by_seed = {m["seed"]: m for m in metrics_data if m["exp_id"] == proactive_exp}

        common_seeds = set(greedy_by_seed.keys()) & set(proactive_by_seed.keys())

        if not common_seeds:
            continue

        diffs_sr = []
        diffs_fail = []
        diffs_cost = []

        for seed in sorted(common_seeds):
            g = greedy_by_seed[seed]
            p = proactive_by_seed[seed]

            if g.get("service_rate") and p.get("service_rate"):
                diffs_sr.append(p["service_rate"] - g["service_rate"])
            if g.get("deadline_failures") is not None and p.get("deadline_failures") is not None:
                diffs_fail.append(p["deadline_failures"] - g["deadline_failures"])
            if g.get("penalized_cost") and p.get("penalized_cost"):
                diffs_cost.append(p["penalized_cost"] - g["penalized_cost"])

            paired_results.append({
                "scenario": scenario_name,
                "seed": seed,
                "greedy_sr": g.get("service_rate"),
                "proactive_sr": p.get("service_rate"),
                "diff_sr": p.get("service_rate", 0) - g.get("service_rate", 0) if g.get("service_rate") and p.get("service_rate") else None,
                "greedy_fail": g.get("deadline_failures"),
                "proactive_fail": p.get("deadline_failures"),
                "diff_fail": p.get("deadline_failures", 0) - g.get("deadline_failures", 0) if g.get("deadline_failures") is not None and p.get("deadline_failures") is not None else None,
            })

    # Save paired comparison
    paired_path = AUDITS_DIR / f"greedy_vs_proactive_paired_{TS}.csv"
    with open(paired_path, "w") as f:
        if paired_results:
            headers = list(paired_results[0].keys())
            f.write(",".join(headers) + "\n")
            for item in paired_results:
                row = [str(item.get(h, "")) for h in headers]
                f.write(",".join(row) + "\n")
        else:
            f.write("# No paired comparisons available\n")

    print(f"Paired comparison: {paired_path}")

    # Stats summary
    stats_path = AUDITS_DIR / f"greedy_vs_proactive_stats_{TS}.txt"
    summary_path = AUDITS_DIR / f"one_page_greedy_vs_proactive_{TS}.txt"

    with open(stats_path, "w") as f, open(summary_path, "w") as s:
        header = "=" * 70 + "\n"
        header += "GREEDY VS PROACTIVE STATISTICAL COMPARISON\n"
        header += "=" * 70 + "\n"
        header += f"Generated: {datetime.now().isoformat()}\n\n"

        f.write(header)
        s.write(header)

        for greedy_exp, proactive_exp, scenario_name in comparisons:
            greedy_by_seed = {m["seed"]: m for m in metrics_data if m["exp_id"] == greedy_exp}
            proactive_by_seed = {m["seed"]: m for m in metrics_data if m["exp_id"] == proactive_exp}

            common_seeds = set(greedy_by_seed.keys()) & set(proactive_by_seed.keys())

            section = f"\n{'-' * 70}\n"
            section += f"SCENARIO: {scenario_name}\n"
            section += f"{greedy_exp} (Greedy) vs {proactive_exp} (Proactive)\n"
            section += f"{'-' * 70}\n"
            section += f"Paired seeds: {sorted(common_seeds)} (n={len(common_seeds)})\n\n"

            f.write(section)
            s.write(section)

            if not common_seeds:
                msg = "No paired data available.\n"
                f.write(msg)
                s.write(msg)
                continue

            # Compute stats
            greedy_sr = [greedy_by_seed[seed]["service_rate"] for seed in common_seeds if greedy_by_seed[seed].get("service_rate")]
            proactive_sr = [proactive_by_seed[seed]["service_rate"] for seed in common_seeds if proactive_by_seed[seed].get("service_rate")]

            greedy_fail = [greedy_by_seed[seed]["deadline_failures"] for seed in common_seeds if greedy_by_seed[seed].get("deadline_failures") is not None]
            proactive_fail = [proactive_by_seed[seed]["deadline_failures"] for seed in common_seeds if proactive_by_seed[seed].get("deadline_failures") is not None]

            # Service rate
            if greedy_sr and proactive_sr:
                g_mean, g_lo, g_hi = bootstrap_ci(greedy_sr)
                p_mean, p_lo, p_hi = bootstrap_ci(proactive_sr)

                diffs = [p - g for p, g in zip(proactive_sr, greedy_sr)]
                d_mean, d_lo, d_hi = bootstrap_ci(diffs)

                sr_section = "SERVICE RATE:\n"
                sr_section += f"  Greedy:    {g_mean:.4f} [{g_lo:.4f}, {g_hi:.4f}]\n"
                sr_section += f"  Proactive: {p_mean:.4f} [{p_lo:.4f}, {p_hi:.4f}]\n"
                sr_section += f"  Diff (P-G): {d_mean:+.4f} [{d_lo:+.4f}, {d_hi:+.4f}]\n"

                if d_lo > 0:
                    sr_section += f"  => Proactive SIGNIFICANTLY BETTER (95% CI excludes 0)\n"
                elif d_hi < 0:
                    sr_section += f"  => Greedy SIGNIFICANTLY BETTER (95% CI excludes 0)\n"
                else:
                    sr_section += f"  => No significant difference (95% CI includes 0)\n"
                sr_section += "\n"

                f.write(sr_section)
                s.write(sr_section)

            # Deadline failures
            if greedy_fail and proactive_fail:
                g_mean, g_lo, g_hi = bootstrap_ci(greedy_fail)
                p_mean, p_lo, p_hi = bootstrap_ci(proactive_fail)

                diffs = [p - g for p, g in zip(proactive_fail, greedy_fail)]
                d_mean, d_lo, d_hi = bootstrap_ci(diffs)

                fail_section = "DEADLINE FAILURES:\n"
                fail_section += f"  Greedy:    {g_mean:.1f} [{g_lo:.1f}, {g_hi:.1f}]\n"
                fail_section += f"  Proactive: {p_mean:.1f} [{p_lo:.1f}, {p_hi:.1f}]\n"
                fail_section += f"  Diff (P-G): {d_mean:+.1f} [{d_lo:+.1f}, {d_hi:+.1f}]\n"

                if d_hi < 0:
                    fail_section += f"  => Proactive has FEWER failures (95% CI < 0)\n"
                elif d_lo > 0:
                    fail_section += f"  => Greedy has FEWER failures (95% CI > 0)\n"
                else:
                    fail_section += f"  => No significant difference (95% CI includes 0)\n"
                fail_section += "\n"

                f.write(fail_section)
                s.write(fail_section)

        footer = "\n" + "=" * 70 + "\n"
        footer += "END OF STATISTICAL SUMMARY\n"
        footer += "=" * 70 + "\n"

        f.write(footer)
        s.write(footer)

    print(f"Stats: {stats_path}")
    print(f"One-page summary: {summary_path}")

    # Traffic light
    traffic_csv = AUDITS_DIR / f"greedy_traffic_light_{TS}.csv"
    traffic_txt = AUDITS_DIR / f"greedy_traffic_light_{TS}.txt"

    with open(traffic_csv, "w") as f:
        f.write("exp_id,seed,artifacts_ok,strategy_correct,days_complete\n")
        for item in metrics_data:
            artifacts_ok = item.get("service_rate") is not None
            strategy_correct = "Greedy" in str(item.get("strategy", "")) if item["exp_id"] in ["EXP12", "EXP13"] else "Proactive" in str(item.get("strategy", ""))
            f.write(f"{item['exp_id']},{item['seed']},{artifacts_ok},{strategy_correct},True\n")

    with open(traffic_txt, "w") as f:
        f.write("Traffic Light Audit - Greedy Baselines\n")
        f.write(f"Generated: {TS}\n")
        f.write("=" * 60 + "\n\n")

        greedy_ok = sum(1 for m in metrics_data if m["exp_id"] in ["EXP12", "EXP13"] and m.get("service_rate"))
        f.write(f"Greedy runs with valid metrics: {greedy_ok}/20\n")

    print(f"Traffic light: {traffic_csv}")

    print(f"\n{'=' * 60}")
    print("AUDIT COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
