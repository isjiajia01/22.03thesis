#!/bin/bash
set -euo pipefail

#BSUB -J EXP10_Phase_Diagram[1-33]
#BSUB -q hpc
#BSUB -o logs/exp10_%I.out
#BSUB -e logs/exp10_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"

# Ratio sweep for phase diagram (proactive)

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
EXPECTED_SKLEARN="${EXPECTED_SKLEARN:-1.6.1}"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "FATAL: Python runtime not found at $PYTHON_BIN" >&2
    exit 1
fi

export PYTHONPATH=".:src:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEEDS=(1 2 3)
SEED_COUNT=3
VARIANT_IDX=$(( (LSB_JOBINDEX - 1) / SEED_COUNT ))
SEED_IDX=$(( (LSB_JOBINDEX - 1) % SEED_COUNT ))
SEED=${SEEDS[$SEED_IDX]}

case $VARIANT_IDX in
0)
    ENDPOINT_KEY="ratio_0.55"
    OVERRIDES=(--override "endpoint_key=ratio_0.55" --override "ratio=0.55")
    ;;
1)
    ENDPOINT_KEY="ratio_0.56"
    OVERRIDES=(--override "endpoint_key=ratio_0.56" --override "ratio=0.56")
    ;;
2)
    ENDPOINT_KEY="ratio_0.57"
    OVERRIDES=(--override "endpoint_key=ratio_0.57" --override "ratio=0.57")
    ;;
3)
    ENDPOINT_KEY="ratio_0.58"
    OVERRIDES=(--override "endpoint_key=ratio_0.58" --override "ratio=0.58")
    ;;
4)
    ENDPOINT_KEY="ratio_0.59"
    OVERRIDES=(--override "endpoint_key=ratio_0.59" --override "ratio=0.59")
    ;;
5)
    ENDPOINT_KEY="ratio_0.6"
    OVERRIDES=(--override "endpoint_key=ratio_0.6" --override "ratio=0.6")
    ;;
6)
    ENDPOINT_KEY="ratio_0.61"
    OVERRIDES=(--override "endpoint_key=ratio_0.61" --override "ratio=0.61")
    ;;
7)
    ENDPOINT_KEY="ratio_0.62"
    OVERRIDES=(--override "endpoint_key=ratio_0.62" --override "ratio=0.62")
    ;;
8)
    ENDPOINT_KEY="ratio_0.63"
    OVERRIDES=(--override "endpoint_key=ratio_0.63" --override "ratio=0.63")
    ;;
9)
    ENDPOINT_KEY="ratio_0.64"
    OVERRIDES=(--override "endpoint_key=ratio_0.64" --override "ratio=0.64")
    ;;
10)
    ENDPOINT_KEY="ratio_0.65"
    OVERRIDES=(--override "endpoint_key=ratio_0.65" --override "ratio=0.65")
    ;;
*)
    echo "FATAL: unknown VARIANT_IDX=$VARIANT_IDX" >&2
    exit 1
    ;;
esac

echo "Starting EXP10 - Seed $SEED"
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

"$PYTHON_BIN" -m scripts.runner.master_runner --exp EXP10 --seed $SEED "${OVERRIDES[@]}"

echo "Completed EXP10 - Seed $SEED ($ENDPOINT_KEY)"
