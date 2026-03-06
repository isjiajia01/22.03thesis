#!/bin/bash
set -euo pipefail
#BSUB -J EXP13a[1-70]
#BSUB -q hpc
#BSUB -W 2:00
#BSUB -n 4
#BSUB -R "rusage[mem=4GB]"
#BSUB -o logs/EXP13a_%J_%I.out
#BSUB -e logs/EXP13a_%J_%I.err

# EXP13: EXP13a - Bandit-Augmented Allocator
# Git hash: unknown
# Generated: 2026-03-06T09:44:40.578555

PROJECT_ROOT="/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "${PROJECT_ROOT}/logs"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

# Map job array index to (seed, scenario)
SEEDS=(1 2 3 4 5 6 7 8 9 10)
SCENARIOS=(crunch_d5_d10 crunch_d3_d6 crunch_d6_d9 ratio_0.55 ratio_0.59 ratio_0.6 ratio_0.65)

N_SEEDS=${#SEEDS[@]}
N_SCENARIOS=${#SCENARIOS[@]}

IDX=$((LSB_JOBINDEX - 1))
SEED_IDX=$((IDX / N_SCENARIOS))
SCENARIO_IDX=$((IDX % N_SCENARIOS))

SEED=${SEEDS[$SEED_IDX]}
SCENARIO=${SCENARIOS[$SCENARIO_IDX]}

echo "Job $LSB_JOBINDEX: variant=EXP13a, seed=$SEED, scenario=$SCENARIO"

"$PYTHON_BIN" code/experiments/exp13_bandit_allocator.py \
    --variant EXP13a \
    --scenario $SCENARIO \
    --seed $SEED \
    --single-run
