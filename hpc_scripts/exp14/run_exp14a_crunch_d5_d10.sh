#!/bin/bash
set -euo pipefail
#BSUB -J EXP14a_crunch_d5_d10[1-10]
#BSUB -q hpc
#BSUB -W 4:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp14/EXP14a_%J_%I.out"
#BSUB -e "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp14/EXP14a_%J_%I.err"

# EXP14: EXP14a - Sparse Fail-Safe Bandit
# Scenario: crunch_d5_d10

PROJECT_ROOT="/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
mkdir -p "${PROJECT_ROOT}/hpc_logs/exp14"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEEDS=(1 2 3 4 5 6 7 8 9 10)
SEED=${SEEDS[$LSB_JOBINDEX-1]}
"${PYTHON_BIN}" "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/code/experiments/exp14_sparse_failsafe.py" --variant EXP14a --seed "$SEED" --scenario crunch_d5_d10
