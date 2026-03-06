#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rolling Horizon Integrated simulator (patched)

Key fixes vs your previous patched version:
1) Output directory structure is compatible with analysis scripts:
   - self.base_dir points to the "run root" (optionally a run_id folder)
   - self.run_dir is ALWAYS: <base_dir>/<scenario>/<strategy>
   This matches scripts expecting: <base_dir>/<scenario>/<strategy>/daily_stats.csv

2) __init__ is robust to experiment script signature drift:
   - accepts **kwargs and provides safe defaults for seed/verbose/run_context/results_dir/run_id/base_dir.

3) Import robustness:
   - ensures the repository root (folder containing "src/") is on sys.path
     so running from src/experiments works without manual PYTHONPATH tweaks.

Behavioral logic retained from your patched version:
- Always generates failed_orders.csv (even if empty).
- Failure logging with reasons:
    * vrp_dropped_on_deadline
    * policy_rejected_or_unserved (post-VRP sweep)
- failed_orders count uses failed_orders_log length (source of truth).
- plan_churn_effective uses carryover-pool Jaccard distance.

This file is intended to replace:
  src/simulation/rolling_horizon_integrated.py
"""

import sys
import os
import json
import copy
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# ==========================================
# Learned Allocator Import (optional)
# ==========================================
_ALLOCATOR_AVAILABLE = False
_BANDIT_ALLOCATOR_AVAILABLE = False

try:
    from code.allocator.allocator_inference import ComputeAllocator
    _ALLOCATOR_AVAILABLE = True
except ImportError:
    try:
        # Alternative import path
        import sys as _sys
        _allocator_path = Path(__file__).resolve().parents[2] / "code" / "allocator"
        if str(_allocator_path) not in _sys.path:
            _sys.path.insert(0, str(_allocator_path))
        from allocator_inference import ComputeAllocator
        _ALLOCATOR_AVAILABLE = True
    except ImportError:
        ComputeAllocator = None

# EXP13/14: Bandit-Augmented Allocator
try:
    from compute_allocator import (
        BanditAugmentedAllocator,
        FittedQAllocator,
        SparseFailSafeBandit,
        create_allocator,
        compute_reward_v2,
        AllocatorDebug
    )
    _BANDIT_ALLOCATOR_AVAILABLE = True
except ImportError:
    try:
        from simulation.compute_allocator import (
            BanditAugmentedAllocator,
            FittedQAllocator,
            SparseFailSafeBandit,
            create_allocator,
            compute_reward_v2,
            AllocatorDebug
        )
        _BANDIT_ALLOCATOR_AVAILABLE = True
    except ImportError:
        BanditAugmentedAllocator = None
        FittedQAllocator = None
        SparseFailSafeBandit = None
        create_allocator = None
        compute_reward_v2 = None
        AllocatorDebug = None

# ==========================================
# [Path Setup] FIRST - robust repo-root detection
# ==========================================
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = None

# Try to find repo root by looking for "src" or "code" directory
for _p in _THIS_FILE.parents:
    if (_p / "src").is_dir():
        _REPO_ROOT = _p
        break
    if (_p / "code").is_dir() and (_p / "data").is_dir():
        _REPO_ROOT = _p
        break

if _REPO_ROOT is None:
    # Fallback: best-effort
    _REPO_ROOT = _THIS_FILE.parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Also add code directory for imports
_CODE_DIR = _REPO_ROOT / "code"
if _CODE_DIR.is_dir() and str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# Try different import paths
try:
    from src.simulation.policies import GreedyPolicy, ProactivePolicy, StabilityPolicy
    from src.solvers.alns_solver import ALNS_Solver
except ImportError:
    try:
        from simulation.policies import GreedyPolicy, ProactivePolicy, StabilityPolicy
        from solvers.alns_solver import ALNS_Solver
    except ImportError:
        from policies import GreedyPolicy, ProactivePolicy, StabilityPolicy
        from solvers.alns_solver import ALNS_Solver


# ==========================================
# Helper Functions
# ==========================================
def is_order_released(order, current_date):
    r_date_str = order.get("release_date") or order.get("order_date")
    if not r_date_str:
        return True
    r_dt = datetime.strptime(r_date_str, "%Y-%m-%d")
    return r_dt <= current_date


def calculate_real_daily_capacity(vehicles_config, availability_ratio=1.0):
    total_colli = 0
    total_volume = 0
    adjusted_config = []
    for v_type in vehicles_config:
        original_count = v_type["count"]
        active_count = int(original_count * availability_ratio)
        cap = v_type["capacity"]
        total_colli += active_count * cap["colli"]
        total_volume += active_count * cap["volume"]
        v_copy = copy.deepcopy(v_type)
        v_copy["count"] = active_count
        adjusted_config.append(v_copy)
    return total_colli, total_volume, adjusted_config


def _normalize_stop_to_order_id(stop, todays_orders, orders_map):
    """Normalize ALNS route stops to real order_id."""
    if stop is None:
        return None
    if stop in orders_map:
        return stop
    if stop == 0 or stop == "0" or stop == "DEPOT" or stop == "depot":
        return None
    if isinstance(stop, int):
        idx = stop - 1
        if 0 <= idx < len(todays_orders):
            oid = todays_orders[idx].get("id")
            return oid if oid in orders_map else None
    if isinstance(stop, str) and stop.isdigit():
        idx = int(stop) - 1
        if 0 <= idx < len(todays_orders):
            oid = todays_orders[idx].get("id")
            return oid if oid in orders_map else None
    return None


def _normalize_dropped_to_order_id(d, todays_orders, orders_map):
    """Normalize ALNS dropped indices / ids to real order_id."""
    if d is None:
        return None
    if d in orders_map:
        return d
    if isinstance(d, (list, tuple)) and len(d) > 0:
        return _normalize_dropped_to_order_id(d[0], todays_orders, orders_map)
    if isinstance(d, int):
        idx = d - 1
        if 0 <= idx < len(todays_orders):
            oid = todays_orders[idx].get("id")
            return oid if oid in orders_map else None
    if isinstance(d, str) and d.isdigit():
        return _normalize_dropped_to_order_id(int(d), todays_orders, orders_map)
    return None


# ==========================================
# Global Capacity Analyzer
# ==========================================
class GlobalCapacityAnalyzer:
    def __init__(self, orders, vehicles_config, start_date, end_date, capacity_profile=None):
        self.orders = orders
        self.start_date = start_date
        self.end_date = end_date
        self.vehicles_config = vehicles_config
        self.capacity_profile = capacity_profile if capacity_profile else {}
        self.target_load_profile = {}
        self.order_target_day = {}
        self.daily_capacity_limit = {}

        curr = self.start_date
        day_idx = 0
        while curr <= self.end_date:
            d_str = curr.strftime("%Y-%m-%d")
            ratio = float(self.capacity_profile.get(str(day_idx), 1.0))
            cap_colli, _, _ = calculate_real_daily_capacity(self.vehicles_config, ratio)
            self.daily_capacity_limit[d_str] = cap_colli
            self.target_load_profile[d_str] = 0
            curr += timedelta(days=1)
            day_idx += 1

        self._calculate_target_load_profile()

    def _calculate_target_load_profile(self):
        temp_load = {d: 0 for d in self.target_load_profile}
        sorted_orders = sorted(self.orders, key=lambda x: x["feasible_dates"][-1])

        for order in sorted_orders:
            colli = order["demand"]["colli"]
            best_day = None
            min_load_ratio = float("inf")

            for d_str in order["feasible_dates"]:
                if d_str not in temp_load:
                    continue
                limit = self.daily_capacity_limit.get(d_str, 0)
                if limit <= 0:
                    continue
                ratio = temp_load[d_str] / limit
                if ratio < min_load_ratio:
                    min_load_ratio = ratio
                    best_day = d_str

            if best_day:
                temp_load[best_day] += colli
                self.order_target_day[order["id"]] = best_day
            else:
                fallback = order["feasible_dates"][-1]
                if fallback in temp_load:
                    temp_load[fallback] += colli
                    self.order_target_day[order["id"]] = fallback

        self.target_load_profile = temp_load

    def get_target_day(self, order_id):
        return self.order_target_day.get(order_id, None)

    def get_day_target_load(self, date_str):
        return self.target_load_profile.get(date_str, 0)


# ==========================================
# Rolling Horizon Integrated
# ==========================================
class RollingHorizonIntegrated:
    def __init__(self, data_source, strategy_config=None, validator=None, **kwargs):
        """
        Args:
            data_source: dict or path to json
            strategy_config: dict for policy configuration
            validator: optional external validator
            **kwargs: accepts (non-exhaustive)
                seed: int
                verbose: bool
                run_context: dict with keys {"scenario","strategy"}
                results_dir: str (parent folder that will contain run_id folder)
                run_id: str (run folder name; defaults to timestamp)
                base_dir: str (explicit run root; if provided, takes precedence over results_dir/run_id)
                scenario_name / strategy_name: optional overrides
        """
        import random

        self.seed = int(kwargs.get("seed", 42))
        random.seed(self.seed)
        self.validator = validator
        self.verbose = bool(kwargs.get("verbose", False))

        self.run_context = kwargs.get("run_context") or {}
        self.scenario_name = self.run_context.get("scenario", "UNKNOWN_SCENARIO")
        self.strategy_name = self.run_context.get("strategy", "UNKNOWN_STRATEGY")

        # optional direct overrides
        self.scenario_name = kwargs.get("scenario_name", self.scenario_name)
        self.strategy_name = kwargs.get("strategy_name", self.strategy_name)

        # ------------------------------
        # Output directory structure
        # ------------------------------
        run_id = kwargs.get("run_id")
        base_dir = kwargs.get("base_dir")  # if provided, this is already the "run root"
        results_dir = kwargs.get("results_dir")

        if base_dir:
            run_root = str(base_dir)
            self.run_id = str(run_id) if run_id else os.path.basename(os.path.normpath(run_root))
        else:
            self.run_id = str(run_id) if run_id else datetime.now().strftime("%Y%m%d_%H%M%S")
            results_dir = str(results_dir) if results_dir else os.path.join(str(_REPO_ROOT), "data", "results", "thesis_runs")
            run_root = os.path.join(results_dir, self.run_id)

        self.base_dir = run_root  # <-- analysis scripts should pass this as --base_dir
        self.run_dir = os.path.join(self.base_dir, self.scenario_name, self.strategy_name)
        os.makedirs(self.run_dir, exist_ok=True)

        # ------------------------------
        # Load data
        # ------------------------------
        if isinstance(data_source, str):
            with open(data_source, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = data_source

        self.all_orders = self.data["orders"]
        self.orders_map = {o["id"]: o for o in self.all_orders}
        self.depot = self.data["depot"]
        self.vehicles_config = self.data["vehicles"]

        self.start_date = datetime.strptime(self.data["metadata"]["horizon_start"], "%Y-%m-%d")
        self.end_date = datetime.strptime(self.data["metadata"]["horizon_end"], "%Y-%m-%d")
        self.current_date = self.start_date

        # ------------------------------
        # State
        # ------------------------------
        self.completed_order_ids = set()
        self.failed_order_ids = set()  # for filtering "zombies"
        self.failed_orders_log = []    # structured logs -> failed_orders.csv
        self.daily_stats = []
        self.vrp_audit_traces = []
        self.total_horizon_cost = 0.0

        # churn + stickiness
        self.prev_selected_ids = set()   # yesterday planned set (plan turnover)
        self.prev_suggested_day = {}     # for target churn
        self.prev_planned_ids = set()    # carryover pool: planned-but-not-delivered
        # previous-day VRP outcomes (for crisis stop-capping heuristics)
        self.prev_day_planned = None
        self.prev_day_vrp_dropped = None

        # ------------------------------
        # Config + policy
        # ------------------------------
        default_config = {
            "mode": "proactive_quota",
            "lookahead_days": 3,
            "buffer_ratio": 1.05,
            "weights": {"urgency": 20.0, "profile": 2.0},
            "penalty_per_fail": 150.0,
        }
        if strategy_config:
            default_config.update(strategy_config)
        self.config = default_config

        mode = self.config["mode"]
        if mode == "greedy":
            self.policy = GreedyPolicy(self.config)
        elif mode == "stability":
            self.policy = StabilityPolicy(self.config)
        else:
            self.policy = ProactivePolicy(self.config)

        # ------------------------------
        # Learned Allocator (optional)
        # ------------------------------
        self.learned_allocator = None
        self.bandit_allocator = None  # EXP13/14: Bandit-Augmented Allocator
        self.prev_day_failures = 0  # Track previous day failures for allocator features
        self.allocator_type = self.config.get('allocator_type', 'fitted_q')

        if self.config.get('use_learned_allocator', False):
            allocator_model_path = self.config.get('allocator_model_path')

            # EXP14: Use SparseFailSafeBandit if specified
            if self.allocator_type in ('sparse_fail_safe', 'exp14', 'sfb') and _BANDIT_ALLOCATOR_AVAILABLE:
                try:
                    allocator_config = {
                        "policy": self.config.get('allocator_policy', 'epsilon_greedy'),
                        "epsilon_schedule": self.config.get('epsilon_schedule', {
                            "kind": "piecewise",
                            "warmup_days": 2,
                            "eps_start": 0.15,
                            "eps_end": 0.03
                        }),
                        "guardrails": {"enabled": False},  # Disabled for EXP14
                        "lambda_compute": self.config.get('allocator_lambda', 0.05),
                        "fail_safe": self.config.get('fail_safe', {}),
                    }
                    self.bandit_allocator = SparseFailSafeBandit(
                        q_model_path=allocator_model_path,
                        run_dir=self.run_dir,
                        seed=self.seed,
                        config=allocator_config
                    )
                    if self.verbose:
                        print(f"[Allocator] Loaded SparseFailSafeBandit: {allocator_model_path}")
                except Exception as e:
                    print(f"[Allocator] Failed to load SparseFailSafeBandit: {e}")
                    self.bandit_allocator = None

            # EXP13: Use BanditAugmentedAllocator if specified
            elif self.allocator_type in ('bandit_augmented', 'exp13', 'baa') and _BANDIT_ALLOCATOR_AVAILABLE:
                try:
                    allocator_config = {
                        "policy": self.config.get('allocator_policy', 'epsilon_greedy'),
                        "epsilon_schedule": self.config.get('epsilon_schedule', {
                            "kind": "piecewise",
                            "warmup_days": 2,
                            "eps_start": 0.15,
                            "eps_end": 0.03
                        }),
                        "guardrails": self.config.get('guardrails', {"enabled": True}),
                        "lambda_compute": self.config.get('allocator_lambda', 0.05),
                    }
                    self.bandit_allocator = BanditAugmentedAllocator(
                        q_model_path=allocator_model_path,
                        run_dir=self.run_dir,
                        seed=self.seed,
                        config=allocator_config
                    )
                    if self.verbose:
                        print(f"[Allocator] Loaded BanditAugmentedAllocator: {allocator_model_path}")
                        print(f"[Allocator] Policy: {allocator_config['policy']}")
                        print(f"[Allocator] Guardrails: {allocator_config['guardrails']}")
                except Exception as e:
                    print(f"[Allocator] Failed to load BanditAugmentedAllocator: {e}")
                    self.bandit_allocator = None

            # Fallback to original ComputeAllocator (EXP12)
            elif allocator_model_path and _ALLOCATOR_AVAILABLE:
                try:
                    self.learned_allocator = ComputeAllocator(
                        model_path=allocator_model_path,
                        fallback_action=self.config.get('base_compute', 60)
                    )
                    if self.verbose:
                        print(f"[Allocator] Loaded FittedQ model: {allocator_model_path}")
                except Exception as e:
                    print(f"[Allocator] Failed to load model: {e}")
                    self.learned_allocator = None
            elif not _ALLOCATOR_AVAILABLE and not _BANDIT_ALLOCATOR_AVAILABLE:
                print("[Allocator] Warning: allocator modules not available")
            elif not allocator_model_path:
                print("[Allocator] Warning: use_learned_allocator=True but no allocator_model_path specified")

    # ---------------------------------
    # Helper: get previous day failures
    # ---------------------------------
    def _get_prev_failures(self):
        """Get the number of failures from the previous day."""
        return self.prev_day_failures

    # ---------------------------------
    # churn(target): target-day churn
    # ---------------------------------
    def calculate_suggestion_churn(self, current_analyzer, visible_orders):
        churn_count = 0
        common = 0
        current_suggestions = {}

        for order in visible_orders:
            oid = order["id"]
            new_target = current_analyzer.get_target_day(oid)
            current_suggestions[oid] = new_target
            if oid in self.prev_suggested_day:
                common += 1
                if self.prev_suggested_day[oid] != new_target:
                    churn_count += 1

        self.prev_suggested_day = current_suggestions
        return {"count": churn_count, "rate": (churn_count / common if common > 0 else 0.0), "intersection": common}

    def _log_failure(self, oid, d_str, reason):
        """Add a failure entry once (idempotent)."""
        if oid in self.failed_order_ids:
            return
        self.failed_order_ids.add(oid)

        o = self.orders_map.get(oid, {})
        f = {
            "id": oid,
            "scenario": self.scenario_name,
            "strategy": self.strategy_name,
            "fail_date": d_str,
            "deadline": (o.get("feasible_dates") or [None])[-1],
            "release_date": o.get("release_date") or o.get("order_date"),
            "reason": str(reason),
        }
        self.failed_orders_log.append(f)

    # ---------------------------------
    # main loop
    # ---------------------------------
    def run_simulation(self):
        cap_profile = self.data.get("metadata", {}).get("capacity_profile", {})

        vrp_config = {"base_penalty": 2000, "urgent_penalty": 1e7, "beta": 5.0, "epsilon": 0.1}

        while self.current_date <= self.end_date:
            d_str = self.current_date.strftime("%Y-%m-%d")
            day_idx = (self.current_date - self.start_date).days

            # --- visible orders (filter completed + failed zombies) ---
            visible_open_orders = [
                o for o in self.all_orders
                if o["id"] not in self.completed_order_ids
                and o["id"] not in self.failed_order_ids
                and is_order_released(o, self.current_date)
            ]

            # capacity
            ratio = float(cap_profile.get(str(day_idx), 1.0))
            daily_cap_colli, _, adjusted_vehicles = calculate_real_daily_capacity(self.vehicles_config, ratio)

            # number of vehicles today (optional; some policies use it)
            try:
                n_vehicles_today = int(sum(v.get("count", 0) for v in adjusted_vehicles))
            except Exception:
                n_vehicles_today = 0

            # pressure window
            lookahead_check = int(self.config.get("pressure_lookahead", 7))
            ratios_window = [float(cap_profile.get(str(day_idx + k), 1.0)) for k in range(0, lookahead_check + 1)]
            min_ratio = min(ratios_window) if ratios_window else 1.0
            k_star = ratios_window.index(min_ratio) if ratios_window else 999

            analyzer = GlobalCapacityAnalyzer(
                visible_open_orders,
                self.vehicles_config,
                self.current_date,
                self.end_date,
                capacity_profile=cap_profile,
            )

            # --- policy selection ---
            carry_prev = set(self.prev_planned_ids) if self.prev_planned_ids else set()
            todays_orders = self.policy.select_orders(
                current_date=self.current_date,
                visible_orders=visible_open_orders,
                analyzer=analyzer,
                prev_planned_ids=self.prev_planned_ids,
                daily_capacity_colli=daily_cap_colli,
                future_capacity_pressure=min_ratio,
                pressure_k_star=k_star,
                prev_selected_ids=self.prev_selected_ids,
                capacity_ratio_today=ratio,
                prev_day_planned=self.prev_day_planned,
                prev_day_vrp_dropped=self.prev_day_vrp_dropped,
                depot=self.depot,
                n_vehicles=n_vehicles_today,
            )

            planned_ids_today = [o["id"] for o in todays_orders]
            current_selected_ids = set(planned_ids_today)

            # -------------------------
            # Dynamic Compute: Read risk metrics and set VRP time limit
            # -------------------------
            policy_debug = getattr(self.policy, "last_debug_info", {}) or {}

            # Handle risk_p: if NaN (risk model disabled or invalid), keep as NaN
            risk_p_raw = policy_debug.get('risk_p', np.nan)  # Default to NaN, not 0.5
            if isinstance(risk_p_raw, float) and np.isnan(risk_p_raw):
                risk_p = risk_p_raw  # Keep NaN
            else:
                risk_p = float(risk_p_raw)

            risk_p_valid = bool(policy_debug.get('risk_p_valid', False))
            risk_mode_on = bool(policy_debug.get('risk_mode_on', False))
            risk_logit = float(policy_debug.get('risk_logit', 0.0))

            # Set compute limit based on risk_mode_on ONLY (not risk_p threshold)
            # This ensures compute_limit_seconds aligns exactly with risk_mode_on
            # base/high values come from config (single source of truth)
            base_compute = int(self.config.get('base_compute',
                               int(os.environ.get("VRP_TIME_LIMIT_SECONDS", 60))))
            high_compute = int(self.config.get('high_compute',
                               int(os.environ.get("VRP_HIGH_COMPUTE_LIMIT", base_compute))))

            # -------------------------
            # Learned Allocator Integration (Step 3 / EXP13)
            # -------------------------
            allocator_action_raw = None
            allocator_action_final = None
            allocator_fallback_reason = None
            allocator_lambda = None
            allocator_model_name = None
            # EXP13 additional audit fields
            allocator_debug = None  # Will hold AllocatorDebug object
            allocator_qhat = {30: 0.0, 60: 0.0, 120: 0.0, 300: 0.0}
            allocator_epsilon = 0.0
            allocator_propensity = 1.0
            allocator_triggered_guards = []
            allocator_exploration = False
            allocator_policy_name = "none"

            use_learned_allocator = bool(self.config.get('use_learned_allocator', False))

            # Build feature dict for allocator (shared by EXP12 and EXP13)
            allocator_features = {
                "capacity_ratio": float(ratio),
                "capacity_pressure": float(min_ratio),
                "pressure_k_star": float(k_star),
                "visible_open_orders": float(len(visible_open_orders)),
                "mandatory_count": float(policy_debug.get("mandatory_count", 0)),
                "prev_drop_rate": float(self.prev_day_vrp_dropped / self.prev_day_planned) if self.prev_day_planned and self.prev_day_planned > 0 else 0.0,
                "prev_failures": float(self._get_prev_failures()),
                "target_load": float(analyzer.target_load_profile.get(d_str, 0)),
                "served_colli_lag1": float(self.daily_stats[-1]["served_colli"]) if self.daily_stats else 0.0,
                "vrp_dropped_lag1": float(self.prev_day_vrp_dropped) if self.prev_day_vrp_dropped is not None else 0.0,
                "failures_lag1": float(self._get_prev_failures()),
                # EXP13 additional features
                "due_today_count": float(policy_debug.get("due_today_count", 0)),
                "due_soon_count": float(policy_debug.get("due_soon_count", 0)),
                "day_index": float(len(self.daily_stats)),
            }

            # EXP13: Use BanditAugmentedAllocator if available
            if use_learned_allocator and self.bandit_allocator is not None:
                try:
                    allocator_action_final, allocator_debug = self.bandit_allocator.select_action(allocator_features)
                    allocator_action_raw = allocator_debug.original_action
                    allocator_lambda = self.config.get('allocator_lambda', 0.05)
                    allocator_model_name = f"BAA_{self.bandit_allocator.policy}"

                    # Extract audit fields from debug
                    allocator_qhat = {
                        30: allocator_debug.qhat_30,
                        60: allocator_debug.qhat_60,
                        120: allocator_debug.qhat_120,
                        300: allocator_debug.qhat_300,
                    }
                    allocator_epsilon = allocator_debug.epsilon
                    allocator_propensity = allocator_debug.propensity
                    allocator_triggered_guards = allocator_debug.triggered_guards
                    allocator_exploration = allocator_debug.exploration_triggered
                    allocator_policy_name = allocator_debug.policy

                except Exception as e:
                    allocator_fallback_reason = f"bandit_error: {str(e)[:50]}"
                    allocator_action_raw = None
                    allocator_action_final = None
                    allocator_debug = None

            # EXP12: Use original ComputeAllocator
            elif use_learned_allocator and self.learned_allocator is not None:
                try:
                    # Get raw action from allocator
                    allocator_action_raw = self.learned_allocator.predict(allocator_features)
                    allocator_lambda = self.learned_allocator.lambda_compute
                    allocator_model_name = self.learned_allocator.model_path.name if self.learned_allocator.model_path else "unknown"
                    allocator_policy_name = "fitted_q"

                    # Apply safety guardrails
                    allocator_action_final = allocator_action_raw

                    # Guardrail 1: Avoid 60s (observed to be in "search trajectory valley")
                    if allocator_action_raw == 60:
                        if risk_mode_on:
                            allocator_action_final = 120
                            allocator_triggered_guards.append("avoid_60s_high_risk")
                        else:
                            allocator_action_final = 30
                            allocator_triggered_guards.append("avoid_60s_low_risk")

                    # Guardrail 2: Risk floor - minimum 300s when risk_mode_on
                    if risk_mode_on and allocator_action_final < 300:
                        allocator_action_final = 300
                        allocator_triggered_guards.append("risk_floor")

                    # Guardrail 3: Capacity crunch floor - minimum 60s when capacity_ratio < 1.0
                    if ratio < 1.0 and allocator_action_final < 60:
                        allocator_action_final = 60
                        allocator_triggered_guards.append("crunch_floor")

                    # Validate action is in valid set
                    if allocator_action_final not in {30, 60, 120, 300}:
                        allocator_fallback_reason = f"invalid_action_{allocator_action_final}"
                        allocator_action_final = None

                except Exception as e:
                    allocator_fallback_reason = f"prediction_error: {str(e)[:50]}"
                    allocator_action_raw = None
                    allocator_action_final = None

            # Compute limit decision
            if use_learned_allocator and allocator_action_final is not None:
                # Use learned allocator's decision
                compute_limit = allocator_action_final
            else:
                # Fallback to original binary logic
                if use_learned_allocator and allocator_fallback_reason is None:
                    allocator_fallback_reason = "allocator_not_loaded"

                if risk_mode_on:
                    compute_limit = high_compute
                else:
                    compute_limit = base_compute

            os.environ["VRP_TIME_LIMIT_SECONDS"] = str(compute_limit)

            # churn(target)
            target_churn_stats = self.calculate_suggestion_churn(analyzer, visible_open_orders)

            # (optional) turnover between consecutive planned sets (not used in summary)
            if self.prev_selected_ids:
                inter2 = len(self.prev_selected_ids & current_selected_ids)
                union2 = len(self.prev_selected_ids | current_selected_ids)
                _ = 1.0 - (inter2 / union2) if union2 > 0 else 0.0

            self.prev_selected_ids = current_selected_ids

            # VRP
            cost = 0.0
            served_colli = 0.0
            delivered_ids_today = []
            failed_today_count = 0
            vrp_dropped = 0
            vrp_routes = 0
            vrp_avg_dist = 0.0
            routes = []
            dropped_raw = []
            result = None

            if todays_orders and daily_cap_colli > 0:
                daily_data = {
                    "metadata": self.data.get("metadata", {}),
                    "depot": self.depot,
                    "vehicles": adjusted_vehicles,
                    "orders": todays_orders,
                }
                solver = ALNS_Solver(daily_data, d_str, config=vrp_config)
                result = solver.solve()

                if result:
                    routes = result.get("routes", [])
                    vrp_routes = len(routes)
                    dists = [r.get("distance", 0.0) for r in routes]
                    vrp_avg_dist = (sum(dists) / len(dists)) if dists else 0.0

                    dropped_raw = result.get("dropped_indices", result.get("dropped", result.get("dropped_orders", [])))
                    vrp_dropped = len(dropped_raw) if dropped_raw else 0

                    # delivered ids
                    delivered_set = set()
                    for route in routes:
                        for stop in route.get("stops", []):
                            oid = _normalize_stop_to_order_id(stop, todays_orders, self.orders_map)
                            if oid is not None:
                                delivered_set.add(oid)
                    delivered_ids_today = list(delivered_set)

                    # VRP-dropped orders: mark as failure ONLY if dropped on its deadline day
                    if dropped_raw:
                        for d in dropped_raw:
                            oid = _normalize_dropped_to_order_id(d, todays_orders, self.orders_map)
                            if oid is None:
                                continue
                            o = self.orders_map.get(oid)
                            if not o:
                                continue
                            fds = o.get("feasible_dates") or []
                            if fds and fds[-1] == d_str:
                                self._log_failure(oid, d_str, reason="vrp_dropped_on_deadline")
                                failed_today_count += 1

                    # commit deliveries + cost
                    self.completed_order_ids.update(delivered_ids_today)
                    cost = float(result.get("cost", 0.0))
                    for oid in delivered_ids_today:
                        served_colli += float(self.orders_map[oid]["demand"]["colli"])
                    self.total_horizon_cost += cost

            # Post-VRP deadline sweep: any order whose deadline is today and not delivered is a fail.
            # We disambiguate:
            #   - if it was planned today -> VRP-level unserved (routing/time-window/solver)
            #   - if it was NOT planned today -> policy-level rejection/unserved
            delivered_set_today = set(delivered_ids_today)
            planned_set_today = set(planned_ids_today)
            for o in visible_open_orders:
                oid = o["id"]
                if oid in delivered_set_today:
                    continue
                if oid in self.failed_order_ids:
                    continue
                fds = o.get("feasible_dates") or []
                if fds and fds[-1] == d_str:
                    if oid in planned_set_today:
                        self._log_failure(oid, d_str, reason="vrp_unserved_on_deadline")
                    else:
                        self._log_failure(oid, d_str, reason="policy_rejected_or_unserved")
                    failed_today_count += 1

            # carryover pool (planned but not delivered)
            carry_today = set(planned_ids_today) - delivered_set_today

            self.vrp_audit_traces.append({
                "date": d_str,
                "day_idx": int(day_idx),
                "visible_open_order_ids": [o.get("id") for o in visible_open_orders],
                "planned_order_ids": list(planned_ids_today),
                "delivered_order_ids": list(delivered_ids_today),
                "vrp_dropped_order_ids": list(dropped_raw) if (todays_orders and daily_cap_colli > 0 and result) else [],
                "routes": routes if (todays_orders and daily_cap_colli > 0 and result) else [],
                "capacity_ratio": float(ratio),
                "daily_capacity_colli": float(daily_cap_colli),
            })

            planned_prev_count = len(carry_prev)
            planned_curr_count = len(carry_today)
            planned_intersection = len(carry_prev & carry_today)
            planned_union = len(carry_prev | carry_today)

            plan_churn_raw = 1.0 - (planned_intersection / planned_union) if planned_union > 0 else 0.0
            plan_churn_effective = plan_churn_raw

            # Update carryover pool for next day
            self.prev_planned_ids = carry_today

            self.daily_stats.append({
                "date": d_str,
                "cost": cost,
                "failures": int(failed_today_count),
                "served_colli": float(served_colli),
                "target_load": float(analyzer.get_day_target_load(d_str)),
                "target_churn": float(target_churn_stats["rate"]),
                "target_churn_common": int(target_churn_stats["intersection"]),
                "target_churn_count": int(target_churn_stats["count"]),
                "plan_churn_raw": float(plan_churn_raw),
                "plan_churn_effective": float(plan_churn_effective),
                "planned_prev_count": int(planned_prev_count),
                "planned_curr_count": int(planned_curr_count),
                "planned_intersection": int(planned_intersection),
                "planned_union": int(planned_union),
                "mode_status": policy_debug.get("mode_status", "unknown"),
                "kept_count": int(policy_debug.get("kept_count", 0)),
                "frozen_count": int(policy_debug.get("frozen_count", 0)),
                "mandatory_count": int(policy_debug.get("mandatory_count", 0)),
                "capacity_pressure": float(min_ratio),
                "pressure_k_star": int(k_star),
                "capacity_ratio": float(ratio),
                "capacity": float(daily_cap_colli),
                "visible_open_orders": int(len(visible_open_orders)),
                "planned_today": int(len(planned_ids_today)),
                "delivered_today": int(len(delivered_ids_today)),
                "vrp_routes": int(vrp_routes),
                "vrp_avg_dist": float(vrp_avg_dist),
                "vrp_dropped": int(vrp_dropped),
                "risk_p": float(risk_p),
                "risk_p_valid": int(risk_p_valid),  # Add validity flag
                "risk_mode_on": int(risk_mode_on),
                "risk_logit": float(risk_logit),
                "compute_limit_seconds": int(compute_limit),  # Actual limit used today
                "compute_base_seconds": int(base_compute),    # Config base (for audit)
                "compute_high_seconds": int(high_compute),    # Config high (for audit)
                # Allocator fields (Step 3 / EXP13)
                "allocator_enabled": int(use_learned_allocator),
                "allocator_action_raw": int(allocator_action_raw) if allocator_action_raw is not None else -1,
                "allocator_action_final": int(allocator_action_final) if allocator_action_final is not None else -1,
                "allocator_lambda": float(allocator_lambda) if allocator_lambda is not None else -1.0,
                "allocator_model": str(allocator_model_name) if allocator_model_name else "",
                "allocator_fallback_reason": str(allocator_fallback_reason) if allocator_fallback_reason else "",
                # EXP13 additional audit fields
                "allocator_policy": str(allocator_policy_name),
                "allocator_epsilon": float(allocator_epsilon),
                "allocator_propensity": float(allocator_propensity),
                "allocator_exploration": int(allocator_exploration),
                "allocator_qhat_30": float(allocator_qhat.get(30, 0.0)),
                "allocator_qhat_60": float(allocator_qhat.get(60, 0.0)),
                "allocator_qhat_120": float(allocator_qhat.get(120, 0.0)),
                "allocator_qhat_300": float(allocator_qhat.get(300, 0.0)),
                "allocator_triggered_guards": ",".join(allocator_triggered_guards) if allocator_triggered_guards else "",
            })

            # Add hysteresis controller state if risk gate is enabled
            if hasattr(self.policy, 'risk_controller') and self.policy.risk_controller is not None:
                controller_state = self.policy.risk_controller.get_state_dict()
                self.daily_stats[-1]["risk_exit_counter"] = int(controller_state.get("risk_exit_counter", 0))
                self.daily_stats[-1]["risk_delta_on"] = float(controller_state.get("risk_delta_on", np.nan))
                self.daily_stats[-1]["risk_delta_off"] = float(controller_state.get("risk_delta_off", np.nan))
            else:
                # Gate not enabled: use default values
                self.daily_stats[-1]["risk_exit_counter"] = 0
                self.daily_stats[-1]["risk_delta_on"] = float(np.nan)
                self.daily_stats[-1]["risk_delta_off"] = float(np.nan)

            # Track risk model load status (critical for validation)
            if hasattr(self.policy, 'risk_predictor') and self.policy.risk_predictor is not None:
                self.daily_stats[-1]["risk_model_loaded"] = int(self.policy.risk_predictor.model_loaded)
            else:
                self.daily_stats[-1]["risk_model_loaded"] = 0

            # store previous-day VRP outcomes for next-day policy heuristics
            self.prev_day_planned = int(len(planned_ids_today))
            self.prev_day_vrp_dropped = int(vrp_dropped)
            self.prev_day_failures = int(failed_today_count)  # For allocator features

            # -------------------------
            # Feedback Loop: Call policy.on_day_end to update memory
            # -------------------------
            if hasattr(self.policy, 'on_day_end'):
                day_stats_for_policy = {
                    'planned': int(len(planned_ids_today)),
                    'vrp_dropped': int(vrp_dropped),
                    'failures': int(failed_today_count),
                }
                self.policy.on_day_end(day_stats_for_policy)

            # -------------------------
            # EXP13: Update Bandit Allocator with reward
            # -------------------------
            if self.bandit_allocator is not None and allocator_debug is not None:
                # Compute reward_v2
                reward_v2 = compute_reward_v2(
                    failures=int(failed_today_count),
                    vrp_dropped=int(vrp_dropped),
                    action_seconds=int(allocator_action_final) if allocator_action_final else 60,
                    lambda_compute=self.config.get('allocator_lambda', 0.05)
                )
                # Update allocator with today's outcome
                self.bandit_allocator.update(
                    day_ctx=allocator_features,
                    action=int(allocator_action_final) if allocator_action_final else 60,
                    reward=reward_v2,
                    debug=allocator_debug,
                    today_failures=int(failed_today_count)
                )
                # Record reward in daily_stats
                self.daily_stats[-1]["allocator_reward_v2"] = float(reward_v2)

            self.current_date += timedelta(days=1)

        return self.calculate_metrics()

    # ---------------------------------
    # metrics + outputs
    # ---------------------------------
    def calculate_metrics(self):
        if not self.daily_stats:
            return {}

        eligible_orders = [o for o in self.all_orders if is_order_released(o, self.end_date)]
        eligible_count = len(eligible_orders)

        delivered_count = len(self.completed_order_ids)
        failed_count = len(self.failed_orders_log)  # SOURCE OF TRUTH for penalty + reporting

        total_cost = float(self.total_horizon_cost)
        penalty_per_fail = float(self.config.get("penalty_per_fail", 150.0))
        penalized_cost = total_cost + failed_count * penalty_per_fail

        service_rate = (delivered_count / eligible_count) if eligible_count > 0 else 0.0
        cost_per_order = (total_cost / delivered_count) if delivered_count > 0 else 0.0

        loads = [float(s["served_colli"]) for s in self.daily_stats]
        targets = [float(s["target_load"]) for s in self.daily_stats]
        load_mse = sum((l - t) ** 2 for l, t in zip(loads, targets)) / len(loads) if loads else 0.0

        avg_target_churn = sum(float(s["target_churn"]) for s in self.daily_stats) / len(self.daily_stats)
        avg_plan_churn_effective = sum(float(s["plan_churn_effective"]) for s in self.daily_stats) / len(self.daily_stats)
        avg_plan_churn_raw = sum(float(s["plan_churn_raw"]) for s in self.daily_stats) / len(self.daily_stats)

        # daily_stats.csv
        df = pd.DataFrame(self.daily_stats)

        # aggregate pressure diagnostics (min over horizon)
        future_pressure_min = None
        pressure_k_star = None
        try:
            if "capacity_pressure" in df.columns and len(df) > 0:
                idx = int(df["capacity_pressure"].astype(float).idxmin())
                future_pressure_min = float(df.loc[idx, "capacity_pressure"])
                if "pressure_k_star" in df.columns:
                    # pressure_k_star may be float/NaN depending on writer
                    pk = df.loc[idx, "pressure_k_star"]
                    if pk is not None and pk == pk:
                        pressure_k_star = int(pk)
        except Exception:
            # keep None if any parsing fails
            future_pressure_min = None
            pressure_k_star = None

        df.to_csv(os.path.join(self.run_dir, "daily_stats.csv"), index=False)

        # failed_orders.csv (ALWAYS generate)
        df_fail = pd.DataFrame(self.failed_orders_log)
        if df_fail.empty:
            df_fail = pd.DataFrame(columns=["id", "scenario", "strategy", "fail_date", "deadline", "release_date", "reason"])
        df_fail.to_csv(os.path.join(self.run_dir, "failed_orders.csv"), index=False)

        summary_final = {
            "run_id": self.run_id,
            "scenario": self.scenario_name,
            "strategy": self.strategy_name,
            "base_dir": self.base_dir,
            "run_dir": self.run_dir,

            # Core metrics with explicit definitions
            "eligible_count": int(eligible_count),
            "delivered_within_window_count": int(delivered_count),
            "deadline_failure_count": int(failed_count),
            "service_rate_within_window": float(service_rate),

            # Cost metrics
            "penalized_cost": penalized_cost,
            "cost_raw": total_cost,
            "cost_per_order": cost_per_order,

            # Churn metrics
            "target_churn": avg_target_churn,
            "plan_churn": avg_plan_churn_effective,
            "plan_churn_raw": avg_plan_churn_raw,
            "load_mse": load_mse,

            # Legacy fields (for backward compatibility)
            "failed_orders": int(failed_count),
            "service_rate": service_rate,

            # Configuration
            "penalty_param": float(penalty_per_fail),
            "future_pressure_min": future_pressure_min,
            "pressure_k_star": pressure_k_star,

            # Metric definitions (for reproducibility)
            "metric_definitions": {
                "eligible_count": "Total unique orders released within simulation window (start_date to end_date)",
                "delivered_within_window_count": "Orders successfully delivered within simulation window",
                "deadline_failure_count": "Orders that reached their deadline day without being delivered",
                "service_rate_within_window": "delivered_within_window_count / eligible_count",
                "note": "Orders with deadlines beyond window end are NOT counted as failures"
            }
        }
        with open(os.path.join(self.run_dir, "summary_final.json"), "w", encoding="utf-8") as f:
            json.dump(summary_final, f, indent=2)

        return summary_final


# ==========================================
# Convenience wrapper for master_runner.py
# ==========================================
def run_rolling_horizon(config):
    """
    Wrapper function for master_runner.py compatibility.

    Args:
        config: dict with keys:
            - capacity_ratio: float
            - total_days: int
            - use_risk_model: bool
            - risk_model_path: str
            - risk_threshold_on: float
            - risk_threshold_off: float
            - seed: int
            - crunch_start: int (optional)
            - crunch_end: int (optional)
            - mode: str (optional) - 'greedy' or 'proactive' (default: 'proactive')

    Returns:
        dict: summary_final from RollingHorizonIntegrated.run()
    """
    from src.simulation.policies import ProactivePolicy, GreedyPolicy

    # Load data
    data_path = Path(_REPO_ROOT) / "data" / "processed" / "multiday_benchmark_herlev.json"
    with open(data_path, 'r') as f:
        data = json.load(f)

    # Build strategy config for ProactivePolicy
    strategy_config = {
        'capacity_ratio': config.get('capacity_ratio', 1.0),
        'total_days': config.get('total_days', 10),
        'use_risk_model': config.get('use_risk_model', False),
        'risk_model_path': config.get('risk_model_path', 'models/risk_model.joblib'),
        'risk_threshold_on': config.get('risk_threshold_on', 0.826),
        'risk_threshold_off': config.get('risk_threshold_off', 0.496),
        # Compute limits: single source of truth from experiment config
        'base_compute': config.get('base_compute', 60),
        'high_compute': config.get('high_compute', 60),
    }

    # Add crunch period if specified
    if 'crunch_start' in config:
        strategy_config['crunch_start'] = config['crunch_start']
        strategy_config['crunch_end'] = config['crunch_end']

    # Build capacity_profile from crunch parameters
    # Supports both single window (crunch_start/end) and multi-window (crunch_windows)
    capacity_profile = {}
    total_days = config.get('total_days', 12)
    crunch_start = config.get('crunch_start')
    crunch_end = config.get('crunch_end')
    crunch_windows = config.get('crunch_windows', [])
    crunch_ratio = config.get('capacity_ratio', 1.0)

    # Normalize: convert single window to list format for unified handling
    if not crunch_windows and crunch_start is not None and crunch_end is not None:
        crunch_windows = [(crunch_start, crunch_end)]

    for day_idx in range(total_days):
        if crunch_windows:
            # Check if day_idx falls within any crunch window
            in_crunch = any(start <= day_idx <= end for start, end in crunch_windows)
            capacity_profile[str(day_idx)] = crunch_ratio if in_crunch else 1.0
        else:
            # No crunch period: use capacity_ratio for all days (BAU scenario)
            capacity_profile[str(day_idx)] = crunch_ratio

    # Inject capacity_profile into data metadata
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["capacity_profile"] = capacity_profile

    # Determine policy mode (greedy vs proactive)
    mode = config.get('mode', 'proactive').lower()

    # Create policy based on mode
    if mode == 'greedy':
        strategy_config['mode'] = 'greedy'
        policy = GreedyPolicy(config=strategy_config)
        strategy_name = 'Greedy'
    else:
        strategy_config['mode'] = 'proactive_quota'
        policy = ProactivePolicy(config=strategy_config)
        strategy_name = 'ProactiveRisk' if config.get('use_risk_model') else 'Proactive'

    # Create simulator
    simulator = RollingHorizonIntegrated(
        data_source=data,
        strategy_config=strategy_config,
        seed=config.get('seed', 42),
        verbose=config.get('verbose', False),
        run_context={
            'scenario': config.get('scenario', 'DEFAULT'),
            'strategy': strategy_name
        },
        results_dir=config.get('results_dir', 'data/results'),
        run_id=config.get('run_id')
    )

    # Override end_date if total_days is specified
    if 'total_days' in config and config['total_days'] is not None:
        from datetime import timedelta
        simulator.end_date = simulator.start_date + timedelta(days=config['total_days'] - 1)

    # Set policy
    simulator.policy = policy

    # Run simulation
    summary = simulator.run_simulation()

    # Return both summary and daily_stats for master_runner compatibility
    return {
        'daily_stats': simulator.daily_stats,
        'vrp_audit_traces': simulator.vrp_audit_traces,
        'summary': summary,
        **summary  # Include all summary fields at top level for backward compatibility
    }
