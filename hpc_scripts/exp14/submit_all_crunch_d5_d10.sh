#!/bin/bash
# Submit all EXP14 variants for crunch_d5_d10

cd "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_scripts/exp14"

bsub < run_exp14a_crunch_d5_d10.sh
bsub < run_exp14b_crunch_d5_d10.sh
bsub < run_exp14c_crunch_d5_d10.sh
