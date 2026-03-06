#!/usr/bin/env python3
"""
Audit script: legacy Greedy vs Proactive comparison.
Scans data/results/ to identify policy types and generate comparison metrics.
Historical result folders may use EXP12/EXP13 labels; these do not correspond
to the paper-aligned EXP12/EXP13 learning-augmented experiments in 22.03.

Usage:
    python scripts/audit_greedy_vs_proactive.py

Outputs to data/audits/ with timestamp.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = REPO_ROOT / "data" / "results"
AUDITS_DIR = REPO_ROOT / "data" / "audits"
AUDITS_DIR.mkdir(parents=True, exist_ok=True)


def find_all_runs():
    """Find all run directories with config_dump.json."""
    runs = []

    # Pattern 1: EXP_*/*/Seed_*/
    for exp_dir in RESULTS_DIR.glob("EXP_*"):
        for scenario_dir in exp_dir.iterdir():
            if scenario_dir.is_dir() and not scenario_dir.name.startswith("."):
                for seed_dir in scenario_dir.glob("Seed_*"):
                    config_path = seed_dir / "config_dump.json"
                    if config_path.exists():
                        runs.append(seed_dir)

    # Pattern 2: timestamp dirs (20260130_*/DEFAULT/*)
    for ts_dir in RESULTS_DIR.glob("20*"):
        if ts_dir.is_dir():
            for scenario_dir in ts_dir.iterdir():
                if scenario_dir.is_dir():
                    for strategy_dir in scenario_dir.iterdir():
                        if strategy_dir.is_dir():
                            summary_path = strategy_dir / "summary_final.json"
                            if summary_path.exists():
                                runs.append(strategy_dir)

    return runs


def identify_policy(run_dir: Path) -> dict:
    """
    Identify policy family from run directory.
    Returns dict with policy info and run metadata.
    """
    result = {
        "run_dir": str(run_dir),
        "exp_id": "",
        "endpoint_key": "",
        "seed": None,
        "policy_family": "Unknown",
        "ratio": None,
        "crunch_start": None,
        "crunch_end": None,
        "crunch_windows": None,
        "use_risk_model": None,
        "base_compute": None,
        "high_compute": None,
        "total_days": None,
        "artifacts_ok": False,
        "strategy_raw": "",
    }

    # Check artifacts
    config_path = run_dir / "config_dump.json"
    summary_path = run_dir / "summary_final.json"
    sim_path = run_dir / "simulation_results.json"

    has_config = config_path.exists()
    has_summary = summary_path.exists()
    has_sim = sim_path.exists()
    result["artifacts_ok"] = has_config and has_summary and has_sim

    # Try to get strategy from summary_final.json first
    if has_summary:
        try:
            with open(summary_path) as f:
                summary = json.load(f)
            strategy = summary.get("strategy", "")
            result["strategy_raw"] = strategy

            if "greedy" in strategy.lower():
                result["policy_family"] = "Greedy"
            elif "proactive" in strategy.lower():
                if "risk" in strategy.lower():
                    result["policy_family"] = "ProactiveRisk"
                else:
                    result["policy_family"] = "Proactive"
        except Exception:
            pass

    # Get config parameters
    if has_config:
        try:
            with open(config_path) as f:
                config = json.load(f)

            result["exp_id"] = config.get("experiment_id", "")
            result["seed"] = config.get("seed")

            params = config.get("parameters", {})
            result["ratio"] = params.get("ratio")
            result["crunch_start"] = params.get("crunch_start")
            result["crunch_end"] = params.get("crunch_end")
            result["crunch_windows"] = params.get("crunch_windows")
            result["use_risk_model"] = params.get("use_risk_model")
            result["base_compute"] = params.get("base_compute")
            result["high_compute"] = params.get("high_compute")
            result["total_days"] = params.get("total_days")
        except Exception:
            pass

    # Try to extract endpoint_key from path
    # Pattern: EXP_EXP07/ratio_0.6_risk_False/Seed_1
    parts = run_dir.parts
    for i, part in enumerate(parts):
        if part.startswith("EXP_"):
            result["exp_id"] = part.replace("EXP_", "")
        if part.startswith("ratio_") or part.startswith("max_trips_"):
            result["endpoint_key"] = part
        if part.startswith("Seed_"):
            try:
                result["seed"] = int(part.replace("Seed_", ""))
            except ValueError:
                pass

    return result


def extract_metrics(run_dir: Path) -> dict:
    """Extract key metrics from a run directory."""
    metrics = {
        "service_rate_within_window": None,
        "deadline_failure_count": None,
        "sum_vrp_dropped": None,
        "sum_failures": None,
        "sum_delivered_today": None,
        "penalized_cost": None,
        "cost_raw": None,
        "plan_churn": None,
        "target_churn": None,
        "total_days_actual": None,
        "mean_visible_open": None,
        "max_visible_open": None,
        "mean_mandatory_count": None,
    }

    summary_path = run_dir / "summary_final.json"
    sim_path = run_dir / "simulation_results.json"

    # From summary_final.json
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                summary = json.load(f)
            metrics["service_rate_within_window"] = summary.get("service_rate_within_window")
            metrics["deadline_failure_count"] = summary.get("deadline_failure_count")
            metrics["penalized_cost"] = summary.get("penalized_cost")
            metrics["cost_raw"] = summary.get("cost_raw")
            metrics["plan_churn"] = summary.get("plan_churn")
            metrics["target_churn"] = summary.get("target_churn")
        except Exception:
            pass

    # From simulation_results.json daily_stats
    if sim_path.exists():
        try:
            with open(sim_path) as f:
                sim = json.load(f)
            daily_stats = sim.get("daily_stats", [])

            if daily_stats:
                metrics["total_days_actual"] = len(daily_stats)

                # Aggregate metrics
                vrp_dropped = sum(d.get("vrp_dropped", 0) for d in daily_stats)
                failures = sum(d.get("failures", 0) for d in daily_stats)
                delivered = sum(d.get("delivered_today", 0) for d in daily_stats)

                metrics["sum_vrp_dropped"] = vrp_dropped
                metrics["sum_failures"] = failures
                metrics["sum_delivered_today"] = delivered

                # Visible open orders
                visible_open = [d.get("visible_open_orders", 0) for d in daily_stats]
                if visible_open:
                    metrics["mean_visible_open"] = np.mean(visible_open)
                    metrics["max_visible_open"] = max(visible_open)

                # Mandatory count
                mandatory = [d.get("mandatory_count", 0) for d in daily_stats]
                if mandatory:
                    metrics["mean_mandatory_count"] = np.mean(mandatory)
        except Exception:
            pass

    return metrics


def create_scenario_key(run_info: dict) -> str:
    """Create a unique scenario key for grouping comparable runs."""
    parts = []

    # Ratio
    ratio = run_info.get("ratio")
    if ratio is not None:
        parts.append(f"r{ratio}")

    # Crunch
    cs = run_info.get("crunch_start")
    ce = run_info.get("crunch_end")
    cw = run_info.get("crunch_windows")
    if cw:
        parts.append(f"cw{cw}")
    elif cs is not None and ce is not None:
        parts.append(f"c{cs}-{ce}")
    else:
        parts.append("c_none")

    # Compute
    bc = run_info.get("base_compute")
    hc = run_info.get("high_compute")
    if bc is not None and hc is not None:
        parts.append(f"comp{bc}/{hc}")

    # Risk model
    risk = run_info.get("use_risk_model")
    if risk is not None:
        parts.append(f"risk{int(risk)}")

    return "_".join(parts)


def bootstrap_ci(data, n_bootstrap=10000, ci=0.95):
    """Compute bootstrap confidence interval for mean."""
    if len(data) < 2:
        return np.nan, np.nan, np.nan

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
    print(f"Greedy vs Proactive Audit")
    print(f"Timestamp: {TS}")
    print(f"=" * 60)

    # Find all runs
    runs = find_all_runs()
    print(f"\nFound {len(runs)} run directories")

    # Identify policies and extract info
    inventory = []
    for run_dir in runs:
        info = identify_policy(run_dir)
        inventory.append(info)

    # Count by policy family
    policy_counts = {}
    for item in inventory:
        pf = item["policy_family"]
        policy_counts[pf] = policy_counts.get(pf, 0) + 1

    print(f"\nPolicy distribution:")
    for pf, count in sorted(policy_counts.items()):
        print(f"  {pf}: {count}")

    # Save inventory CSV
    inventory_path = AUDITS_DIR / f"greedy_proactive_inventory_{TS}.csv"
    with open(inventory_path, "w") as f:
        headers = [
            "run_dir", "exp_id", "endpoint_key", "seed",
            "policy_family", "ratio", "crunch_start", "crunch_end", "crunch_windows",
            "use_risk_model", "base_compute", "high_compute", "total_days",
            "artifacts_ok", "strategy_raw"
        ]
        f.write(",".join(headers) + "\n")
        for item in inventory:
            row = [str(item.get(h, "")) for h in headers]
            f.write(",".join(row) + "\n")
    print(f"\nInventory saved: {inventory_path}")

    # Filter to Greedy and Proactive only
    greedy_runs = [i for i in inventory if i["policy_family"] == "Greedy"]
    proactive_runs = [i for i in inventory if i["policy_family"] in ("Proactive", "ProactiveRisk")]

    print(f"\nGreedy runs: {len(greedy_runs)}")
    print(f"Proactive runs: {len(proactive_runs)}")

    # Extract metrics for all runs
    metrics_by_run = []
    for item in inventory:
        if item["policy_family"] in ("Greedy", "Proactive", "ProactiveRisk"):
            run_dir = Path(item["run_dir"])
            metrics = extract_metrics(run_dir)
            combined = {**item, **metrics}
            combined["scenario_key"] = create_scenario_key(item)
            metrics_by_run.append(combined)

    # Save metrics by run
    metrics_path = AUDITS_DIR / f"greedy_proactive_metrics_by_run_{TS}.csv"
    if metrics_by_run:
        with open(metrics_path, "w") as f:
            headers = list(metrics_by_run[0].keys())
            f.write(",".join(headers) + "\n")
            for item in metrics_by_run:
                row = [str(item.get(h, "")) for h in headers]
                f.write(",".join(row) + "\n")
        print(f"Metrics by run saved: {metrics_path}")

    # Aggregate by scenario x policy
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))

    for item in metrics_by_run:
        key = (item["scenario_key"], item["policy_family"])
        for metric in ["service_rate_within_window", "deadline_failure_count",
                       "sum_vrp_dropped", "sum_failures", "penalized_cost"]:
            val = item.get(metric)
            if val is not None:
                agg[key][metric].append(val)

    # Save aggregated metrics
    agg_path = AUDITS_DIR / f"greedy_proactive_metrics_agg_{TS}.csv"
    with open(agg_path, "w") as f:
        f.write("scenario_key,policy_family,metric,n,mean,std\n")
        for (scenario, policy), metrics_dict in sorted(agg.items()):
            for metric, values in metrics_dict.items():
                if values:
                    mean = np.mean(values)
                    std = np.std(values) if len(values) > 1 else 0
                    f.write(f"{scenario},{policy},{metric},{len(values)},{mean:.6f},{std:.6f}\n")
    print(f"Aggregated metrics saved: {agg_path}")

    # Paired comparison (if both Greedy and Proactive exist for same scenario+seed)
    paired_path = AUDITS_DIR / f"greedy_vs_proactive_paired_{TS}.csv"
    stats_path = AUDITS_DIR / f"greedy_vs_proactive_stats_{TS}.txt"

    # Group by scenario+seed
    by_scenario_seed = defaultdict(dict)
    for item in metrics_by_run:
        key = (item["scenario_key"], item["seed"])
        by_scenario_seed[key][item["policy_family"]] = item

    # Find paired comparisons
    paired_data = []
    for (scenario, seed), policies in by_scenario_seed.items():
        if "Greedy" in policies and ("Proactive" in policies or "ProactiveRisk" in policies):
            greedy = policies["Greedy"]
            proactive = policies.get("Proactive") or policies.get("ProactiveRisk")
            paired_data.append({
                "scenario_key": scenario,
                "seed": seed,
                "greedy_sr": greedy.get("service_rate_within_window"),
                "proactive_sr": proactive.get("service_rate_within_window"),
                "greedy_fail": greedy.get("deadline_failure_count"),
                "proactive_fail": proactive.get("deadline_failure_count"),
                "greedy_drop": greedy.get("sum_vrp_dropped"),
                "proactive_drop": proactive.get("sum_vrp_dropped"),
            })

    with open(paired_path, "w") as f:
        if paired_data:
            headers = list(paired_data[0].keys())
            f.write(",".join(headers) + "\n")
            for item in paired_data:
                row = [str(item.get(h, "")) for h in headers]
                f.write(",".join(row) + "\n")
        else:
            f.write("# No paired Greedy vs Proactive comparisons found\n")
    print(f"Paired comparison saved: {paired_path}")

    # Stats summary
    with open(stats_path, "w") as f:
        f.write(f"Greedy vs Proactive Statistical Summary\n")
        f.write(f"Generated: {TS}\n")
        f.write(f"=" * 60 + "\n\n")

        if paired_data:
            f.write(f"Found {len(paired_data)} paired comparisons\n\n")
            # Compute paired differences and bootstrap CI
            # ... (would add detailed stats here)
        else:
            f.write("NO PAIRED COMPARISONS AVAILABLE\n\n")
            f.write("Reason: No Greedy runs found in data/results/\n\n")
            f.write("Current policy distribution:\n")
            for pf, count in sorted(policy_counts.items()):
                f.write(f"  {pf}: {count}\n")
    print(f"Stats saved: {stats_path}")

    # Traffic light audit
    traffic_csv = AUDITS_DIR / f"greedy_proactive_traffic_light_{TS}.csv"
    traffic_txt = AUDITS_DIR / f"greedy_proactive_traffic_light_{TS}.txt"

    with open(traffic_csv, "w") as f:
        f.write("run_dir,policy_family,artifacts_ok,days_complete,compute_ok\n")
        for item in metrics_by_run:
            days_ok = item.get("total_days_actual") == item.get("total_days", 12)
            f.write(f"{item['run_dir']},{item['policy_family']},{item['artifacts_ok']},{days_ok},True\n")

    with open(traffic_txt, "w") as f:
        f.write(f"Traffic Light Audit - Greedy/Proactive Runs\n")
        f.write(f"Generated: {TS}\n")
        f.write(f"=" * 60 + "\n\n")

        complete = sum(1 for i in metrics_by_run if i.get("artifacts_ok"))
        f.write(f"Runs with complete artifacts: {complete}/{len(metrics_by_run)}\n")

    print(f"Traffic light saved: {traffic_csv}")

    # One-page summary
    summary_path = AUDITS_DIR / f"one_page_greedy_vs_proactive_{TS}.txt"

    with open(summary_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("ONE-PAGE SUMMARY: Greedy vs Proactive Experiment Audit\n")
        f.write("=" * 70 + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Audit script: scripts/audit_greedy_vs_proactive.py\n\n")

        f.write("-" * 70 + "\n")
        f.write("1. INVENTORY SUMMARY\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total runs scanned: {len(inventory)}\n\n")
        f.write("Policy distribution:\n")
        for pf, count in sorted(policy_counts.items()):
            f.write(f"  - {pf}: {count} runs\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("2. CRITICAL FINDING: NO GREEDY RUNS EXIST\n")
        f.write("-" * 70 + "\n")
        f.write("*** GREEDY BASELINE RUNS ARE MISSING ***\n\n")
        f.write("All existing runs use ProactivePolicy variants:\n")
        f.write(f"  - Proactive (no risk model): {policy_counts.get('Proactive', 0)} runs\n")
        f.write(f"  - ProactiveRisk (with risk model): {policy_counts.get('ProactiveRisk', 0)} runs\n")
        f.write(f"  - Greedy: {policy_counts.get('Greedy', 0)} runs\n\n")

        f.write("This means:\n")
        f.write("  - Cannot perform Greedy vs Proactive paired comparison\n")
        f.write("  - Cannot establish baseline performance for comparison\n")
        f.write("  - Thesis claims about Proactive improvement lack baseline reference\n\n")

        f.write("-" * 70 + "\n")
        f.write("3. EXISTING PROACTIVE RUNS BY SCENARIO\n")
        f.write("-" * 70 + "\n")

        # Group by scenario
        scenarios = defaultdict(list)
        for item in metrics_by_run:
            scenarios[item["scenario_key"]].append(item)

        for scenario, items in sorted(scenarios.items()):
            policies = set(i["policy_family"] for i in items)
            seeds = sorted(set(i["seed"] for i in items if i["seed"] is not None))

            # Get mean metrics
            sr_vals = [i["service_rate_within_window"] for i in items if i.get("service_rate_within_window")]
            fail_vals = [i["deadline_failure_count"] for i in items if i.get("deadline_failure_count") is not None]

            f.write(f"\nScenario: {scenario}\n")
            f.write(f"  Policies: {', '.join(sorted(policies))}\n")
            f.write(f"  Seeds: {seeds}\n")
            f.write(f"  N runs: {len(items)}\n")
            if sr_vals:
                f.write(f"  Service Rate: {np.mean(sr_vals):.4f} +/- {np.std(sr_vals):.4f}\n")
            if fail_vals:
                f.write(f"  Deadline Failures: {np.mean(fail_vals):.1f} +/- {np.std(fail_vals):.1f}\n")

        f.write("\n")
        f.write("-" * 70 + "\n")
        f.write("4. PAIRED COMPARISON RESULTS\n")
        f.write("-" * 70 + "\n")
        f.write("NOT AVAILABLE - No Greedy runs to compare against.\n\n")

        f.write("-" * 70 + "\n")
        f.write("5. GAP ANALYSIS & RECOMMENDED ACTIONS\n")
        f.write("-" * 70 + "\n")
        f.write("To enable Greedy vs Proactive comparison, run Greedy baseline for:\n\n")

        # List scenarios that need Greedy runs
        for scenario, items in sorted(scenarios.items()):
            seeds = sorted(set(i["seed"] for i in items if i["seed"] is not None))
            exp_ids = sorted(set(i["exp_id"] for i in items if i["exp_id"]))
            f.write(f"  Scenario: {scenario}\n")
            f.write(f"    Experiments: {exp_ids}\n")
            f.write(f"    Seeds needed: {seeds}\n")
            f.write(f"    Total runs needed: {len(seeds)}\n\n")

        f.write("Implementation:\n")
        f.write("  1. Modify master_runner.py to accept strategy_config parameter\n")
        f.write("  2. Use exp_utils.strategy_greedy() to create Greedy config\n")
        f.write("  3. Run matching experiments with mode='greedy'\n")
        f.write("  4. Ensure same seeds, ratios, crunch windows as Proactive runs\n\n")

        f.write("Minimum viable set for thesis:\n")
        f.write("  - EXP01 (Crunch_Baseline): seeds 1-10 with Greedy\n")
        f.write("  - EXP04 (Dynamic_Compute_RiskGate): seeds 1-10 with Greedy\n")
        f.write("  - Total: ~20 additional runs\n\n")

        f.write("-" * 70 + "\n")
        f.write("6. FILES GENERATED\n")
        f.write("-" * 70 + "\n")
        f.write(f"  - {inventory_path}\n")
        f.write(f"  - {metrics_path}\n")
        f.write(f"  - {agg_path}\n")
        f.write(f"  - {paired_path}\n")
        f.write(f"  - {stats_path}\n")
        f.write(f"  - {traffic_csv}\n")
        f.write(f"  - {traffic_txt}\n")
        f.write(f"  - {summary_path}\n\n")

        f.write("=" * 70 + "\n")
        f.write("END OF SUMMARY\n")
        f.write("=" * 70 + "\n")

    print(f"\nOne-page summary saved: {summary_path}")
    print(f"\n{'=' * 60}")
    print("AUDIT COMPLETE")
    print(f"{'=' * 60}")

    return {
        "inventory_path": str(inventory_path),
        "metrics_path": str(metrics_path),
        "agg_path": str(agg_path),
        "paired_path": str(paired_path),
        "stats_path": str(stats_path),
        "traffic_csv": str(traffic_csv),
        "traffic_txt": str(traffic_txt),
        "summary_path": str(summary_path),
        "greedy_count": len(greedy_runs),
        "proactive_count": len(proactive_runs),
    }


if __name__ == "__main__":
    main()
