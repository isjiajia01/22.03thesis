#!/bin/bash
set -euo pipefail

#BSUB -J EXP06_Boundary_Probe[1-20]
#BSUB -q hpc
#BSUB -o logs/exp06_%I.out
#BSUB -e logs/exp06_%I.err
#BSUB -n 1
#BSUB -W 01:00
#BSUB -R "rusage[mem=4GB]"


# Phase transition boundary: 0.58 vs 0.59 (proactive)

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
EXPECTED_SKLEARN="${EXPECTED_SKLEARN:-1.6.1}"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "FATAL: Python runtime not found at $PYTHON_BIN" >&2
    exit 1
fi

export PYTHONPATH=".:src:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEEDS=(1 2 3 4 5 6 7 8 9 10)
SEED_COUNT=10
VARIANT_IDX=$(( (LSB_JOBINDEX - 1) / SEED_COUNT ))
SEED_IDX=$(( (LSB_JOBINDEX - 1) % SEED_COUNT ))
SEED=${SEEDS[$SEED_IDX]}

case $VARIANT_IDX in
0)
    ENDPOINT_KEY="ratio_0.58"
    OVERRIDES=(--override "endpoint_key=ratio_0.58" --override "ratio=0.58")
    ;;
1)
    ENDPOINT_KEY="ratio_0.59"
    OVERRIDES=(--override "endpoint_key=ratio_0.59" --override "ratio=0.59")
    ;;
*)
    echo "FATAL: unknown VARIANT_IDX=$VARIANT_IDX" >&2
    exit 1
    ;;
esac

echo "Starting EXP06 - Seed $SEED"
echo "Job ID: $LSB_JOBID, Array Index: $LSB_JOBINDEX"
echo "Endpoint: $ENDPOINT_KEY"
"$PYTHON_BIN" - <<'PY'
import platform
import sys
import sklearn

print(f"Python executable: {sys.executable}")
print(f"Python version: {platform.python_version()}")
print(f"scikit-learn version: {sklearn.__version__}")
PY

if [[ "False" == "True" ]]; then
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

"$PYTHON_BIN" -m scripts.runner.master_runner --exp EXP06 --seed $SEED "${OVERRIDES[@]}"

echo "Completed EXP06 - Seed $SEED ($ENDPOINT_KEY)"
