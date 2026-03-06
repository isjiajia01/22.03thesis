"""
RiskGate: risk-model wrapper and hysteresis controller.

IMPORTANT (do not remove or bypass):
------------------------------------

The `RiskModelPredictor` in this module is **the only supported way**
to call the pre-trained risk model in production code.  It implements
two critical pieces of **defensive inference logic**:

1. **Feature-order alignment via `feature_names_in_`**
   - At inference time, feature dictionaries are first converted into a
     single-row `pandas.DataFrame`, and **columns are ordered strictly
     according to `model.feature_names_in_`** (if present).
   - If the model does not carry `feature_names_in_`, we fall back to
     a _hard-coded_ 7-dimensional order that must be kept in sync with
     the training script:
       ["capacity_ratio", "capacity_pressure", "pressure_k_star",
        "visible_open_orders", "mandatory_count",
        "prev_drop_rate", "prev_failures"]
   - **Rationale**: the underlying sklearn model only "sees" column
     positions, not semantic names.  Any change to the order of the
     input vector will silently flip semantics (e.g. treating
     `prev_failures` as `capacity_ratio`), which in turn creates
     catastrophic but hard-to-detect logical inversions
     (e.g. low risk during overload and high risk during calm days).
   - **Instruction**: it is **forbidden** to replace this logic with
     `dict.values()`, manual lists, or any other ad-hoc ordering.
     Future contributors must keep this alignment step intact.

2. **Dynamic positive-class indexing via `classes_`**
   - We **never** assume that the "positive" (high-risk) class is at
     fixed index 1 in `predict_proba` output.
   - Instead, we dynamically locate the index of label `1` via
     `pos_idx = list(model.classes_).index(1)` and extract
     `probs[0, pos_idx]`.
   - If `classes_` is unavailable or does not contain `1`, we fall
     back to "last column is positive" (multi-class) or `0` (binary).
   - **Rationale**: sklearn may order classes as `[0, 1]` or `[1, 0]`
     depending on how the estimator was fit.  Hard-coding `[:, 1]`
     makes the sign of the probability dependent on internal ordering,
     which will eventually break when the model is retrained.

Together, these two guarantees make it **much harder** for future
model updates to silently invert the meaning of `risk_p`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


class RiskModelLoadError(Exception):
    """Raised when risk model fails to load and use_risk_model=True."""
    pass


class RiskModelPredictor:
    """
    Wrapper around a pre-trained sklearn Pipeline (StandardScaler +
    LogisticRegression) stored in a `risk_model.joblib`.

    Key properties:
    - Lazy loading: the underlying model is only loaded on first use.
    - FAIL-FAST: When fail_on_error=True (default for use_risk_model=True),
      any load failure raises RiskModelLoadError instead of silently
      returning 0.0 (which would pollute experimental results).
    - Defensive feature alignment:
        * Uses `model.feature_names_in_` when available.
        * Otherwise falls back to the canonical 7-D schema documented
          in the module-level docstring.
    - Defensive class indexing:
        * Uses `model.classes_` to locate the positive (high-risk)
          class `1`, instead of hard-coding `[:, 1]`.
    - Diagnostics:
        * Exposes `_last_logit` (raw decision function) for logging.
        * Prints detailed information when features mismatch expected
          schema or when probabilities are suspiciously zero on
          non-zero inputs.
    """

    def __init__(self, model_path: Optional[str] = None, fail_on_error: bool = False) -> None:
        self.model_path = model_path
        self.fail_on_error = fail_on_error  # When True, raise instead of returning 0.0
        self._model: Any = None  # lazy load
        self._load_attempted: bool = False
        self._load_error: Optional[str] = None
        self._last_logit: Optional[float] = None
        self.model_loaded: bool = False  # Exposed for validation

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _load_model(self):
        if self._model is None and not self._load_attempted:
            self._load_attempted = True
            if self.model_path is None:
                err_msg = "model_path is None"
                print(f"🔥 [RiskModelPredictor] ERROR: {err_msg}!")
                self._load_error = err_msg
                self.model_loaded = False
                if self.fail_on_error:
                    raise RiskModelLoadError(f"Risk model load failed: {err_msg}")
                return None

            # Resolve relative paths against plausible repo roots
            if not os.path.isabs(self.model_path):
                possible_roots = [
                    Path(__file__).resolve().parents[2],  # repo_root (contains src/)
                    Path.cwd(),
                ]
                for root in possible_roots:
                    candidate = root / self.model_path
                    if candidate.exists():
                        self.model_path = str(candidate.resolve())
                        break

            if not os.path.exists(self.model_path):
                err_msg = f"File not found: {self.model_path}"
                print(f"🔥 [RiskModelPredictor] ERROR: Model file does not exist: {self.model_path}")
                print(f"🔥 [RiskModelPredictor] Current working directory: {os.getcwd()}")
                print(f"🔥 [RiskModelPredictor] Absolute path attempted: {os.path.abspath(self.model_path)}")
                self._load_error = err_msg
                self.model_loaded = False
                if self.fail_on_error:
                    raise RiskModelLoadError(f"Risk model load failed: {err_msg}")
                return None

            try:
                import joblib

                print(f"[RiskModelPredictor] Loading model from: {self.model_path}")
                self._model = joblib.load(self.model_path)
                print(f"[RiskModelPredictor] ✅ Model loaded successfully. Type: {type(self._model)}")
                if hasattr(self._model, "named_steps"):
                    print(f"[RiskModelPredictor] Model is Pipeline with steps: "
                          f"{list(self._model.named_steps.keys())}")
                self._load_error = None
                self.model_loaded = True
            except Exception as e:
                err_msg = str(e)
                print(f"🔥 [RiskModelPredictor] Failed to load model from {self.model_path}: {e}")
                import traceback
                traceback.print_exc()
                self._model = None
                self._load_error = err_msg
                self.model_loaded = False
                if self.fail_on_error:
                    raise RiskModelLoadError(f"Risk model load failed: {err_msg}")
        elif self._model is None and self._load_attempted:
            # already tried and failed; nothing more to do here
            pass
        return self._model

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def predict_proba(self, feats: Dict[str, Any], feats_array=None, debug_day: int = None) -> float:
        """
        Predict HIGH_RISK probability given a feature dict.

        CRITICAL CONTRACT (do not weaken):
        ----------------------------------
        - This method **must**:
          1) Align features by column name using `feature_names_in_`
             when present.
          2) Fall back to the canonical 7-D order otherwise.
          3) Use `model.classes_` to locate the positive-class index.
        - Do **not**:
          - Change this to rely on `dict.values()` ordering.
          - Manually build positional lists without a schema.
          - Hard-code `proba[:, 1]` without checking `classes_`.

        Args:
            feats: Feature dictionary
            feats_array: Unused (legacy parameter)
            debug_day: If provided, print detailed debug info for this day
        """
        model = self._load_model()
        if model is None:
            # CRITICAL: Never return 0.0 when model fails - this pollutes results
            # by making failed loads look like "low risk"
            if self.fail_on_error:
                raise RiskModelLoadError(
                    f"Risk model not loaded, cannot predict. "
                    f"Load error: {self._load_error}"
                )
            # Return NaN to indicate invalid prediction (not low risk!)
            if not hasattr(self, "_warned_predict_proba"):
                print("🔥 [RiskModelPredictor.predict_proba] Model is None! Returning NaN (not 0.0)")
                print(f"🔥 [RiskModelPredictor.predict_proba] Load error: {getattr(self, '_load_error', 'Unknown')}")
                print(f"🔥 [RiskModelPredictor.predict_proba] Model path: {self.model_path}")
                self._warned_predict_proba = True
            return float('nan')

        try:
            import numpy as np
            import pandas as pd

            # 1) Decide feature ordering
            if hasattr(model, "feature_names_in_"):
                expected_features = list(model.feature_names_in_)
            else:
                expected_features = [
                    "capacity_ratio",
                    "capacity_pressure",
                    "pressure_k_star",
                    "visible_open_orders",
                    "mandatory_count",
                    "prev_drop_rate",
                    "prev_failures",
                ]

            # 2) Construct single-row DataFrame with strict column order
            received_features = list(feats.keys()) if isinstance(feats, dict) else []
            missing = [f for f in expected_features if f not in feats]
            extra = [f for f in received_features if f not in expected_features]
            if missing or extra:
                print("⚠️ [RiskModelPredictor.predict_proba] Feature mismatch detected!")
                print(f"  - expected_features: {expected_features}")
                print(f"  - received_features: {received_features}")
                print(f"  - missing (treated as 0.0): {missing}")
                print(f"  - extra (ignored for ordering): {extra}")

            row = {f: feats.get(f, 0.0) for f in expected_features}
            X_df = pd.DataFrame([row])[expected_features]

            # 3) Predict probability matrix
            probs = model.predict_proba(X_df)

            # 4) Locate positive class index dynamically
            try:
                classes = list(model.classes_)
                pos_idx = classes.index(1)
            except Exception:
                pos_idx = probs.shape[1] - 1 if probs.shape[1] > 1 else 0

            risk_p = float(probs[0, pos_idx])

            # 5) DEBUG OUTPUT for specified days
            if debug_day is not None:
                print(f"\n{'='*70}")
                print(f"🔍 RISK MODEL DEBUG - Day {debug_day}")
                print(f"{'='*70}")
                print(f"Model class: {model.__class__.__name__}")
                print(f"Model type: {type(model)}")
                print(f"\nFeature values (ordered):")
                for i, feat_name in enumerate(expected_features):
                    print(f"  [{i}] {feat_name:20s} = {row[feat_name]}")
                print(f"\nModel outputs:")
                print(f"  predict_proba(X)[0]: {probs[0]}")
                print(f"  classes_: {getattr(model, 'classes_', 'N/A')}")
                print(f"  pos_idx: {pos_idx}")
                print(f"  risk_p (final): {risk_p}")

                # Try to get decision_function if available
                if hasattr(model, "decision_function"):
                    try:
                        logits = model.decision_function(X_df)
                        print(f"  decision_function(X): {logits[0]}")
                    except Exception as e:
                        print(f"  decision_function: Error - {e}")

                # Try to get predict (hard classification)
                if hasattr(model, "predict"):
                    try:
                        pred = model.predict(X_df)
                        print(f"  predict(X): {pred[0]}")
                    except Exception as e:
                        print(f"  predict: Error - {e}")

                print(f"{'='*70}\n")

            if risk_p == 0.0 and np.any(X_df.values != 0):
                print("⚠️ [RiskModelPredictor.predict_proba] WARNING: risk_p=0.0 for non-zero features!")
                print(f"  - expected_features: {expected_features}")
                print(f"  - X_df.values: {X_df.values}")
                print(f"  - classes_: {getattr(model, 'classes_', None)}")
                print(f"  - model type: {type(model)}")

            # 6) Capture logit for diagnostics (if supported)
            if hasattr(model, "decision_function"):
                try:
                    logits = model.decision_function(X_df)
                    logit_val = float(np.ravel(logits)[0])
                    self._last_logit = logit_val
                except Exception:
                    self._last_logit = None

            return risk_p
        except Exception as e:
            print(f"🔥 Risk Prediction Error: {str(e)}")
            print(f"🔥 Feature dict: {feats}")
            if feats_array is not None:
                print(f"🔥 Feature array: {feats_array}")
            import traceback

            traceback.print_exc()
            raise e

    def decision_function(self, feats: Dict[str, Any], feats_array=None) -> float:
        """
        Get the raw logit score (before sigmoid) for diagnostic purposes.
        Returns the decision function value from the underlying model.
        """
        model = self._load_model()
        if model is None:
            if self.fail_on_error:
                raise RiskModelLoadError(
                    f"Risk model not loaded, cannot compute decision function. "
                    f"Load error: {self._load_error}"
                )
            if not hasattr(self, "_warned_decision_function"):
                print("🔥 [RiskModelPredictor.decision_function] Model is None! Returning NaN")
                print(f"🔥 [RiskModelPredictor.decision_function] Load error: {getattr(self, '_load_error', 'Unknown')}")
                print(f"🔥 [RiskModelPredictor.decision_function] Model path: {self.model_path}")
                self._warned_decision_function = True
            return float('nan')

        try:
            import numpy as np

            if feats_array is not None:
                X = feats_array
            else:
                # Conservative fallback: keep 7-D schema in the same order
                X = np.array([[
                    feats.get("capacity_ratio", 0.0),
                    feats.get("capacity_pressure", 0.0),
                    feats.get("pressure_k_star", 0.0),
                    feats.get("visible_open_orders", 0.0),
                    feats.get("mandatory_count", 0.0),
                    feats.get("prev_drop_rate", 0.0),
                    feats.get("prev_failures", 0.0),
                ]])

            if hasattr(model, "named_steps"):
                scaler = model.named_steps.get("scaler")
                lr = model.named_steps.get("lr")
                if scaler is not None and lr is not None:
                    X_scaled = scaler.transform(X)
                    logit = lr.decision_function(X_scaled)[0]
                    return float(logit)
                if hasattr(model, "decision_function"):
                    return float(model.decision_function(X)[0])
            elif hasattr(model, "decision_function"):
                return float(model.decision_function(X)[0])

            return float("nan")
        except Exception as e:
            print(f"🔥 Risk Decision Function Error: {str(e)}")
            return float("nan")


class RiskGatingController:
    """
    Hysteresis-based gate controller.

    - Enter HIGH_RISK if p >= delta_on (default 0.826)
    - Exit HIGH_RISK if p <= delta_off (default 0.496)
      for `exit_days` consecutive days (default 2).
    """

    def __init__(self, delta_on: float = 0.826, delta_off: float = 0.496, exit_days: int = 2) -> None:
        self.delta_on = delta_on
        self.delta_off = delta_off
        self.exit_days = exit_days

        self.active: bool = False
        self._consecutive_below_off: int = 0

    def update_state(self, p: float) -> bool:
        """
        Update the gate state given new probability `p`.
        Returns True if HIGH_RISK mode is active after this update.

        IMPORTANT: If p is NaN (model load failed), state is NOT updated.
        This prevents invalid predictions from affecting the gate.
        """
        import math

        # Do NOT update state if p is NaN (invalid prediction)
        if p is None or (isinstance(p, float) and math.isnan(p)):
            # Return current state without modification
            return self.active

        if not self.active:
            if p >= self.delta_on:
                self.active = True
                self._consecutive_below_off = 0
        else:
            if p <= self.delta_off:
                self._consecutive_below_off += 1
                if self._consecutive_below_off >= self.exit_days:
                    self.active = False
                    self._consecutive_below_off = 0
            else:
                self._consecutive_below_off = 0
        return self.active

    def is_active(self) -> bool:
        return self.active

    def get_state_dict(self) -> dict:
        """
        Return internal state for debugging/logging.
        """
        return {
            'risk_gate_active': self.active,
            'risk_exit_counter': self._consecutive_below_off,
            'risk_delta_on': self.delta_on,
            'risk_delta_off': self.delta_off,
            'risk_exit_days_required': self.exit_days,
            'risk_exit_condition_met': self._consecutive_below_off >= self.exit_days if self.active else False,
        }

