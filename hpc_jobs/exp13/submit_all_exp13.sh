#!/bin/bash
# Submit all EXP13 jobs
# Git hash: unknown

mkdir -p logs

echo "Submitting EXP13a (with guardrails)..."
bsub < submit_exp13a.sh

echo "Submitting EXP13b (no guardrails - ablation)..."
bsub < submit_exp13b.sh

echo "Done. Check job status with: bjobs -w"
