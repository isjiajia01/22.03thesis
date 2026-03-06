#!/bin/bash
set -euo pipefail
#BSUB -J EXP15c[1-200]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15c_%J_%I.out"
#BSUB -e "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15c_%J_%I.err"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="/zhome/2a/1/202283/active/projects/thesis/22.03thesis:/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

VARIANTS=(full no_ratio no_calendar no_calendar_aug)
RATIOS=(0.59 0.59 0.55 0.5 0.65)
SHIFTS=(0 -2 -2 -1 -2)
SEEDS=(1 2 3 4 5 6 7 8 9 10)

NUM_VARIANTS=4
NUM_CONDITIONS=5
NUM_SEEDS=10

IDX=$((LSB_JOBINDEX - 1))
VARIANT_IDX=$((IDX / (NUM_CONDITIONS * NUM_SEEDS)))
REMAINDER=$((IDX % (NUM_CONDITIONS * NUM_SEEDS)))
COND_IDX=$((REMAINDER / NUM_SEEDS))
SEED_IDX=$((REMAINDER % NUM_SEEDS))

VARIANT=${VARIANTS[$VARIANT_IDX]}
RATIO=${RATIOS[$COND_IDX]}
SHIFT=${SHIFTS[$COND_IDX]}
SEED=${SEEDS[$SEED_IDX]}

cd "/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
"$PYTHON_BIN" "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code/experiments/exp15_ood_evaluation.py" --exp 15c --variant $VARIANT --ratio $RATIO --shift $SHIFT --seed $SEED
