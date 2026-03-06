#!/usr/bin/env python3
"""
Preflight check for HPC compute nodes.

This script MUST be run at the beginning of every LSF job to verify:
1. Python environment is correct
2. Required dependencies (joblib, sklearn) are available
3. Risk model can be loaded successfully
4. Model structure is valid (Pipeline with scaler + classifier)

If any check fails, the script exits with code 1 to fail the job early.
"""

import sys
import os

def preflight_check(model_path: str = "models/risk_model.joblib") -> bool:
    """
    Run all preflight checks. Returns True if all pass, False otherwise.
    """
    print("=" * 70)
    print("PREFLIGHT CHECK - HPC Compute Node Validation")
    print("=" * 70)

    all_passed = True

    # 1. Python environment
    print(f"\n[1] Python Environment")
    print(f"    sys.executable: {sys.executable}")
    print(f"    sys.version: {sys.version}")
    print(f"    cwd: {os.getcwd()}")

    # 2. Check joblib
    print(f"\n[2] Dependency: joblib")
    try:
        import joblib
        print(f"    ✅ joblib version: {joblib.__version__}")
    except ImportError as e:
        print(f"    ❌ FAILED: Cannot import joblib: {e}")
        print(f"    FIX: Ensure venv is activated and joblib is installed")
        all_passed = False

    # 3. Check sklearn
    print(f"\n[3] Dependency: sklearn")
    try:
        import sklearn
        print(f"    ✅ sklearn version: {sklearn.__version__}")
    except ImportError as e:
        print(f"    ❌ FAILED: Cannot import sklearn: {e}")
        print(f"    FIX: Ensure venv is activated and scikit-learn is installed")
        all_passed = False

    # 4. Check pandas/numpy
    print(f"\n[4] Dependency: pandas/numpy")
    try:
        import pandas as pd
        import numpy as np
        print(f"    ✅ pandas version: {pd.__version__}")
        print(f"    ✅ numpy version: {np.__version__}")
    except ImportError as e:
        print(f"    ❌ FAILED: Cannot import pandas/numpy: {e}")
        all_passed = False

    # 5. Check model file exists
    print(f"\n[5] Risk Model File")

    # Resolve path relative to repo root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    if not os.path.isabs(model_path):
        model_path = os.path.join(repo_root, model_path)

    print(f"    Model path: {model_path}")

    if not os.path.exists(model_path):
        print(f"    ❌ FAILED: Model file does not exist")
        all_passed = False
    else:
        print(f"    ✅ Model file exists")

        # 6. Load model and validate structure
        print(f"\n[6] Risk Model Load & Validation")
        try:
            import joblib
            model = joblib.load(model_path)
            print(f"    ✅ Model loaded successfully")
            print(f"    Model type: {type(model)}")

            # Check if it's a Pipeline
            if hasattr(model, "named_steps"):
                steps = list(model.named_steps.keys())
                print(f"    ✅ Model is Pipeline with steps: {steps}")

                # Check for scaler
                has_scaler = any('scaler' in s.lower() for s in steps)
                if has_scaler:
                    print(f"    ✅ Pipeline contains scaler")
                else:
                    print(f"    ⚠️  WARNING: No scaler found in pipeline steps")

                # Check for classifier
                has_clf = any(s in ['lr', 'clf', 'classifier', 'logisticregression']
                             for s in [s.lower() for s in steps])
                if has_clf:
                    print(f"    ✅ Pipeline contains classifier")
                else:
                    print(f"    ⚠️  WARNING: No classifier found in pipeline steps")
            else:
                print(f"    ⚠️  WARNING: Model is not a Pipeline (type: {type(model).__name__})")

            # Check for predict_proba
            if hasattr(model, "predict_proba"):
                print(f"    ✅ Model has predict_proba method")
            else:
                print(f"    ❌ FAILED: Model missing predict_proba method")
                all_passed = False

            # Check for classes_
            if hasattr(model, "classes_"):
                print(f"    ✅ Model has classes_: {model.classes_}")
            else:
                print(f"    ⚠️  WARNING: Model missing classes_ attribute")

            # Check for feature_names_in_
            if hasattr(model, "feature_names_in_"):
                print(f"    ✅ Model has feature_names_in_: {list(model.feature_names_in_)}")
            else:
                print(f"    ⚠️  WARNING: Model missing feature_names_in_ (will use fallback order)")

        except Exception as e:
            print(f"    ❌ FAILED: Cannot load model: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    # Summary
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ PREFLIGHT CHECK PASSED - Ready for simulation")
    else:
        print("❌ PREFLIGHT CHECK FAILED - DO NOT proceed with simulation")
        print("\nCommon fixes:")
        print("  1. Ensure job script sources the correct venv:")
        print("     source /path/to/thesis/venv/bin/activate")
        print("  2. Install missing dependencies:")
        print("     pip install joblib scikit-learn pandas numpy")
        print("  3. Verify model file exists at expected path")
    print("=" * 70)

    return all_passed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HPC Preflight Check")
    parser.add_argument("--model-path", default="models/risk_model.joblib",
                       help="Path to risk model file")
    parser.add_argument("--exit-on-fail", action="store_true", default=True,
                       help="Exit with code 1 if checks fail (default: True)")
    args = parser.parse_args()

    passed = preflight_check(args.model_path)

    if not passed and args.exit_on_fail:
        sys.exit(1)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
