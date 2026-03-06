#!/bin/bash
#BSUB -J exp12_s6
#BSUB -q hpc
#BSUB -n 1
#BSUB -W 2:00
#BSUB -R "rusage[mem=4GB]"
#BSUB -o exp12_seed6_%J.out
#BSUB -e exp12_seed6_%J.err

export PATH="/zhome/2a/1/202283/miniforge3/bin:/zhome/2a/1/202283/.local/bin:$PATH"
export PYTHONPATH="/zhome/2a/1/202283/.local/lib/python3.12/site-packages:$PYTHONPATH"

cd "/zhome/2a/1/202283/22.01 thesis/code"
python3 experiments/exp12_learned_allocator.py --lambda 0.01 --seed-start 6 --seed-end 6 --exp12-only
