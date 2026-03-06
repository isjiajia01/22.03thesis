#!/usr/bin/env python3
"""
Re-export persisted risk-model artifacts as native scikit-learn 1.6.1 objects.

Why this exists:
- The repository's joblib artifacts were serialized with newer sklearn builds.
- Cluster jobs currently run with sklearn 1.6.1.
- Loading newer artifacts under 1.6.1 emits InconsistentVersionWarning and is
  not a sound experimental setup.

This script migrates the existing fitted parameters into fresh 1.6.1 estimator
instances, then writes back version-compatible joblib files.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "models"
EXPECTED_VERSION = "1.6.1"


def clone_scaler(old: StandardScaler) -> StandardScaler:
    new = StandardScaler(**old.get_params())
    for attr in (
        "mean_",
        "scale_",
        "var_",
        "n_features_in_",
        "n_samples_seen_",
        "feature_names_in_",
    ):
        if hasattr(old, attr):
            value = getattr(old, attr)
            setattr(new, attr, value.copy() if hasattr(value, "copy") else value)
    return new


def clone_logistic(old: LogisticRegression) -> LogisticRegression:
    params = {
        "C": getattr(old, "C", 1.0),
        "class_weight": getattr(old, "class_weight", None),
        "dual": getattr(old, "dual", False),
        "fit_intercept": getattr(old, "fit_intercept", True),
        "intercept_scaling": getattr(old, "intercept_scaling", 1),
        "l1_ratio": getattr(old, "l1_ratio", None),
        "max_iter": getattr(old, "max_iter", 100),
        "n_jobs": getattr(old, "n_jobs", None),
        "penalty": getattr(old, "penalty", "l2"),
        "random_state": getattr(old, "random_state", None),
        "solver": getattr(old, "solver", "lbfgs"),
        "tol": getattr(old, "tol", 1e-4),
        "verbose": getattr(old, "verbose", 0),
        "warm_start": getattr(old, "warm_start", False),
    }
    if hasattr(old, "multi_class"):
        params["multi_class"] = getattr(old, "multi_class")

    new = LogisticRegression(**params)
    for attr in (
        "classes_",
        "coef_",
        "intercept_",
        "n_features_in_",
        "feature_names_in_",
        "n_iter_",
    ):
        if hasattr(old, attr):
            value = getattr(old, attr)
            setattr(new, attr, value.copy() if hasattr(value, "copy") else value)

    # Mirror sklearn's derived attributes expected by inference.
    if hasattr(new, "coef_"):
        new.n_features_in_ = new.coef_.shape[1]
        if len(getattr(new, "classes_", [])) == 2:
            new.n_iter_ = np.asarray(getattr(new, "n_iter_", [0]), dtype=np.int32)
    return new


def backup(path: Path) -> Path:
    backup_path = path.with_suffix(path.suffix + ".pre_sklearn_1_6_backup")
    shutil.copy2(path, backup_path)
    return backup_path


def migrate_pipeline(path: Path) -> None:
    old = joblib.load(path)
    if not isinstance(old, Pipeline):
        raise TypeError(f"{path} is not a Pipeline")

    scaler = clone_scaler(old.named_steps["scaler"])
    clf = clone_logistic(old.named_steps["clf"])
    new = Pipeline([("scaler", scaler), ("clf", clf)])

    backup_path = backup(path)
    joblib.dump(new, path)
    print(f"migrated pipeline: {path.name} (backup: {backup_path.name})")


def migrate_estimator(path: Path, estimator_type: str) -> None:
    old = joblib.load(path)
    if estimator_type == "logistic":
        new = clone_logistic(old)
    elif estimator_type == "scaler":
        new = clone_scaler(old)
    else:
        raise ValueError(f"unsupported estimator type: {estimator_type}")

    backup_path = backup(path)
    joblib.dump(new, path)
    print(f"migrated {estimator_type}: {path.name} (backup: {backup_path.name})")


def main() -> int:
    import sklearn

    if sklearn.__version__ != EXPECTED_VERSION:
        raise SystemExit(
            f"Run this script under scikit-learn {EXPECTED_VERSION}, got {sklearn.__version__}"
        )

    migrate_pipeline(MODELS_DIR / "risk_model.joblib")
    migrate_estimator(MODELS_DIR / "risk_model_old.joblib", "logistic")
    migrate_estimator(MODELS_DIR / "risk_scaler.joblib", "scaler")
    migrate_estimator(MODELS_DIR / "mock_risk_model.joblib", "logistic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
