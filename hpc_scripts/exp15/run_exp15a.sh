#!/bin/bash
set -euo pipefail
#BSUB -J EXP15a[1-400]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15a_%J_%I.out"
#BSUB -e "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15a_%J_%I.err"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="/zhome/2a/1/202283/active/projects/thesis/22.03thesis:/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

RATIOS=(0.45 0.5 0.55 0.59 0.6 0.62 0.65 0.7)
SHIFTS=(-2 -1 0 1 2)
SEEDS=(1 2 3 4 5 6 7 8 9 10)

NUM_RATIOS=8
NUM_SHIFTS=5
NUM_SEEDS=10

IDX=$((LSB_JOBINDEX - 1))
COMBO_IDX=$((IDX / NUM_SEEDS))
SEED_IDX=$((IDX % NUM_SEEDS))

RATIO_IDX=$((COMBO_IDX / NUM_SHIFTS))
SHIFT_IDX=$((COMBO_IDX % NUM_SHIFTS))

RATIO=${RATIOS[$RATIO_IDX]}
SHIFT=${SHIFTS[$SHIFT_IDX]}
SEED=${SEEDS[$SEED_IDX]}

cd "/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
"$PYTHON_BIN" "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code/experiments/exp15_ood_evaluation.py" --exp 15a --ratio $RATIO --shift $SHIFT --seed $SEED
