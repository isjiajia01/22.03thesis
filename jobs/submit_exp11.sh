#!/bin/bash
set -euo pipefail

#BSUB -J EXP11_Time_Limit_Sweep[1-80]
#BSUB -q hpc
#BSUB -o logs/exp11_%I.out
#BSUB -e logs/exp11_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"

# Compute resource ROI curve (proactive)

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
    ENDPOINT_KEY="risk_False_tl_30"
    OVERRIDES=(--override "endpoint_key=risk_False_tl_30" --override "use_risk_model=False" --override "base_compute=30" --override "high_compute=30")
    ;;
1)
    ENDPOINT_KEY="risk_False_tl_60"
    OVERRIDES=(--override "endpoint_key=risk_False_tl_60" --override "use_risk_model=False" --override "base_compute=60" --override "high_compute=60")
    ;;
2)
    ENDPOINT_KEY="risk_False_tl_120"
    OVERRIDES=(--override "endpoint_key=risk_False_tl_120" --override "use_risk_model=False" --override "base_compute=120" --override "high_compute=120")
    ;;
3)
    ENDPOINT_KEY="risk_False_tl_300"
    OVERRIDES=(--override "endpoint_key=risk_False_tl_300" --override "use_risk_model=False" --override "base_compute=300" --override "high_compute=300")
    ;;
4)
    ENDPOINT_KEY="risk_True_tl_30"
    OVERRIDES=(--override "endpoint_key=risk_True_tl_30" --override "use_risk_model=True" --override "base_compute=30" --override "high_compute=30")
    ;;
5)
    ENDPOINT_KEY="risk_True_tl_60"
    OVERRIDES=(--override "endpoint_key=risk_True_tl_60" --override "use_risk_model=True" --override "base_compute=60" --override "high_compute=60")
    ;;
6)
    ENDPOINT_KEY="risk_True_tl_120"
    OVERRIDES=(--override "endpoint_key=risk_True_tl_120" --override "use_risk_model=True" --override "base_compute=120" --override "high_compute=120")
    ;;
7)
    ENDPOINT_KEY="risk_True_tl_300"
    OVERRIDES=(--override "endpoint_key=risk_True_tl_300" --override "use_risk_model=True" --override "base_compute=300" --override "high_compute=300")
    ;;
*)
    echo "FATAL: unknown VARIANT_IDX=$VARIANT_IDX" >&2
    exit 1
    ;;
esac

echo "Starting EXP11 - Seed $SEED"
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

if [[ "True" == "True" ]]; then
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

"$PYTHON_BIN" -m scripts.runner.master_runner --exp EXP11 --seed $SEED "${OVERRIDES[@]}"

echo "Completed EXP11 - Seed $SEED ($ENDPOINT_KEY)"
