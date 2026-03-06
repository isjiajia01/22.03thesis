#!/bin/bash
set -euo pipefail
#BSUB -J exp12_full
#BSUB -q hpc
#BSUB -n 4
#BSUB -W 6:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o exp12_%J.out
#BSUB -e exp12_%J.err

PROJECT_ROOT="/zhome/2a/1/202283/active/projects/thesis/22.03thesis"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PATH="/zhome/2a/1/202283/miniforge3/bin:/zhome/2a/1/202283/.local/bin:$PATH"
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/code:${PYTHONPATH:-}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" code/experiments/exp12_learned_allocator.py --lambda 0.01 --seeds 10 --run_baselines --parallel 4
