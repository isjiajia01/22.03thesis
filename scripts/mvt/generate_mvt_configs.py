#!/usr/bin/env python3
"""Generate minimal verifiable test (MVT) configs and synthetic datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "audits" / "mvt_configs"
DATA_DIR = OUT_DIR / "datasets"


@dataclass
class CaseDef:
    case_name: str
    purpose: str
    expected_days: int
    seeds: List[int]
    scenario_name: str
    strategy_name: str
    sim_config: Dict[str, Any]
    data_file: str
    checks: Dict[str, bool]
    tags: List[str]


def dseq(start: date, days: int) -> List[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def base_depot() -> Dict[str, Any]:
    return {
        "name": "MVT_DEPOT",
        "location": [55.6800, 12.5700],
        "opening_time": 360,
        "closing_time": 1080,
        "picking_open_min": 300,
        "picking_close_min": 1200,
        "gates": 2,
        "picking_capacity": {"colli_per_hour": 200},
        "loading_time_minutes": 8,
        "unloading_time_minutes": 5,
    }


def base_vehicles(count: int = 1, cap_colli: int = 10) -> List[Dict[str, Any]]:
    return [
        {
            "type_name": "MVT_VAN",
            "count": int(count),
            "depot": "MVT_DEPOT",
            "capacity": {
                "colli": int(cap_colli),
                "volume": float(cap_colli * 1.5),
                "weight": float(cap_colli * 300.0),
            },
            "max_duration_hours": 10,
            "max_distance_km": 300,
        }
    ]


def mk_order(
    oid: int,
    feasible_dates: List[str],
    lat: float,
    lon: float,
    tw: List[int],
    colli: int = 1,
    service: int = 8,
    release_date: str | None = None,
) -> Dict[str, Any]:
    rd = release_date or feasible_dates[0]
    return {
        "id": int(oid),
        "original_id": str(oid),
        "feasible_dates": list(feasible_dates),
        "location": [float(lat), float(lon)],
        "demand": {
            "colli": int(colli),
            "volume": float(colli * 1.0),
            "weight": float(colli * 120.0),
        },
        "time_window": [int(tw[0]), int(tw[1])],
        "service_time": int(service),
        "order_date": rd,
        "release_date": rd,
        "is_flexible": len(feasible_dates) > 1,
        "delivery_window_days": len(feasible_dates),
    }


def build_tiny_feasible() -> Dict[str, Any]:
    start = date(2025, 12, 1)
    days = 4
    all_days = dseq(start, days)
    orders = []
    for i in range(8):
        fds = all_days[min(i // 3, 2):]
        orders.append(
            mk_order(
                oid=i,
                feasible_dates=fds,
                lat=55.6805 + 0.003 * (i % 3),
                lon=12.5705 + 0.003 * (i // 3),
                tw=[420, 960],
                colli=1,
                service=8,
                release_date=all_days[0],
            )
        )

    return {
        "metadata": {
            "description": "MVT A1 tiny feasible",
            "depot_name": "MVT_DEPOT",
            "horizon_start": all_days[0],
            "horizon_end": all_days[-1],
            "total_orders_in_file": len(orders),
            "capacity_profile": {str(i): 1.0 for i in range(days)},
        },
        "depot": base_depot(),
        "vehicles": base_vehicles(count=1, cap_colli=10),
        "orders": orders,
    }


def build_tiny_infeasible() -> Dict[str, Any]:
    start = date(2025, 12, 1)
    d0 = start.isoformat()
    orders = [
        mk_order(0, [d0], 55.8200, 12.3500, [360, 382], colli=1, service=25, release_date=d0),
        mk_order(1, [d0], 55.5250, 12.9300, [365, 390], colli=1, service=25, release_date=d0),
        mk_order(2, [d0], 55.8050, 12.3400, [370, 395], colli=1, service=25, release_date=d0),
    ]
    return {
        "metadata": {
            "description": "MVT A2 tiny infeasible",
            "depot_name": "MVT_DEPOT",
            "horizon_start": d0,
            "horizon_end": d0,
            "total_orders_in_file": len(orders),
            "capacity_profile": {"0": 1.0},
        },
        "depot": base_depot(),
        "vehicles": base_vehicles(count=1, cap_colli=10),
        "orders": orders,
    }


def build_deadline_sweep() -> Dict[str, Any]:
    start = date(2025, 12, 1)
    horizon_days = 4
    all_days = dseq(start, horizon_days)
    out_days = dseq(start + timedelta(days=4), 2)
    orders = [
        mk_order(0, [all_days[0], all_days[1]], 55.8450, 12.3200, [360, 380], colli=1, service=30, release_date=all_days[0]),
        mk_order(1, [out_days[0], out_days[1]], 55.6890, 12.5710, [480, 900], colli=1, service=8, release_date=all_days[0]),
        mk_order(2, [all_days[0], all_days[1], all_days[2]], 55.6830, 12.5750, [540, 900], colli=1, service=8, release_date=all_days[0]),
        mk_order(3, [all_days[2], all_days[3]], 55.6840, 12.5690, [500, 910], colli=1, service=8, release_date=all_days[1]),
    ]
    return {
        "metadata": {
            "description": "MVT A3 deadline sweep",
            "depot_name": "MVT_DEPOT",
            "horizon_start": all_days[0],
            "horizon_end": all_days[-1],
            "total_orders_in_file": len(orders),
            "capacity_profile": {str(i): 1.0 for i in range(horizon_days)},
        },
        "depot": base_depot(),
        "vehicles": base_vehicles(count=1, cap_colli=4),
        "orders": orders,
    }


def build_crunch_12d(single_window: bool = True) -> Dict[str, Any]:
    start = date(2025, 12, 1)
    days = 12
    all_days = dseq(start, days)
    orders: List[Dict[str, Any]] = []
    oid = 0
    for day_idx, ds in enumerate(all_days):
        for j in range(4):
            end_idx = min(days - 1, day_idx + 3)
            fds = all_days[day_idx : end_idx + 1]
            orders.append(
                mk_order(
                    oid=oid,
                    feasible_dates=fds,
                    lat=55.6800 + 0.01 * ((day_idx + j) % 4),
                    lon=12.5600 + 0.01 * ((day_idx + 2 * j) % 4),
                    tw=[420 + 10 * (j % 2), 780 + 10 * (j % 3)],
                    colli=2,
                    service=10,
                    release_date=ds,
                )
            )
            oid += 1

    cap = {}
    for i in range(days):
        if single_window:
            cap[str(i)] = 0.59 if 5 <= i <= 10 else 1.0
        else:
            cap[str(i)] = 0.59 if (2 <= i <= 3 or 8 <= i <= 9) else 1.0

    return {
        "metadata": {
            "description": "MVT 12-day crunch",
            "depot_name": "MVT_DEPOT",
            "horizon_start": all_days[0],
            "horizon_end": all_days[-1],
            "total_orders_in_file": len(orders),
            "capacity_profile": cap,
        },
        "depot": base_depot(),
        "vehicles": base_vehicles(count=1, cap_colli=8),
        "orders": orders,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_cases() -> List[CaseDef]:
    risk_model_path = ROOT / "models" / "risk_model.joblib"
    risk_exists = risk_model_path.exists()

    cases: List[CaseDef] = [
        CaseDef(
            case_name="A1_Tiny_Feasible",
            purpose="Minimal feasible route/metrics sanity",
            expected_days=4,
            seeds=[1],
            scenario_name="MVT_A1",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 1,
                "high_compute": 1,
                "use_risk_model": False,
                "max_trips": 2,
            },
            data_file="a1_tiny_feasible.json",
            checks={"expect_some_failures": False},
            tags=["A1", "tiny"],
        ),
        CaseDef(
            case_name="A2_Tiny_Infeasible",
            purpose="Must produce drop/failure instead of silent violation",
            expected_days=1,
            seeds=[1],
            scenario_name="MVT_A2",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 1,
                "high_compute": 1,
                "use_risk_model": False,
                "max_trips": 1,
            },
            data_file="a2_tiny_infeasible.json",
            checks={"expect_some_failures": True},
            tags=["A2", "infeasible"],
        ),
        CaseDef(
            case_name="A3_Deadline_Sweep",
            purpose="Deadline failure semantics with inside/outside horizon deadlines",
            expected_days=4,
            seeds=[1],
            scenario_name="MVT_A3",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 1,
                "high_compute": 1,
                "use_risk_model": False,
                "max_trips": 2,
            },
            data_file="a3_deadline_sweep.json",
            checks={"expect_out_of_horizon_carryover": True},
            tags=["A3", "deadline"],
        ),
        CaseDef(
            case_name="A4_Crunch_Compute_Gate",
            purpose="12-day crunch compute gating aligned with risk_mode_on",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A4",
            strategy_name="ProactiveRisk" if risk_exists else "Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 3,
                "high_compute": 9,
                "use_risk_model": bool(risk_exists),
                "risk_model_path": str(risk_model_path),
                "risk_threshold_on": 0.826,
                "risk_threshold_off": 0.496,
                "max_trips": 2,
            },
            data_file="a4_crunch_single.json",
            checks={"expect_risk_trigger": bool(risk_exists)},
            tags=["A4", "compute_gate", "crunch"],
        ),
        CaseDef(
            case_name="A4_REAL_EXP04_Seed1",
            purpose="Real-threshold real-model known-trigger scenario from existing EXP04 Seed_1 artifact",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A4_REAL",
            strategy_name="ProactiveRisk",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 60,
                "high_compute": 300,
                "use_risk_model": True,
                "risk_model_path": str(risk_model_path),
                "risk_threshold_on": 0.826,
                "risk_threshold_off": 0.496,
                "max_trips": 2,
            },
            data_file="real_multiday_benchmark_herlev.json",
            checks={"expect_risk_trigger": True, "known_trigger_case": True},
            tags=["A4", "real", "known_trigger"],
        ),
        CaseDef(
            case_name="A4_ALT_ForcedTrigger",
            purpose="Alternative minimal trigger scenario with relaxed risk thresholds for test only",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A4_ALT",
            strategy_name="ProactiveRisk" if risk_exists else "Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 3,
                "high_compute": 9,
                "use_risk_model": bool(risk_exists),
                "risk_model_path": str(risk_model_path),
                "risk_threshold_on": 0.10,
                "risk_threshold_off": 0.05,
                "max_trips": 2,
            },
            data_file="a4_crunch_single.json",
            checks={"is_alternative_trigger_case": True},
            tags=["A4", "compute_gate", "alternative"],
        ),
        CaseDef(
            case_name="A4b_MultiWindow_Capacity_Trace",
            purpose="Capacity profile trace for multi-window crunch",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A4B",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 2,
                "high_compute": 2,
                "use_risk_model": False,
                "max_trips": 2,
            },
            data_file="a4b_crunch_multiwindow.json",
            checks={"expect_risk_trigger": False},
            tags=["A4", "capacity_trace", "multi_window"],
        ),
        CaseDef(
            case_name="A5_Policy_Sanity_Proactive",
            purpose="Proactive baseline for policy sanity comparison",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A5",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 2,
                "high_compute": 2,
                "use_risk_model": False,
                "max_trips": 2,
            },
            data_file="a4_crunch_single.json",
            checks={},
            tags=["A5", "policy", "proactive"],
        ),
        CaseDef(
            case_name="A5_Policy_Sanity_Greedy",
            purpose="Greedy baseline for policy sanity comparison",
            expected_days=12,
            seeds=[1],
            scenario_name="MVT_A5",
            strategy_name="Greedy",
            sim_config={
                "mode": "greedy",
                "base_compute": 2,
                "high_compute": 2,
                "use_risk_model": False,
                "max_trips": 2,
            },
            data_file="a4_crunch_single.json",
            checks={},
            tags=["A5", "policy", "greedy"],
        ),
        CaseDef(
            case_name="A6_Determinism_Guard",
            purpose="Same config+seed repeated twice for determinism guard",
            expected_days=6,
            seeds=[1],
            scenario_name="MVT_A6",
            strategy_name="Proactive",
            sim_config={
                "mode": "proactive_quota",
                "base_compute": 2,
                "high_compute": 2,
                "use_risk_model": False,
                "max_trips": 2,
                "repeat_runs": 2,
            },
            data_file="a6_determinism.json",
            checks={"determinism_case": True},
            tags=["A6", "determinism"],
        ),
    ]
    return cases


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    datasets = {
        "a1_tiny_feasible.json": build_tiny_feasible(),
        "a2_tiny_infeasible.json": build_tiny_infeasible(),
        "a3_deadline_sweep.json": build_deadline_sweep(),
        "a4_crunch_single.json": build_crunch_12d(single_window=True),
        "a4b_crunch_multiwindow.json": build_crunch_12d(single_window=False),
        "a6_determinism.json": build_tiny_feasible() | {
            "metadata": {
                **build_tiny_feasible()["metadata"],
                "horizon_end": dseq(date(2025, 12, 1), 6)[-1],
                "capacity_profile": {str(i): 1.0 for i in range(6)},
            }
        },
        "real_multiday_benchmark_herlev.json": json.loads(
            (ROOT / "data" / "processed" / "multiday_benchmark_herlev.json").read_text(encoding="utf-8")
        ),
    }

    # Fix A6 dataset to exactly 6 days with more orders.
    a6 = build_tiny_feasible()
    a6_days = dseq(date(2025, 12, 1), 6)
    a6["metadata"]["horizon_end"] = a6_days[-1]
    a6["metadata"]["capacity_profile"] = {str(i): 1.0 for i in range(6)}
    extra = []
    for i in range(10):
        start_idx = min(max(0, i - 1), len(a6_days) - 1)
        end_idx = min(len(a6_days), start_idx + 3)
        fds = a6_days[start_idx:end_idx]
        if not fds:
            fds = [a6_days[-1]]
        extra.append(
            mk_order(
                200 + i,
                fds,
                55.681 + 0.004 * (i % 4),
                12.572 + 0.003 * (i % 3),
                [450, 900],
                1,
                8,
                a6_days[0],
            )
        )
    a6["orders"] = a6["orders"] + extra
    a6["metadata"]["total_orders_in_file"] = len(a6["orders"])
    datasets["a6_determinism.json"] = a6

    for name, data in datasets.items():
        write_json(DATA_DIR / name, data)

    cases = build_cases()
    case_index = []
    for c in cases:
        payload = {
            "case_name": c.case_name,
            "purpose": c.purpose,
            "expected_days": c.expected_days,
            "seeds": c.seeds,
            "scenario_name": c.scenario_name,
            "strategy_name": c.strategy_name,
            "sim_config": c.sim_config,
            "data_file": c.data_file,
            "data_path": str((DATA_DIR / c.data_file).relative_to(ROOT)),
            "checks": c.checks,
            "tags": c.tags,
        }
        if c.case_name == "A4_REAL_EXP04_Seed1":
            payload["source_run_dir"] = "data/results/EXP_EXP04/Seed_1"
        cfg_path = OUT_DIR / f"{c.case_name}.json"
        write_json(cfg_path, payload)
        case_index.append({"case_name": c.case_name, "config_path": str(cfg_path.relative_to(ROOT))})

    write_json(OUT_DIR / "mvt_case_index.json", {"cases": case_index})
    print(f"Generated {len(cases)} MVT cases under {OUT_DIR}")


if __name__ == "__main__":
    main()
