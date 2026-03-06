#!/usr/bin/env python3
"""
Compute Allocator Module for EXP13: Bandit-Augmented Allocator (BAA).

This module provides three allocator classes:
1. BaseComputeAllocator - Abstract base class defining the interface
2. FittedQAllocator - Wrapper around EXP12's fitted-Q model
3. BanditAugmentedAllocator - Bandit layer on top of FittedQ with guardrails

Design principles:
- No global mutable state (all state in instance or run_dir)
- Deterministic given same seed + config + code version
- Full audit trail (all decisions logged)
- Parallel-safe (each run uses independent directories)

Usage:
    from compute_allocator import BanditAugmentedAllocator

    allocator = BanditAugmentedAllocator(
        q_model_path="path/to/model.joblib",
        run_dir="path/to/run_dir",
        seed=42,
        config={...}
    )

    action, debug = allocator.select_action(day_ctx)
    # ... run simulation day ...
    allocator.update(day_ctx, action, reward, debug)
"""

import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
import numpy as np

try:
    import joblib
except ImportError:
    joblib = None


# =============================================================================
# Constants
# =============================================================================

VALID_ACTIONS = [30, 60, 120, 300]
DEFAULT_LAMBDA = 0.05


# =============================================================================
# Data Classes for Configuration and Debug Info
# =============================================================================

@dataclass
class EpsilonSchedule:
    """Epsilon schedule for exploration."""
    kind: str = "piecewise"
    warmup_days: int = 2
    eps_start: float = 0.15
    eps_end: float = 0.03

    def get_epsilon(self, day_index: int) -> float:
        """Get epsilon value for given day index (0-based)."""
        if self.kind == "piecewise":
            if day_index < self.warmup_days:
                return self.eps_start
            else:
                return self.eps_end
        elif self.kind == "constant":
            return self.eps_start
        elif self.kind == "linear_decay":
            # Linear decay from eps_start to eps_end over warmup_days
            if day_index >= self.warmup_days:
                return self.eps_end
            progress = day_index / max(1, self.warmup_days)
            return self.eps_start + (self.eps_end - self.eps_start) * progress
        else:
            return self.eps_end


@dataclass
class GuardrailConfig:
    """Configuration for safety guardrails."""
    enabled: bool = True
    deadline_guard: bool = True      # mandatory_count > 0 OR due_today_count > 0 => action >= 60
    degradation_guard: bool = True   # prev_failures >= 1 OR prev_drop_rate >= 0.15 => action >= 120
    crunch_guard: bool = True        # capacity_ratio <= 0.65 OR capacity_pressure >= 0.35 => action in {120, 300}
    fail_safe_escalation: bool = True  # today_failures > 0 AND action < 300 => next day force 300


@dataclass
class AllocatorDebug:
    """Debug information for a single allocation decision."""
    day_index: int
    action_seconds: int
    original_action: int
    final_action: int
    qhat_30: float
    qhat_60: float
    qhat_120: float
    qhat_300: float
    policy: str
    epsilon: float
    propensity: float
    triggered_guards: List[str]
    exploration_triggered: bool
    fail_safe_active: bool = False
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AllocatorConfig:
    """Full allocator configuration for audit."""
    allocator_type: str
    actions: List[int]
    policy: str
    epsilon_schedule: Dict[str, Any]
    guardrails: Dict[str, bool]
    lambda_compute: float
    q_model_path: Optional[str]
    seed: int
    git_hash: Optional[str]
    run_uuid: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Base Allocator Class
# =============================================================================

class BaseComputeAllocator(ABC):
    """Abstract base class for compute allocators."""

    ACTIONS = VALID_ACTIONS

    def __init__(
        self,
        run_dir: Optional[Union[str, Path]] = None,
        seed: int = 0,
        config: Optional[Dict] = None
    ):
        """Initialize base allocator.

        Args:
            run_dir: Directory for this run's outputs (must be unique per run)
            seed: Random seed for reproducibility
            config: Additional configuration options
        """
        self.run_dir = Path(run_dir) if run_dir else None
        self.seed = seed
        self.config = config or {}
        self.rng = np.random.RandomState(seed)
        self.day_index = 0
        self.history: List[Dict] = []

    @abstractmethod
    def select_action(self, day_ctx: Dict[str, float]) -> Tuple[int, AllocatorDebug]:
        """Select compute budget action for the day.

        Args:
            day_ctx: Dictionary of day context features

        Returns:
            Tuple of (action_seconds, debug_info)
        """
        pass

    def update(
        self,
        day_ctx: Dict[str, float],
        action: int,
        reward: float,
        debug: AllocatorDebug
    ) -> None:
        """Update allocator after observing reward.

        Args:
            day_ctx: Day context features used for decision
            action: Action that was taken
            reward: Observed reward (reward_v2)
            debug: Debug info from select_action
        """
        record = {
            "day_index": self.day_index,
            "action": action,
            "reward": reward,
            "debug": debug.to_dict(),
            "ctx": day_ctx.copy()
        }
        self.history.append(record)
        self.day_index += 1

    def reset(self) -> None:
        """Reset allocator state for new episode."""
        self.rng = np.random.RandomState(self.seed)
        self.day_index = 0
        self.history = []

    def get_config_dump(self) -> Dict[str, Any]:
        """Return configuration for audit dump."""
        return {
            "allocator_type": self.__class__.__name__,
            "seed": self.seed,
            "config": self.config,
        }

    def save_config_dump(self, git_hash: Optional[str] = None) -> None:
        """Save configuration dump to run_dir."""
        if self.run_dir is None:
            return

        config_dump = self.get_config_dump()
        config_dump["git_hash"] = git_hash
        config_dump["created_at"] = datetime.now().isoformat()

        dump_path = self.run_dir / "allocator_config_dump.json"
        with open(dump_path, "w") as f:
            json.dump(config_dump, f, indent=2, default=str)


# =============================================================================
# Fitted-Q Allocator (EXP12 wrapper)
# =============================================================================

class FittedQAllocator(BaseComputeAllocator):
    """Fitted-Q allocator wrapping EXP12's learned model."""

    def __init__(
        self,
        q_model_path: Optional[Union[str, Path]] = None,
        run_dir: Optional[Union[str, Path]] = None,
        seed: int = 0,
        config: Optional[Dict] = None,
        fallback_action: int = 60
    ):
        """Initialize Fitted-Q allocator.

        Args:
            q_model_path: Path to trained Q-model (.joblib)
            run_dir: Directory for outputs
            seed: Random seed
            config: Additional config
            fallback_action: Action to use if model fails
        """
        super().__init__(run_dir=run_dir, seed=seed, config=config)

        self.q_model_path = Path(q_model_path) if q_model_path else None
        self.fallback_action = fallback_action
        self.q_models = None
        self.feature_cols = None
        self.lambda_compute = config.get("lambda_compute", DEFAULT_LAMBDA) if config else DEFAULT_LAMBDA
        self.model_loaded = False

        if self.q_model_path:
            self.load_model(self.q_model_path)

    def load_model(self, model_path: Union[str, Path]) -> bool:
        """Load Q-model from disk."""
        if joblib is None:
            print("Warning: joblib not available, cannot load model")
            return False

        try:
            self.q_model_path = Path(model_path)
            model_data = joblib.load(self.q_model_path)

            self.q_models = model_data["q_models"]
            self.feature_cols = model_data["feature_cols"]
            self.lambda_compute = model_data.get("lambda_compute", self.lambda_compute)
            self.model_loaded = True

            print(f"  Q-model loaded: {model_path} "
                  f"(n_features={len(self.feature_cols)}, "
                  f"feature_set={model_data.get('feature_set_name', 'full')})")

            return True
        except Exception as e:
            print(f"Error loading Q-model from {model_path}: {e}")
            self.model_loaded = False
            return False

    def score_actions(self, day_ctx: Dict[str, float]) -> Dict[int, float]:
        """Get Q-values for all actions given context.

        Args:
            day_ctx: Day context features

        Returns:
            Dictionary mapping action -> Q-value
        """
        if not self.model_loaded or self.q_models is None:
            return {a: 0.0 for a in self.ACTIONS}

        try:
            X = self._build_feature_vector(day_ctx)
            q_values = {}
            for action, model in self.q_models.items():
                q_values[int(action)] = float(model.predict(X.reshape(1, -1))[0])

            # Fill missing actions
            for action in self.ACTIONS:
                if action not in q_values:
                    q_values[action] = float('-inf')

            return q_values
        except Exception as e:
            print(f"Warning: score_actions failed ({e})")
            return {a: 0.0 for a in self.ACTIONS}

    def _build_feature_vector(self, features: Dict[str, float]) -> np.ndarray:
        """Build feature vector in correct order."""
        X = np.zeros(len(self.feature_cols))

        for i, col in enumerate(self.feature_cols):
            feat_name = col.replace("feat_", "")
            if col in features:
                X[i] = features[col]
            elif feat_name in features:
                X[i] = features[feat_name]
            else:
                X[i] = 0.0

        return X

    def select_action(self, day_ctx: Dict[str, float]) -> Tuple[int, AllocatorDebug]:
        """Select action using argmax Q-value."""
        q_values = self.score_actions(day_ctx)

        if self.model_loaded:
            best_action = max(q_values, key=q_values.get)
            fallback_reason = None
        else:
            best_action = self.fallback_action
            fallback_reason = "model_not_loaded"

        # Validate action
        if best_action not in self.ACTIONS:
            fallback_reason = f"invalid_action_{best_action}"
            best_action = self.fallback_action

        debug = AllocatorDebug(
            day_index=self.day_index,
            action_seconds=best_action,
            original_action=best_action,
            final_action=best_action,
            qhat_30=q_values.get(30, 0.0),
            qhat_60=q_values.get(60, 0.0),
            qhat_120=q_values.get(120, 0.0),
            qhat_300=q_values.get(300, 0.0),
            policy="fitted_q",
            epsilon=0.0,
            propensity=1.0,
            triggered_guards=[],
            exploration_triggered=False,
            fallback_reason=fallback_reason
        )

        return best_action, debug

    def get_config_dump(self) -> Dict[str, Any]:
        config = super().get_config_dump()
        config.update({
            "q_model_path": str(self.q_model_path) if self.q_model_path else None,
            "lambda_compute": self.lambda_compute,
            "fallback_action": self.fallback_action,
            "model_loaded": self.model_loaded,
            "feature_cols": self.feature_cols,
        })
        return config


# =============================================================================
# Bandit-Augmented Allocator (EXP13)
# =============================================================================

class BanditAugmentedAllocator(BaseComputeAllocator):
    """Bandit-augmented allocator with Q-model prior and guardrails."""

    def __init__(
        self,
        q_model_path: Optional[Union[str, Path]] = None,
        run_dir: Optional[Union[str, Path]] = None,
        seed: int = 0,
        config: Optional[Dict] = None
    ):
        """Initialize Bandit-Augmented allocator.

        Args:
            q_model_path: Path to trained Q-model for warm-start
            run_dir: Directory for outputs (must be unique per run)
            seed: Random seed for reproducibility
            config: Configuration dict with keys:
                - policy: "epsilon_greedy" or "thompson" (default: epsilon_greedy)
                - epsilon_schedule: dict for EpsilonSchedule
                - guardrails: dict for GuardrailConfig
                - lambda_compute: float (default: 0.05)
        """
        super().__init__(run_dir=run_dir, seed=seed, config=config)

        # Initialize Q-model (warm-start prior)
        self.fitted_q = FittedQAllocator(
            q_model_path=q_model_path,
            run_dir=run_dir,
            seed=seed,
            config=config
        )

        # Policy configuration
        self.policy = config.get("policy", "epsilon_greedy") if config else "epsilon_greedy"

        # Epsilon schedule
        eps_config = config.get("epsilon_schedule", {}) if config else {}
        self.epsilon_schedule = EpsilonSchedule(
            kind=eps_config.get("kind", "piecewise"),
            warmup_days=eps_config.get("warmup_days", 2),
            eps_start=eps_config.get("eps_start", 0.15),
            eps_end=eps_config.get("eps_end", 0.03)
        )

        # Guardrails configuration
        guard_config = config.get("guardrails", {}) if config else {}
        self.guardrails = GuardrailConfig(
            enabled=guard_config.get("enabled", True),
            deadline_guard=guard_config.get("deadline_guard", True),
            degradation_guard=guard_config.get("degradation_guard", True),
            crunch_guard=guard_config.get("crunch_guard", True),
            fail_safe_escalation=guard_config.get("fail_safe_escalation", True)
        )

        # Lambda for reward computation
        self.lambda_compute = config.get("lambda_compute", DEFAULT_LAMBDA) if config else DEFAULT_LAMBDA

        # Fail-safe state (for fail_safe_escalation guard)
        self.fail_safe_active = False
        self.fail_safe_triggered_day = -1

        # Run UUID for audit
        self.run_uuid = str(uuid.uuid4())[:8]

    def select_action(self, day_ctx: Dict[str, float]) -> Tuple[int, AllocatorDebug]:
        """Select action using epsilon-greedy with Q-model prior and guardrails.

        Decision flow:
        1. Get Q-values from fitted-Q model
        2. Apply epsilon-greedy exploration
        3. Apply guardrails to ensure safety
        4. Return final action with full debug info
        """
        # Step 1: Get Q-values from fitted-Q model
        q_values = self.fitted_q.score_actions(day_ctx)

        # Step 2: Epsilon-greedy action selection
        epsilon = self.epsilon_schedule.get_epsilon(self.day_index)
        exploration_triggered = False

        if self.policy == "epsilon_greedy":
            if self.rng.random() < epsilon:
                # Explore: random action
                original_action = int(self.rng.choice(self.ACTIONS))
                exploration_triggered = True
                # Propensity = epsilon / |A| for explored action
                propensity = epsilon / len(self.ACTIONS)
            else:
                # Exploit: argmax Q
                original_action = max(q_values, key=q_values.get)
                # Propensity = (1 - epsilon) + epsilon/|A| for greedy action
                propensity = (1 - epsilon) + epsilon / len(self.ACTIONS)
        else:
            # Default to greedy if unknown policy
            original_action = max(q_values, key=q_values.get)
            propensity = 1.0

        # Validate original action
        if original_action not in self.ACTIONS:
            original_action = 60  # Safe default

        # Step 3: Apply guardrails
        final_action = original_action
        triggered_guards = []

        if self.guardrails.enabled:
            final_action, triggered_guards = self._apply_guardrails(
                original_action, day_ctx, q_values
            )

        # Check fail-safe from previous day
        fail_safe_active = False
        if self.fail_safe_active and self.day_index == self.fail_safe_triggered_day + 1:
            if final_action < 300:
                final_action = 300
                triggered_guards.append("fail_safe_escalation")
                fail_safe_active = True
            self.fail_safe_active = False  # Reset after one day

        # Build debug info
        debug = AllocatorDebug(
            day_index=self.day_index,
            action_seconds=final_action,
            original_action=original_action,
            final_action=final_action,
            qhat_30=q_values.get(30, 0.0),
            qhat_60=q_values.get(60, 0.0),
            qhat_120=q_values.get(120, 0.0),
            qhat_300=q_values.get(300, 0.0),
            policy=self.policy,
            epsilon=epsilon,
            propensity=propensity,
            triggered_guards=triggered_guards,
            exploration_triggered=exploration_triggered,
            fail_safe_active=fail_safe_active
        )

        return final_action, debug

    def _apply_guardrails(
        self,
        action: int,
        day_ctx: Dict[str, float],
        q_values: Dict[int, float]
    ) -> Tuple[int, List[str]]:
        """Apply safety guardrails to action.

        Guardrails (in order of application):
        1. deadline_guard: mandatory_count > 0 OR due_today_count > 0 => action >= 60
        2. degradation_guard: prev_failures >= 1 OR prev_drop_rate >= 0.15 => action >= 120
        3. crunch_guard: capacity_ratio <= 0.65 OR capacity_pressure >= 0.35 => action in {120, 300}

        Returns:
            Tuple of (final_action, list of triggered guard names)
        """
        triggered = []
        final_action = action

        # Extract context values with defaults
        mandatory_count = day_ctx.get("mandatory_count", 0)
        due_today_count = day_ctx.get("due_today_count", 0)
        prev_failures = day_ctx.get("prev_failures", 0)
        prev_drop_rate = day_ctx.get("prev_drop_rate", 0)
        capacity_ratio = day_ctx.get("capacity_ratio", 1.0)
        capacity_pressure = day_ctx.get("capacity_pressure", 0)

        # Guard 1: Deadline guard
        if self.guardrails.deadline_guard:
            if mandatory_count > 0 or due_today_count > 0:
                if final_action < 60:
                    final_action = 60
                    triggered.append("deadline_guard")

        # Guard 2: Degradation guard
        if self.guardrails.degradation_guard:
            if prev_failures >= 1 or prev_drop_rate >= 0.15:
                if final_action < 120:
                    final_action = 120
                    triggered.append("degradation_guard")

        # Guard 3: Crunch guard
        if self.guardrails.crunch_guard:
            if capacity_ratio <= 0.65 or capacity_pressure >= 0.35:
                if final_action < 120:
                    # Choose between 120 and 300 based on Q-values
                    q_120 = q_values.get(120, 0)
                    q_300 = q_values.get(300, 0)
                    final_action = 300 if q_300 > q_120 else 120
                    triggered.append("crunch_guard")

        return final_action, triggered

    def update(
        self,
        day_ctx: Dict[str, float],
        action: int,
        reward: float,
        debug: AllocatorDebug,
        today_failures: int = 0
    ) -> None:
        """Update allocator after observing reward.

        Also handles fail_safe_escalation trigger for next day.
        """
        # Check fail-safe escalation trigger
        if self.guardrails.enabled and self.guardrails.fail_safe_escalation:
            if today_failures > 0 and action < 300:
                self.fail_safe_active = True
                self.fail_safe_triggered_day = self.day_index

        # Call parent update
        super().update(day_ctx, action, reward, debug)

    def reset(self) -> None:
        """Reset allocator state for new episode."""
        super().reset()
        self.fail_safe_active = False
        self.fail_safe_triggered_day = -1
        self.fitted_q.reset()

    def get_config_dump(self) -> Dict[str, Any]:
        """Return full configuration for audit."""
        config = AllocatorConfig(
            allocator_type=self.__class__.__name__,
            actions=self.ACTIONS,
            policy=self.policy,
            epsilon_schedule=asdict(self.epsilon_schedule),
            guardrails=asdict(self.guardrails),
            lambda_compute=self.lambda_compute,
            q_model_path=str(self.fitted_q.q_model_path) if self.fitted_q.q_model_path else None,
            seed=self.seed,
            git_hash=None,  # Will be filled by save_config_dump
            run_uuid=self.run_uuid,
            created_at=datetime.now().isoformat()
        )
        d = config.to_dict()
        d["feature_cols"] = self.fitted_q.feature_cols
        d["n_features"] = len(self.fitted_q.feature_cols) if self.fitted_q.feature_cols else None
        return d


# =============================================================================
# EXP14: Sparse Fail-Safe Bandit (SFB)
# =============================================================================

# One-step escalation mapping
ESCALATION_MAP = {30: 60, 60: 120, 120: 300, 300: 300}


@dataclass
class FailSafeConfig:
    """Configuration for EXP14 Sparse Fail-Safe."""
    enabled: bool = True
    # Degradation thresholds
    prev_failures_ge: int = 1
    prev_drop_rate_ge: float = 0.25
    prev_vrp_dropped_ge: int = 10
    # Deadline cliff thresholds
    mandatory_count_ge: int = 80
    mandatory_ratio_ge: float = 0.20
    # Consecutive bad days
    consecutive_bad_days_ge: int = 2


@dataclass
class FailSafeDebug:
    """Debug info for fail-safe decision."""
    fired: bool
    reason: str
    reason_list: List[str]
    action_raw: int
    action_final: int
    delta_seconds: int
    trigger_inputs: Dict[str, Any]


class SparseFailSafeBandit(BanditAugmentedAllocator):
    """EXP14: Sparse Fail-Safe Bandit allocator.

    Extends BanditAugmentedAllocator with sparse fail-safe logic:
    - Only escalates when degradation is observed
    - One-step escalation per day (30->60->120->300)
    - No crunch_guard (bandit handles crunch prediction)
    """

    def __init__(
        self,
        q_model_path: Optional[Union[str, Path]] = None,
        run_dir: Optional[Union[str, Path]] = None,
        seed: int = 0,
        config: Optional[Dict] = None
    ):
        # Disable old guardrails, use sparse fail-safe instead
        if config is None:
            config = {}
        config["guardrails"] = {"enabled": False}

        super().__init__(
            q_model_path=q_model_path,
            run_dir=run_dir,
            seed=seed,
            config=config
        )

        # Fail-safe configuration
        fs_config = config.get("fail_safe", {})
        self.fail_safe = FailSafeConfig(
            enabled=fs_config.get("enabled", True),
            prev_failures_ge=fs_config.get("prev_failures_ge", 1),
            prev_drop_rate_ge=fs_config.get("prev_drop_rate_ge", 0.25),
            prev_vrp_dropped_ge=fs_config.get("prev_vrp_dropped_ge", 10),
            mandatory_count_ge=fs_config.get("mandatory_count_ge", 80),
            mandatory_ratio_ge=fs_config.get("mandatory_ratio_ge", 0.20),
            consecutive_bad_days_ge=fs_config.get("consecutive_bad_days_ge", 2),
        )

        # Track consecutive bad days
        self.consecutive_bad_days = 0
        self.last_fail_safe_debug: Optional[FailSafeDebug] = None

    def select_action(self, day_ctx: Dict[str, float]) -> Tuple[int, AllocatorDebug]:
        """Select action with sparse fail-safe."""
        # Get bandit action (no guardrails)
        action_raw, debug = super().select_action(day_ctx)

        # Apply sparse fail-safe
        if self.fail_safe.enabled:
            fs_debug = self._apply_fail_safe(action_raw, day_ctx)
            self.last_fail_safe_debug = fs_debug
            action_final = fs_debug.action_final

            # Update debug info
            debug.final_action = action_final
            debug.action_seconds = action_final
            if fs_debug.fired:
                debug.triggered_guards = [fs_debug.reason]
        else:
            action_final = action_raw
            self.last_fail_safe_debug = FailSafeDebug(
                fired=False, reason="none", reason_list=[],
                action_raw=action_raw, action_final=action_raw,
                delta_seconds=0, trigger_inputs={}
            )

        return action_final, debug

    def _apply_fail_safe(self, action_raw: int, day_ctx: Dict[str, float]) -> FailSafeDebug:
        """Apply sparse fail-safe logic."""
        reasons = []
        trigger_inputs = {
            "prev_failures": day_ctx.get("prev_failures", 0),
            "prev_drop_rate": day_ctx.get("prev_drop_rate", 0),
            "prev_vrp_dropped": day_ctx.get("vrp_dropped_lag1", 0),
            "mandatory_count": day_ctx.get("mandatory_count", 0),
            "visible_open_orders": day_ctx.get("visible_open_orders", 1),
            "consecutive_bad_days": self.consecutive_bad_days,
        }

        prev_failures = trigger_inputs["prev_failures"]
        prev_drop_rate = trigger_inputs["prev_drop_rate"]
        prev_vrp_dropped = trigger_inputs["prev_vrp_dropped"]
        mandatory_count = trigger_inputs["mandatory_count"]
        visible = max(1, trigger_inputs["visible_open_orders"])
        mandatory_ratio = mandatory_count / visible

        # Check degradation conditions
        if prev_failures >= self.fail_safe.prev_failures_ge:
            reasons.append("degradation_prev_failures")
        if prev_drop_rate >= self.fail_safe.prev_drop_rate_ge:
            reasons.append("degradation_prev_drop_rate")
        if prev_vrp_dropped >= self.fail_safe.prev_vrp_dropped_ge:
            reasons.append("degradation_prev_vrp_dropped")

        # Check deadline cliff
        if mandatory_count >= self.fail_safe.mandatory_count_ge:
            reasons.append("deadline_cliff_mandatory_count")
        if mandatory_ratio >= self.fail_safe.mandatory_ratio_ge:
            reasons.append("deadline_cliff_mandatory_ratio")

        # Check consecutive bad days
        if self.consecutive_bad_days >= self.fail_safe.consecutive_bad_days_ge:
            reasons.append("consecutive_bad_days")

        # Determine if fired and escalate
        fired = len(reasons) > 0
        if fired:
            action_final = ESCALATION_MAP.get(action_raw, action_raw)
            reason = reasons[0]  # Top priority
        else:
            action_final = action_raw
            reason = "none"

        return FailSafeDebug(
            fired=fired,
            reason=reason,
            reason_list=reasons,
            action_raw=action_raw,
            action_final=action_final,
            delta_seconds=action_final - action_raw,
            trigger_inputs=trigger_inputs
        )

    def update(
        self,
        day_ctx: Dict[str, float],
        action: int,
        reward: float,
        debug: AllocatorDebug,
        today_failures: int = 0,
        today_vrp_dropped: int = 0,
        today_drop_rate: float = 0.0
    ) -> None:
        """Update allocator and track consecutive bad days."""
        # Update consecutive bad days counter
        is_bad_day = (
            today_failures >= self.fail_safe.prev_failures_ge or
            today_drop_rate >= self.fail_safe.prev_drop_rate_ge
        )
        if is_bad_day:
            self.consecutive_bad_days += 1
        else:
            self.consecutive_bad_days = 0

        super().update(day_ctx, action, reward, debug, today_failures)

    def reset(self) -> None:
        """Reset allocator state."""
        super().reset()
        self.consecutive_bad_days = 0
        self.last_fail_safe_debug = None

    def get_config_dump(self) -> Dict[str, Any]:
        """Return config with fail-safe settings."""
        config = super().get_config_dump()
        config["fail_safe"] = asdict(self.fail_safe)
        config["allocator_type"] = "SparseFailSafeBandit"
        return config


# =============================================================================
# Reward Computation
# =============================================================================

def compute_reward_v2(
    failures: int,
    vrp_dropped: int,
    action_seconds: int,
    lambda_compute: float = DEFAULT_LAMBDA
) -> float:
    """Compute reward_v2 for allocator update.

    Formula: reward = -failures - 0.1 * vrp_dropped - lambda * (action_seconds / 60)

    Args:
        failures: Number of delivery failures today
        vrp_dropped: Number of orders dropped by VRP solver
        action_seconds: Compute budget used (30, 60, 120, or 300)
        lambda_compute: Weight for compute cost (default: 0.05)

    Returns:
        Reward value (higher is better, but typically negative)
    """
    return -failures - 0.1 * vrp_dropped - lambda_compute * (action_seconds / 60)


# =============================================================================
# Factory Function
# =============================================================================

def create_allocator(
    allocator_type: str,
    q_model_path: Optional[Union[str, Path]] = None,
    run_dir: Optional[Union[str, Path]] = None,
    seed: int = 0,
    config: Optional[Dict] = None
) -> BaseComputeAllocator:
    """Factory function to create allocator by type.

    Args:
        allocator_type: One of "fitted_q", "bandit_augmented", "exp12", "exp13"
        q_model_path: Path to Q-model
        run_dir: Output directory
        seed: Random seed
        config: Configuration dict

    Returns:
        Allocator instance
    """
    allocator_type = allocator_type.lower()

    if allocator_type in ("fitted_q", "exp12", "fittedq"):
        return FittedQAllocator(
            q_model_path=q_model_path,
            run_dir=run_dir,
            seed=seed,
            config=config
        )
    elif allocator_type in ("bandit_augmented", "exp13", "baa"):
        return BanditAugmentedAllocator(
            q_model_path=q_model_path,
            run_dir=run_dir,
            seed=seed,
            config=config
        )
    elif allocator_type in ("sparse_fail_safe", "exp14", "sfb"):
        return SparseFailSafeBandit(
            q_model_path=q_model_path,
            run_dir=run_dir,
            seed=seed,
            config=config
        )
    else:
        raise ValueError(f"Unknown allocator type: {allocator_type}")


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test compute allocator")
    parser.add_argument("--model_path", type=str, help="Path to Q-model")
    parser.add_argument("--allocator", type=str, default="bandit_augmented",
                        choices=["fitted_q", "bandit_augmented"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test", action="store_true", help="Run test scenario")
    args = parser.parse_args()

    # Create allocator
    config = {
        "policy": "epsilon_greedy",
        "epsilon_schedule": {"warmup_days": 2, "eps_start": 0.15, "eps_end": 0.03},
        "guardrails": {"enabled": True},
        "lambda_compute": 0.05
    }

    allocator = create_allocator(
        allocator_type=args.allocator,
        q_model_path=args.model_path,
        seed=args.seed,
        config=config
    )

    if args.test:
        # Test with sample context
        test_ctx = {
            "capacity_ratio": 0.59,
            "capacity_pressure": 0.40,
            "pressure_k_star": 3.0,
            "visible_open_orders": 400.0,
            "mandatory_count": 10.0,
            "prev_drop_rate": 0.05,
            "prev_failures": 2.0,
            "due_today_count": 5.0,
        }

        print(f"\nAllocator: {allocator.__class__.__name__}")
        print(f"Seed: {args.seed}")
        print("\nTest context:")
        for k, v in test_ctx.items():
            print(f"  {k}: {v}")

        # Run 5 days
        print("\nSimulating 5 days:")
        for day in range(5):
            action, debug = allocator.select_action(test_ctx)
            reward = compute_reward_v2(
                failures=1 if day == 2 else 0,
                vrp_dropped=2,
                action_seconds=action
            )

            print(f"\nDay {day}:")
            print(f"  Action: {action}s (original: {debug.original_action}s)")
            print(f"  Epsilon: {debug.epsilon:.3f}")
            print(f"  Propensity: {debug.propensity:.3f}")
            print(f"  Exploration: {debug.exploration_triggered}")
            print(f"  Guards: {debug.triggered_guards}")
            print(f"  Q-values: 30={debug.qhat_30:.2f}, 60={debug.qhat_60:.2f}, "
                  f"120={debug.qhat_120:.2f}, 300={debug.qhat_300:.2f}")
            print(f"  Reward: {reward:.3f}")

            allocator.update(
                test_ctx, action, reward, debug,
                today_failures=1 if day == 2 else 0
            )

        print("\n\nConfig dump:")
        print(json.dumps(allocator.get_config_dump(), indent=2))
