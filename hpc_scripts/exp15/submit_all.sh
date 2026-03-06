#!/bin/bash
cd "/zhome/2a/1/202283/active/projects/thesis/22.03thesis/hpc_scripts/exp15"
bsub < run_exp15a.sh
bsub < run_exp15b.sh
bsub < run_exp15c.sh
