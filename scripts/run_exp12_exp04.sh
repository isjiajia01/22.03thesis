#!/bin/bash
#BSUB -J exp12_exp04
#BSUB -q hpc
#BSUB -n 4
#BSUB -W 4:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -R "span[hosts=1]"
#BSUB -o exp12_exp04_%J.out
#BSUB -e exp12_exp04_%J.err

export PATH="/zhome/2a/1/202283/miniforge3/bin:/zhome/2a/1/202283/.local/bin:$PATH"
export PYTHONPATH="/zhome/2a/1/202283/.local/lib/python3.12/site-packages:$PYTHONPATH"

cd "/zhome/2a/1/202283/22.01 thesis/code"
python3 experiments/exp12_learned_allocator.py --lambda 0.01 --seeds 10 --exp04-only --parallel 4
