#!/bin/bash
#BSUB -J EXP00_BAU_Baseline[1-10]
#BSUB -q hpc
#BSUB -o logs/exp00_%I.out
#BSUB -e logs/exp00_%I.err
#BSUB -n 1
#BSUB -W 01:00
#BSUB -R "rusage[mem=4GB]"


# Business-as-usual baseline (no pressure, no defense)

# Use venv directly
source venv/bin/activate
export PYTHONPATH=.:src:$PYTHONPATH
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEED=$LSB_JOBINDEX

echo "Starting EXP00 - Seed $SEED"
echo "Job ID: $LSB_JOBID, Array Index: $LSB_JOBINDEX"

python3 -m scripts.runner.master_runner --exp EXP00 --seed $SEED

echo "Completed EXP00 - Seed $SEED"
