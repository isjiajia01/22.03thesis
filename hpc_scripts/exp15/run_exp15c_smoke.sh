#!/bin/bash
set -euo pipefail
#BSUB -J EXP15c_smoke
#BSUB -q hpc
#BSUB -W 01:00
#BSUB -n 4
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15c_smoke_%J.out"
#BSUB -e "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_logs/exp15/EXP15c_smoke_%J.err"

PROJECT_ROOT="/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

cd "${PROJECT_ROOT}"
"$PYTHON_BIN" code/experiments/exp15_ood_evaluation.py --exp 15c --variant no_calendar --ratio 0.59 --shift 0 --seed 1
