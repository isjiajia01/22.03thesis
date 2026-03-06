#!/bin/bash
set -euo pipefail

#BSUB -J EXP01_Crunch_Baseline[1-10]
#BSUB -q hpc
#BSUB -o logs/exp01_%I.out
#BSUB -e logs/exp01_%I.err
#BSUB -n 1
#BSUB -W 01:00
#BSUB -R "rusage[mem=4GB]"


# Single-wave pressure, no defense (critical ratio) (proactive)

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
EXPECTED_SKLEARN="${EXPECTED_SKLEARN:-1.6.1}"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "FATAL: Python runtime not found at $PYTHON_BIN" >&2
    exit 1
fi

export PYTHONPATH=".:src:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEED=$LSB_JOBINDEX

echo "Starting EXP01 - Seed $SEED"
echo "Job ID: $LSB_JOBID, Array Index: $LSB_JOBINDEX"
"$PYTHON_BIN" - <<'PY'
import platform
import sys
import sklearn

print(f"Python executable: {sys.executable}")
print(f"Python version: {platform.python_version()}")
print(f"scikit-learn version: {sklearn.__version__}")
PY

if [[ "False" == "True" || "False" == "True" ]]; then
    EXPECTED_SKLEARN="$EXPECTED_SKLEARN" "$PYTHON_BIN" - <<'PY'
import pathlib
import os
import sklearn

model_path = pathlib.Path("models/risk_model.joblib")
if not model_path.exists():
    raise SystemExit(f"FATAL: missing risk model at {model_path}")
expected = os.environ["EXPECTED_SKLEARN"]
if sklearn.__version__ != expected:
    raise SystemExit(
        f"FATAL: risk-model runs require scikit-learn {expected} on the cluster runtime; got {sklearn.__version__}"
    )
PY
fi

"$PYTHON_BIN" -m scripts.runner.master_runner --exp EXP01 --seed $SEED

echo "Completed EXP01 - Seed $SEED"
