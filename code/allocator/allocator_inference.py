#!/usr/bin/env python3
"""
Inference module for Learned Compute Allocator.

Given daily features, outputs the recommended action (30/60/120/300 seconds).

Usage:
    # As module
    from allocator_inference import ComputeAllocator
    allocator = ComputeAllocator(model_path="path/to/model.joblib")
    action = allocator.predict(features_dict)

    # As script (for testing)
    python allocator_inference.py --model_path path/to/model.joblib
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np

try:
    import joblib
except ImportError:
    joblib = None


class ComputeAllocator:
    """Learned Compute Allocator using Fitted-Q approach."""

    ACTIONS = [30, 60, 120, 300]

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        fallback_action: int = 60
    ):
        """Initialize the allocator.

        Args:
            model_path: Path to the trained model (.joblib file)
            fallback_action: Action to use if model fails (default: 60s)
        """
        self.model_path = Path(model_path) if model_path else None
        self.fallback_action = fallback_action
        self.model_data = None
        self.q_models = None
        self.feature_cols = None
        self.lambda_compute = None

        if self.model_path:
            self.load_model(self.model_path)

    def load_model(self, model_path: Union[str, Path]) -> bool:
        """Load a trained model from disk.

        Returns True if successful, False otherwise.
        """
        if joblib is None:
            print("Warning: joblib not available, cannot load model")
            return False

        try:
            self.model_path = Path(model_path)
            self.model_data = joblib.load(self.model_path)

            self.q_models = self.model_data["q_models"]
            self.feature_cols = self.model_data["feature_cols"]
            self.lambda_compute = self.model_data["lambda_compute"]

            print(f"Loaded allocator model: {self.model_path.name}")
            print(f"  Lambda: {self.lambda_compute}")
            print(f"  Features: {len(self.feature_cols)}")
            print(f"  Actions: {list(self.q_models.keys())}")

            return True

        except Exception as e:
            print(f"Error loading model from {model_path}: {e}")
            self.model_data = None
            self.q_models = None
            return False

    def predict(self, features: Dict[str, float]) -> int:
        """Predict the best action given features.

        Args:
            features: Dictionary of feature name -> value.
                      Feature names should match the training features
                      (without 'feat_' prefix).

        Returns:
            Recommended action in seconds (30, 60, 120, or 300)
        """
        if self.q_models is None:
            return self.fallback_action

        try:
            # Build feature vector in correct order
            X = self._build_feature_vector(features)

            # Get Q-values for each action
            q_values = {}
            for action, model in self.q_models.items():
                q_values[action] = float(model.predict(X.reshape(1, -1))[0])

            # Select action with highest Q-value
            best_action = max(q_values, key=q_values.get)

            return int(best_action)

        except Exception as e:
            print(f"Warning: Prediction failed ({e}), using fallback action")
            return self.fallback_action

    def predict_with_q_values(self, features: Dict[str, float]) -> Dict:
        """Predict action and return Q-values for all actions.

        Returns:
            {
                "action": int,
                "q_values": {30: float, 60: float, 120: float, 300: float}
            }
        """
        if self.q_models is None:
            return {
                "action": self.fallback_action,
                "q_values": {a: 0.0 for a in self.ACTIONS}
            }

        try:
            X = self._build_feature_vector(features)

            q_values = {}
            for action, model in self.q_models.items():
                q_values[action] = float(model.predict(X.reshape(1, -1))[0])

            # Fill missing actions with -inf
            for action in self.ACTIONS:
                if action not in q_values:
                    q_values[action] = float('-inf')

            best_action = max(q_values, key=q_values.get)

            return {
                "action": int(best_action),
                "q_values": q_values
            }

        except Exception as e:
            print(f"Warning: Prediction failed ({e})")
            return {
                "action": self.fallback_action,
                "q_values": {a: 0.0 for a in self.ACTIONS}
            }

    def _build_feature_vector(self, features: Dict[str, float]) -> np.ndarray:
        """Build feature vector in the correct order."""
        X = np.zeros(len(self.feature_cols))

        for i, col in enumerate(self.feature_cols):
            # Handle both 'feat_xxx' and 'xxx' naming
            feat_name = col.replace("feat_", "")

            if col in features:
                X[i] = features[col]
            elif feat_name in features:
                X[i] = features[feat_name]
            else:
                # Feature not provided, use 0.0
                X[i] = 0.0

        return X

    def get_feature_names(self) -> List[str]:
        """Return the list of expected feature names (without 'feat_' prefix)."""
        if self.feature_cols is None:
            return []
        return [col.replace("feat_", "") for col in self.feature_cols]

    def get_model_info(self) -> Dict:
        """Return model metadata."""
        if self.model_data is None:
            return {}

        return {
            "version": self.model_data.get("version"),
            "created_at": self.model_data.get("created_at"),
            "lambda_compute": self.model_data.get("lambda_compute"),
            "model_type": self.model_data.get("model_type"),
            "actions": self.model_data.get("actions"),
            "feature_cols": self.model_data.get("feature_cols"),
        }


def find_default_model() -> Optional[Path]:
    """Find the default model file in the standard location."""
    script_dir = Path(__file__).parent
    models_dir = script_dir.parent.parent / "data" / "allocator" / "models"

    if not models_dir.exists():
        return None

    # Look for HGB models (preferred)
    hgb_models = list(models_dir.glob("allocator_Q_lambda_*_hgb.joblib"))
    if hgb_models:
        # Return the one with lambda closest to 0.1 (reasonable default)
        def extract_lambda(p):
            try:
                name = p.stem
                parts = name.split("_")
                lam_idx = parts.index("lambda") + 1
                return float(parts[lam_idx])
            except:
                return 1.0

        return min(hgb_models, key=lambda p: abs(extract_lambda(p) - 0.1))

    return None


# =============================================================================
# CLI for testing
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test compute allocator inference")
    parser.add_argument("--model_path", type=str, default=None, help="Path to model file")
    parser.add_argument("--test", action="store_true", help="Run test with sample features")
    args = parser.parse_args()

    # Find model
    model_path = args.model_path
    if model_path is None:
        model_path = find_default_model()
        if model_path is None:
            print("Error: No model found. Please specify --model_path")
            sys.exit(1)
        print(f"Using default model: {model_path}")

    # Load allocator
    allocator = ComputeAllocator(model_path)

    if args.test:
        # Test with sample features
        test_features = {
            "capacity_ratio": 0.59,
            "capacity_pressure": 0.59,
            "pressure_k_star": 3.0,
            "visible_open_orders": 400.0,
            "mandatory_count": 100.0,
            "prev_drop_rate": 0.05,
            "prev_failures": 2.0,
            "target_load": 450.0,
            "served_colli_lag1": 500.0,
            "vrp_dropped_lag1": 5.0,
            "failures_lag1": 2.0,
        }

        print("\nTest features:")
        for k, v in test_features.items():
            print(f"  {k}: {v}")

        result = allocator.predict_with_q_values(test_features)

        print(f"\nPredicted action: {result['action']}s")
        print("Q-values:")
        for action, q in sorted(result['q_values'].items()):
            marker = " <-- best" if action == result['action'] else ""
            print(f"  {action}s: {q:.4f}{marker}")

    else:
        # Interactive mode
        print("\nModel info:")
        info = allocator.get_model_info()
        for k, v in info.items():
            print(f"  {k}: {v}")

        print("\nExpected features:")
        for feat in allocator.get_feature_names():
            print(f"  - {feat}")


if __name__ == "__main__":
    main()
