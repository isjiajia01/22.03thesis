EXPERIMENTS = {
    # ========================================================================
    # GROUP A: Baseline & Main Conclusions (MUST RUN)
    # ========================================================================

    "EXP00": {
        "name": "BAU_Baseline",
        "description": "Business-as-usual baseline (no pressure, no defense)",
        "params": {
            "ratio": 1.0,
            "total_days": 12,
            "crunch_start": None,
            "crunch_end": None,
            "use_risk_model": False,
            "base_compute": 60,
            "high_compute": 60,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "standard",
    },

    "EXP01": {
        "name": "Crunch_Baseline",
        "description": "Single-wave pressure, no defense (critical ratio)",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": False,
            "base_compute": 60,
            "high_compute": 60,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "standard",
    },

    "EXP02": {
        "name": "Static_Compute_Upper",
        "description": "Pure compute upper bound (300s, no defense)",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": False,
            "base_compute": 300,
            "high_compute": 300,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
    },

    "EXP03": {
        "name": "RiskGate_Only",
        "description": "Risk gate only, no compute switching (60s fixed)",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 60,  # Fixed at 60s
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "standard",
    },

    "EXP04": {
        "name": "Dynamic_Compute_RiskGate",
        "description": "Core contribution: Dynamic compute + RiskGate",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 300,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
    },

    # ========================================================================
    # GROUP B: Physical Bottleneck Breakthrough
    # ========================================================================

    "EXP05": {
        "name": "Trips_Expansion",
        "description": "Hardware expansion: max_trips 2→3",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": False,
            "base_compute": 300,
            "high_compute": 300,
            "max_trips_list": [2, 3],  # Sweep
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

    # ========================================================================
    # GROUP C: Boundary & Discretization
    # ========================================================================

    "EXP06": {
        "name": "Boundary_Probe",
        "description": "Phase transition boundary: 0.58 vs 0.59",
        "params": {
            "ratios": [0.58, 0.59],
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": False,
            "base_compute": 60,
            "high_compute": 60,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "standard",
        "is_sweep": True,
    },

    "EXP07": {
        "name": "Collapse_Stress",
        "description": "Cliff-edge collapse at 0.60",
        "params": {
            "ratios": [0.60, 0.61],
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model_list": [False, True],  # Both
            "base_compute": 60,
            "high_compute": 300,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

    # ========================================================================
    # GROUP D: Threshold Sensitivity
    # ========================================================================

    "EXP08": {
        "name": "Threshold_Sensitivity",
        "description": "Risk gate threshold sensitivity",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 300,
            "max_trips": 2,
            "delta_on_list": [0.6, 0.7, 0.826, 0.9],
            "delta_off_ratio": 0.6,  # delta_off = 0.6 * delta_on
        },
        "seeds": list(range(1, 6)),  # 5 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

    # ========================================================================
    # GROUP E: Risk Model Ablation
    # ========================================================================

    "EXP09": {
        "name": "Risk_Model_Ablation",
        "description": "Ablation: compare with/without risk model under same crunch",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model_list": [False, True],  # With vs without risk model
            "base_compute": 60,
            "high_compute": 300,
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

    # ========================================================================
    # GROUP F: Phase Diagram
    # ========================================================================

    "EXP10": {
        "name": "Phase_Diagram",
        "description": "Ratio sweep for phase diagram",
        "params": {
            "ratios": [0.55, 0.56, 0.57, 0.58, 0.59, 0.60, 0.61, 0.62, 0.63, 0.64, 0.65],
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model": True,
            "base_compute": 60,
            "high_compute": 300,
            "max_trips": 2,
        },
        "seeds": list(range(1, 4)),  # 3 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

    # ========================================================================
    # GROUP G: Compute ROI Curve
    # ========================================================================

    "EXP11": {
        "name": "Time_Limit_Sweep",
        "description": "Compute resource ROI curve",
        "params": {
            "ratio": 0.59,
            "total_days": 12,
            "crunch_start": 5,
            "crunch_end": 10,
            "use_risk_model_list": [False, True],
            "time_limits": [30, 60, 120, 300],
            "max_trips": 2,
        },
        "seeds": list(range(1, 11)),  # 10 seeds
        "resource": "heavy",
        "is_sweep": True,
    },

}


def get_experiment_count():
    """Calculate total number of runs."""
    total = 0
    for exp_id, exp in EXPERIMENTS.items():
        seeds = exp.get("seeds", [1])
        if exp.get("is_sweep"):
            # Estimate sweep size
            params = exp["params"]
            sweep_size = 1
            if "ratios" in params:
                sweep_size *= len(params["ratios"])
            if "max_trips_list" in params:
                sweep_size *= len(params["max_trips_list"])
            if "use_risk_model_list" in params:
                sweep_size *= len(params["use_risk_model_list"])
            if "delta_on_list" in params:
                sweep_size *= len(params["delta_on_list"])
            if "crunch_windows" in params:
                sweep_size *= len(params["crunch_windows"])
            if "time_limits" in params:
                sweep_size *= len(params["time_limits"])
            total += len(seeds) * sweep_size
        else:
            total += len(seeds)
    return total


if __name__ == "__main__":
    print("="*70)
    print("THESIS EXPERIMENT PLAN")
    print("="*70)
    print()

    for group, exps in [
        ("A. Baseline & Main Conclusions", ["EXP00", "EXP01", "EXP02", "EXP03", "EXP04"]),
        ("B. Physical Bottleneck", ["EXP05"]),
        ("C. Boundary & Discretization", ["EXP06", "EXP07"]),
        ("D. Threshold Sensitivity", ["EXP08"]),
        ("E. Risk Model Ablation", ["EXP09"]),
        ("F. Phase Diagram", ["EXP10"]),
        ("G. Compute ROI", ["EXP11"]),
    ]:
        print(f"\n{group}")
        print("-" * 70)
        for exp_id in exps:
            if exp_id in EXPERIMENTS:
                exp = EXPERIMENTS[exp_id]
                seeds = len(exp.get("seeds", [1]))
                print(f"  {exp_id}: {exp['name']}")
                print(f"    Seeds: {seeds}, Resource: {exp['resource']}")

    print()
    print("="*70)
    print(f"TOTAL RUNS: {get_experiment_count()}")
    print("="*70)
