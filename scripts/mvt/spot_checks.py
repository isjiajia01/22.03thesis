#!/usr/bin/env python3
"""Targeted trust spot-checks: A4_REAL, arrival-cumul source, EXP04 Seed_1 large-scale."""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Row:
    check_id: str
    status: str
    detail: str
    evidence_path: str
    counterexample: str


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_mvt_index() -> Path:
    files = sorted(glob.glob(str(ROOT / "data" / "audits" / "mvt_index_*.csv")))
    if not files:
        raise FileNotFoundError("No mvt_index file found.")
    return Path(files[-1])


def find_case_row(index_df: pd.DataFrame, case_name: str) -> Optional[pd.Series]:
    m = index_df[index_df["case_name"] == case_name]
    if m.empty:
        return None
    return m.iloc[0]


def push(rows: List[Row], check_id: str, ok: bool, detail: str, evidence: str, cex: str = "") -> None:
    rows.append(Row(check_id, "PASS" if ok else "FAIL", detail, evidence, cex))


def check_a4_real(index_df: pd.DataFrame, rows: List[Row]) -> None:
    rec = find_case_row(index_df, "A4_REAL_EXP04_Seed1")
    if rec is None:
        push(rows, "A4_REAL_present", False, "A4_REAL case missing from MVT index", str(latest_mvt_index().relative_to(ROOT)), "case_not_found")
        return

    cfg_path = ROOT / rec["config_path"]
    sim_path = ROOT / rec["simulation_results_path"]
    sum_path = ROOT / rec["summary_path"]
    cfg = read_json(cfg_path)
    sim = read_json(sim_path)
    summary = read_json(sum_path)

    sc = cfg.get("sim_config", {})
    thr_on = float(sc.get("risk_threshold_on", -1))
    thr_off = float(sc.get("risk_threshold_off", -1))
    model_path = str(sc.get("risk_model_path", ""))

    ok_thr = abs(thr_on - 0.826) < 1e-9 and abs(thr_off - 0.496) < 1e-9
    push(rows, "A4_REAL_thresholds", ok_thr, f"threshold_on={thr_on}, threshold_off={thr_off}", str(cfg_path.relative_to(ROOT)), "wrong_real_thresholds" if not ok_thr else "")

    model_exists = (ROOT / model_path).exists() if model_path else False
    push(rows, "A4_REAL_model_exists", model_exists, f"risk_model_path={model_path}", str(cfg_path.relative_to(ROOT)), "model_path_missing" if not model_exists else "")

    daily = sim.get("daily_stats", [])
    risk_days = [i for i, d in enumerate(daily) if int(d.get("risk_mode_on", 0)) == 1]
    ok_trigger = len(risk_days) > 0
    push(rows, "A4_REAL_triggered", ok_trigger, f"risk_mode_on_days={risk_days}", str(sim_path.relative_to(ROOT)), "risk_mode_on_never_1" if not ok_trigger else "")

    computes = sorted(set(int(d.get("compute_limit_seconds", 0)) for d in daily))
    ok_compute = 300 in computes
    push(rows, "A4_REAL_high_compute_used", ok_compute, f"unique_compute={computes}", str(sim_path.relative_to(ROOT)), "high_compute_not_used" if not ok_compute else "")

    # Basic summary consistency with daily
    fail_sum = int(sum(int(d.get("failures", 0)) for d in daily))
    ok_consistency = int(summary.get("deadline_failure_count", -1)) == fail_sum
    push(rows, "A4_REAL_summary_daily_consistency", ok_consistency, f"summary_fail={summary.get('deadline_failure_count')}, daily_sum_fail={fail_sum}", str(sum_path.relative_to(ROOT)), "summary_daily_failure_mismatch" if not ok_consistency else "")


def check_arrival_spot(index_df: pd.DataFrame, rows: List[Row]) -> None:
    rec = find_case_row(index_df, "A1_Tiny_Feasible")
    if rec is None:
        push(rows, "ARRIVAL_case_present", False, "A1 case missing", str(latest_mvt_index().relative_to(ROOT)), "a1_not_found")
        return
    sim_path = ROOT / rec["simulation_results_path"]
    sim = read_json(sim_path)

    traces = sim.get("vrp_audit_traces", [])
    target = None
    for d in traces:
        for r in d.get("routes", []) or []:
            for st in r.get("stop_details", []) or []:
                target = {"day_idx": d.get("day_idx"), "vehicle_id": r.get("vehicle_id"), **st}
                break
            if target:
                break
        if target:
            break

    if target is None:
        push(rows, "ARRIVAL_stop_detail_exists", False, "No stop_details found for arrival spot-check", str(sim_path.relative_to(ROOT)), "no_stop_details")
        return

    source = target.get("arrival_source")
    ok_source = source == "ortools_time_dimension_cumul"
    push(rows, "ARRIVAL_source_flag", ok_source, f"arrival_source={source}", str(sim_path.relative_to(ROOT)), "arrival_source_not_cumul" if not ok_source else "")

    arr = target.get("arrival_min")
    cumul = target.get("arrival_cumul_min")
    ok_equal = arr == cumul
    push(
        rows,
        "ARRIVAL_value_match_cumul",
        ok_equal,
        f"day={target.get('day_idx')}, vehicle={target.get('vehicle_id')}, order={target.get('order_id')}, arrival_min={arr}, arrival_cumul_min={cumul}",
        str(sim_path.relative_to(ROOT)),
        "arrival_and_cumul_value_mismatch" if not ok_equal else "",
    )


def check_exp04_seed1_large(rows: List[Row]) -> None:
    run_dir = ROOT / "data" / "results" / "EXP_EXP04" / "Seed_1"
    cfg_path = run_dir / "config_dump.json"
    sim_path = run_dir / "simulation_results.json"
    sum_path = run_dir / "summary_final.json"

    required = [cfg_path, sim_path, sum_path]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    push(rows, "EXP04_seed1_artifact_triple", len(missing) == 0, f"missing={missing}" if missing else "all artifacts present", str(run_dir.relative_to(ROOT)), "missing_artifacts" if missing else "")
    if missing:
        return

    cfg = read_json(cfg_path)
    sim = read_json(sim_path)
    summary = read_json(sum_path)
    daily = sim.get("daily_stats", [])

    push(rows, "EXP04_seed1_days", len(daily) == 12, f"days={len(daily)}", str(sim_path.relative_to(ROOT)), "expected_12_days" if len(daily) != 12 else "")

    risk_days = [i for i, d in enumerate(daily) if int(d.get("risk_mode_on", 0)) == 1]
    push(rows, "EXP04_seed1_risk_trigger", len(risk_days) > 0, f"risk_mode_on_days={risk_days}", str(sim_path.relative_to(ROOT)), "risk_never_triggered" if not risk_days else "")

    # compute gate alignment
    bad = []
    for i, d in enumerate(daily):
        base = int(d.get("compute_base_seconds", 60))
        high = int(d.get("compute_high_seconds", 300))
        actual = int(d.get("compute_limit_seconds", base))
        risk = int(d.get("risk_mode_on", 0))
        if risk == 1 and actual != high:
            bad.append(f"day={i} risk=1 compute={actual} high={high}")
        if risk == 0 and actual != base:
            bad.append(f"day={i} risk=0 compute={actual} base={base}")
    push(rows, "EXP04_seed1_compute_gate", len(bad) == 0, "compute gate aligned" if not bad else bad[0], str(sim_path.relative_to(ROOT)), bad[0] if bad else "")

    fail_sum = int(sum(int(d.get("failures", 0)) for d in daily))
    fail_summary = int(summary.get("deadline_failure_count", -1))
    push(rows, "EXP04_seed1_summary_daily_failures", fail_sum == fail_summary, f"summary_fail={fail_summary}, daily_sum_fail={fail_sum}", str(sum_path.relative_to(ROOT)), "summary_vs_daily_failure_mismatch" if fail_sum != fail_summary else "")

    eligible = int(summary.get("eligible_count", -1))
    delivered = int(summary.get("delivered_within_window_count", -1))
    sr = float(summary.get("service_rate_within_window", -1.0))
    sr_calc = delivered / eligible if eligible > 0 else 0.0
    push(rows, "EXP04_seed1_service_rate_consistency", abs(sr - sr_calc) < 1e-12, f"service_rate={sr}, delivered/eligible={sr_calc}", str(sum_path.relative_to(ROOT)), "service_rate_mismatch" if abs(sr - sr_calc) >= 1e-12 else "")

    # config sanity for real thresholds
    params = cfg.get("parameters", {})
    ok_params = (
        bool(params.get("use_risk_model", False))
        and abs(float(params.get("ratio", -1)) - 0.59) < 1e-9
        and int(params.get("base_compute", -1)) == 60
        and int(params.get("high_compute", -1)) == 300
    )
    push(rows, "EXP04_seed1_config_sanity", ok_params, f"params={params}", str(cfg_path.relative_to(ROOT)), "unexpected_config_params" if not ok_params else "")


def main() -> None:
    idx_path = latest_mvt_index()
    idx_df = pd.read_csv(idx_path)
    rows: List[Row] = []

    check_a4_real(idx_df, rows)
    check_arrival_spot(idx_df, rows)
    check_exp04_seed1_large(rows)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    traffic_path = ROOT / "data" / "audits" / f"mvt_spotcheck_traffic_light_{ts}.csv"
    report_path = ROOT / "data" / "audits" / f"mvt_spotcheck_report_{ts}.md"
    cex_path = ROOT / "data" / "audits" / f"mvt_spotcheck_counterexamples_{ts}.txt"

    df = pd.DataFrame([r.__dict__ for r in rows])
    df.to_csv(traffic_path, index=False)

    fails = df[df["status"] == "FAIL"]
    overall = "PASS" if fails.empty else "FAIL"

    md = [
        "# MVT Spot-Check Report",
        "",
        f"- Overall: **{overall}**",
        f"- MVT index: `{idx_path.relative_to(ROOT)}`",
        f"- Traffic light: `{traffic_path.relative_to(ROOT)}`",
        f"- Counterexamples: `{cex_path.relative_to(ROOT)}`",
        f"- Total checks: {len(df)}",
        f"- Failed checks: {len(fails)}",
        "",
        "## Scope",
        "",
        "- A4_REAL: real thresholds + real model + known-trigger case validation.",
        "- Arrival spot-check: confirm exported arrival field is tagged as OR-Tools Time dimension cumul value.",
        "- EXP04 Seed_1 large-scale spot-check: artifact, compute-gate, and summary consistency checks.",
        "",
        "## Results",
        "",
    ]

    for _, r in df.iterrows():
        md.append(f"- `{r['check_id']}`: {r['status']} | {r['detail']} | evidence=`{r['evidence_path']}`")

    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    with cex_path.open("w", encoding="utf-8") as f:
        if fails.empty:
            f.write("NO_FAILURES\n")
        else:
            for _, r in fails.iterrows():
                f.write(
                    f"check_id={r['check_id']}; detail={r['detail']}; counterexample={r['counterexample']}; evidence={r['evidence_path']}\n"
                )

    print(f"Spot-check complete. Report: {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
