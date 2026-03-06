#!/bin/bash
set -euo pipefail
#BSUB -J EXP15b[1-160]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15b_%J_%I.out"
#BSUB -e "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15b_%J_%I.err"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="/zhome/2a/1/202283/active/projects/thesis/22.03thesis:/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

MULTS=(0.9 1.0 1.1 1.2)
JITTERS=(0 1 3 5)
SEEDS=(1 2 3 4 5 6 7 8 9 10)

NUM_MULTS=4
NUM_JITTERS=4
NUM_SEEDS=10

IDX=$((LSB_JOBINDEX - 1))
COMBO_IDX=$((IDX / NUM_SEEDS))
SEED_IDX=$((IDX % NUM_SEEDS))

MULT_IDX=$((COMBO_IDX / NUM_JITTERS))
JITTER_IDX=$((COMBO_IDX % NUM_JITTERS))

MULT=${MULTS[$MULT_IDX]}
JITTER=${JITTERS[$JITTER_IDX]}
SEED=${SEEDS[$SEED_IDX]}

cd "/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
"$PYTHON_BIN" "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code/experiments/exp15_ood_evaluation.py" --exp 15b --multiplier $MULT --jitter $JITTER --seed $SEED
