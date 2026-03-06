#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate HPC Job Submission Scripts for Sweep Experiments
Creates LSF bsub scripts for EXP05, EXP06, EXP10, EXP11
"""

import os
from pathlib import Path

# Email for job notifications
EMAIL = "isaaronzhang@icloud.com"

# Output directory
JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)

print("="*70)
print("GENERATING SWEEP EXPERIMENT HPC SCRIPTS")
print("="*70)
print()

# ============================================================================
# EXP05: Ratio Sweep (5 ratios × 3 seeds = 15 jobs)
# ============================================================================

exp05_script = f"""#!/bin/bash
#BSUB -J EXP05_RatioSweep[1-15]
#BSUB -o logs/exp05_%I.out
#BSUB -e logs/exp05_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -N
#BSUB -u {EMAIL}

# EXP05: Ratio Sweep - Explore phase transition
# Ratios: [0.75, 0.70, 0.65, 0.60, 0.55]
# Seeds: 1, 2, 3 for each ratio

module load python/3.9
source venv/bin/activate

# Map array index to (ratio, seed)
# 1-3:   r=0.75, seeds 1-3
# 4-6:   r=0.70, seeds 1-3
# 7-9:   r=0.65, seeds 1-3
# 10-12: r=0.60, seeds 1-3
# 13-15: r=0.55, seeds 1-3

INDEX=$LSB_JOBINDEX
RATIOS=(0.75 0.70 0.65 0.60 0.55)

# Calculate ratio index and seed
RATIO_IDX=$(( (INDEX - 1) / 3 ))
SEED=$(( (INDEX - 1) % 3 + 1 ))
RATIO=${{RATIOS[$RATIO_IDX]}}

echo "=========================================="
echo "EXP05: Ratio Sweep"
echo "=========================================="
echo "Job ID: $LSB_JOBID"
echo "Array Index: $LSB_JOBINDEX"
echo "Ratio: $RATIO"
echo "Seed: $SEED"
echo "=========================================="

# Create output directory
OUTPUT_DIR="data/results/EXP_05_Ratio_Sweep/r_${{RATIO}}/Seed_${{SEED}}"
mkdir -p $OUTPUT_DIR

# Run simulation using existing duration scan script
python3 scripts/run_duration_scan.py \\
    --ratio $RATIO \\
    --crunch-start 5 \\
    --crunch-ends 10 \\
    --seeds $SEED \\
    --vrp-time-limit 60 \\
    --max-trips 2 \\
    --penalty-per-fail 10000 \\
    --runs-dir data/results/EXP_05_Ratio_Sweep

echo "Completed EXP05 - Ratio $RATIO, Seed $SEED"
"""

with open(JOBS_DIR / "submit_exp05.sh", 'w') as f:
    f.write(exp05_script)
os.chmod(JOBS_DIR / "submit_exp05.sh", 0o755)
print("✓ Created jobs/submit_exp05.sh (EXP05: Ratio Sweep, 15 jobs)")

# ============================================================================
# EXP06: Duration Scan (3 durations × 3 seeds = 9 jobs)
# ============================================================================

exp06_script = f"""#!/bin/bash
#BSUB -J EXP06_DurationScan[1-9]
#BSUB -o logs/exp06_%I.out
#BSUB -e logs/exp06_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -N
#BSUB -u {EMAIL}

# EXP06: Duration Scan - Long-duration high-pressure robustness
# Fixed: r=0.60, crunch_start=5
# Vary: crunch_end = [9, 10, 11]
# Seeds: 1, 2, 3 for each duration

module load python/3.9
source venv/bin/activate

# Map array index to (crunch_end, seed)
# 1-3: crunch_end=9, seeds 1-3
# 4-6: crunch_end=10, seeds 1-3
# 7-9: crunch_end=11, seeds 1-3

INDEX=$LSB_JOBINDEX
CRUNCH_ENDS=(9 10 11)

# Calculate crunch_end index and seed
CRUNCH_IDX=$(( (INDEX - 1) / 3 ))
SEED=$(( (INDEX - 1) % 3 + 1 ))
CRUNCH_END=${{CRUNCH_ENDS[$CRUNCH_IDX]}}

echo "=========================================="
echo "EXP06: Duration Scan"
echo "=========================================="
echo "Job ID: $LSB_JOBID"
echo "Array Index: $LSB_JOBINDEX"
echo "Ratio: 0.60 (fixed)"
echo "Crunch: 5-$CRUNCH_END"
echo "Seed: $SEED"
echo "=========================================="

# Create output directory
OUTPUT_DIR="data/results/EXP_06_Duration_Scan/crunch_5_${{CRUNCH_END}}/Seed_${{SEED}}"
mkdir -p $OUTPUT_DIR

# Run simulation
python3 scripts/run_duration_scan.py \\
    --ratio 0.60 \\
    --crunch-start 5 \\
    --crunch-ends $CRUNCH_END \\
    --seeds $SEED \\
    --vrp-time-limit 60 \\
    --max-trips 2 \\
    --penalty-per-fail 10000 \\
    --runs-dir data/results/EXP_06_Duration_Scan

echo "Completed EXP06 - Crunch 5-$CRUNCH_END, Seed $SEED"
"""

with open(JOBS_DIR / "submit_exp06.sh", 'w') as f:
    f.write(exp06_script)
os.chmod(JOBS_DIR / "submit_exp06.sh", 0o755)
print("✓ Created jobs/submit_exp06.sh (EXP06: Duration Scan, 9 jobs)")

# ============================================================================
# EXP10: Compute Decoupling (3 configs × 3 seeds = 9 jobs)
# ============================================================================

exp10_script = f"""#!/bin/bash
#BSUB -J EXP10_ComputePower[1-9]
#BSUB -o logs/exp10_%I.out
#BSUB -e logs/exp10_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -N
#BSUB -u {EMAIL}

# EXP10: Compute Power Comparison
# Fixed: r=0.59, crunch 5-11
# Configs:
#   1. Static 60s (baseline)
#   2. Static 300s (brute force)
#   3. Dynamic (RiskGate: 60s → 180s)
# Seeds: 1, 2, 3 for each config

module load python/3.9
source venv/bin/activate

# Map array index to (config, seed)
# 1-3: Static_60s, seeds 1-3
# 4-6: Static_300s, seeds 1-3
# 7-9: Dynamic_RiskGate, seeds 1-3

INDEX=$LSB_JOBINDEX

# Calculate config index and seed
CONFIG_IDX=$(( (INDEX - 1) / 3 ))
SEED=$(( (INDEX - 1) % 3 + 1 ))

case $CONFIG_IDX in
    0)
        CONFIG_NAME="Static_60s"
        VRP_TIME_LIMIT=60
        USE_RISK_MODEL="false"
        ;;
    1)
        CONFIG_NAME="Static_300s"
        VRP_TIME_LIMIT=300
        USE_RISK_MODEL="false"
        ;;
    2)
        CONFIG_NAME="Dynamic_RiskGate"
        VRP_TIME_LIMIT=60
        USE_RISK_MODEL="true"
        ;;
esac

echo "=========================================="
echo "EXP10: Compute Power Comparison"
echo "=========================================="
echo "Job ID: $LSB_JOBID"
echo "Array Index: $LSB_JOBINDEX"
echo "Config: $CONFIG_NAME"
echo "VRP Time Limit: $VRP_TIME_LIMIT"
echo "Use Risk Model: $USE_RISK_MODEL"
echo "Seed: $SEED"
echo "=========================================="

# Create output directory
OUTPUT_DIR="data/results/EXP_10_Compute_Power/${{CONFIG_NAME}}/Seed_${{SEED}}"
mkdir -p $OUTPUT_DIR

# Set environment variable for VRP time limit
export VRP_TIME_LIMIT_SECONDS=$VRP_TIME_LIMIT

# Run simulation
if [ "$USE_RISK_MODEL" = "true" ]; then
    # Dynamic compute with RiskGate
    python3 scripts/run_duration_scan.py \\
        --ratio 0.59 \\
        --crunch-start 5 \\
        --crunch-ends 11 \\
        --seeds $SEED \\
        --vrp-time-limit 60 \\
        --max-trips 2 \\
        --penalty-per-fail 10000 \\
        --risk-model-path models/risk_model.joblib \\
        --runs-dir data/results/EXP_10_Compute_Power
else
    # Static compute (no RiskGate)
    python3 scripts/run_duration_scan.py \\
        --ratio 0.59 \\
        --crunch-start 5 \\
        --crunch-ends 11 \\
        --seeds $SEED \\
        --vrp-time-limit $VRP_TIME_LIMIT \\
        --max-trips 2 \\
        --penalty-per-fail 10000 \\
        --runs-dir data/results/EXP_10_Compute_Power
fi

echo "Completed EXP10 - $CONFIG_NAME, Seed $SEED"
"""

with open(JOBS_DIR / "submit_exp10.sh", 'w') as f:
    f.write(exp10_script)
os.chmod(JOBS_DIR / "submit_exp10.sh", 0o755)
print("✓ Created jobs/submit_exp10.sh (EXP10: Compute Power, 9 jobs)")

# ============================================================================
# EXP11: Max Trips Expansion (2 configs × 3 seeds = 6 jobs)
# ============================================================================

exp11_script = f"""#!/bin/bash
#BSUB -J EXP11_MaxTrips[1-6]
#BSUB -o logs/exp11_%I.out
#BSUB -e logs/exp11_%I.err
#BSUB -n 2
#BSUB -W 04:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -N
#BSUB -u {EMAIL}

# EXP11: Physical DoF - Max Trips Expansion
# Fixed: r=0.59, crunch 5-11
# Configs:
#   1. max_trips=2 (baseline)
#   2. max_trips=3 (expanded capacity)
# Seeds: 1, 2, 3 for each config

module load python/3.9
source venv/bin/activate

# Map array index to (max_trips, seed)
# 1-3: max_trips=2, seeds 1-3
# 4-6: max_trips=3, seeds 1-3

INDEX=$LSB_JOBINDEX

# Calculate max_trips and seed
if [ $INDEX -le 3 ]; then
    MAX_TRIPS=2
    SEED=$INDEX
else
    MAX_TRIPS=3
    SEED=$((INDEX - 3))
fi

echo "=========================================="
echo "EXP11: Physical DoF - Max Trips"
echo "=========================================="
echo "Job ID: $LSB_JOBID"
echo "Array Index: $LSB_JOBINDEX"
echo "Max Trips: $MAX_TRIPS"
echo "Seed: $SEED"
echo "=========================================="

# Create output directory
OUTPUT_DIR="data/results/EXP_11_Physical_DoF/Trips_${{MAX_TRIPS}}/Seed_${{SEED}}"
mkdir -p $OUTPUT_DIR

# Run simulation with RiskGate
python3 scripts/run_duration_scan.py \\
    --ratio 0.59 \\
    --crunch-start 5 \\
    --crunch-ends 11 \\
    --seeds $SEED \\
    --vrp-time-limit 60 \\
    --max-trips $MAX_TRIPS \\
    --penalty-per-fail 10000 \\
    --risk-model-path models/risk_model.joblib \\
    --runs-dir data/results/EXP_11_Physical_DoF

echo "Completed EXP11 - Max Trips $MAX_TRIPS, Seed $SEED"
"""

with open(JOBS_DIR / "submit_exp11.sh", 'w') as f:
    f.write(exp11_script)
os.chmod(JOBS_DIR / "submit_exp11.sh", 0o755)
print("✓ Created jobs/submit_exp11.sh (EXP11: Physical DoF, 6 jobs)")

# ============================================================================
# Master Sweep Submission Script
# ============================================================================

sweep_master_script = f"""#!/bin/bash
# Master Sweep Experiments Submission Script
# Submits EXP05, EXP06, EXP10, EXP11

echo "=========================================="
echo "MOVER Sweep Experiments - HPC Submission"
echo "=========================================="
echo ""

# Create logs directory
mkdir -p logs

echo "Submitting sweep experiments..."
echo ""

# EXP05: Ratio Sweep (15 jobs)
echo "[1/4] Submitting EXP05 - Ratio Sweep (15 jobs)..."
bsub < jobs/submit_exp05.sh
sleep 1

# EXP06: Duration Scan (9 jobs)
echo "[2/4] Submitting EXP06 - Duration Scan (9 jobs)..."
bsub < jobs/submit_exp06.sh
sleep 1

# EXP10: Compute Power (9 jobs)
echo "[3/4] Submitting EXP10 - Compute Power (9 jobs)..."
bsub < jobs/submit_exp10.sh
sleep 1

# EXP11: Physical DoF (6 jobs)
echo "[4/4] Submitting EXP11 - Physical DoF (6 jobs)..."
bsub < jobs/submit_exp11.sh
sleep 1

echo ""
echo "=========================================="
echo "All sweep experiments submitted!"
echo "=========================================="
echo ""
echo "Total jobs: 39"
echo "  - EXP05: 15 jobs (5 ratios × 3 seeds)"
echo "  - EXP06: 9 jobs (3 durations × 3 seeds)"
echo "  - EXP10: 9 jobs (3 configs × 3 seeds)"
echo "  - EXP11: 6 jobs (2 configs × 3 seeds)"
echo ""
echo "Monitor jobs with:"
echo "  bjobs"
echo "  bjobs -l <job_id>"
echo ""
echo "Check logs in:"
echo "  logs/exp05_*.out"
echo "  logs/exp06_*.out"
echo "  logs/exp10_*.out"
echo "  logs/exp11_*.out"
echo ""
echo "Results will be in:"
echo "  data/results/EXP_05_Ratio_Sweep/"
echo "  data/results/EXP_06_Duration_Scan/"
echo "  data/results/EXP_10_Compute_Power/"
echo "  data/results/EXP_11_Physical_DoF/"
echo ""
"""

with open(JOBS_DIR / "submit_sweeps.sh", 'w') as f:
    f.write(sweep_master_script)
os.chmod(JOBS_DIR / "submit_sweeps.sh", 0o755)
print("✓ Created jobs/submit_sweeps.sh (master sweep script)")

# ============================================================================
# Update Master Submission Script to Include Sweeps
# ============================================================================

complete_master_script = f"""#!/bin/bash
# Complete Master HPC Submission Script
# Submits ALL experiments (EXP00-EXP11)

echo "=========================================="
echo "MOVER Complete Thesis Experiments"
echo "=========================================="
echo ""

# Create logs directory
mkdir -p logs

echo "Submitting all experiments..."
echo ""

# ============================================================================
# PART 1: Core Experiments (21 jobs)
# ============================================================================

echo "PART 1: Core Experiments"
echo "----------------------------------------"

# EXP00: BAU Baseline (3 jobs)
echo "[1/10] Submitting EXP00 - BAU Baseline (3 jobs)..."
bsub < jobs/submit_exp00.sh
sleep 1

# EXP01: Crunch Baseline (3 jobs)
echo "[2/10] Submitting EXP01 - Crunch Baseline (3 jobs)..."
bsub < jobs/submit_exp01.sh
sleep 1

# EXP02-04: Ablation Study (9 jobs)
echo "[3/10] Submitting EXP02-04 - Ablation Study (9 jobs)..."
bsub < jobs/submit_ablation.sh
sleep 1

# EXP07: Boundary Point (3 jobs)
echo "[4/10] Submitting EXP07 - Boundary Point (3 jobs)..."
bsub < jobs/submit_exp07.sh
sleep 1

# EXP09: RiskGate Smoke (3 jobs)
echo "[5/10] Submitting EXP09 - RiskGate Smoke (3 jobs)..."
bsub < jobs/submit_exp09.sh
sleep 1

echo ""
echo "PART 2: Sweep Experiments"
echo "----------------------------------------"

# EXP05: Ratio Sweep (15 jobs)
echo "[6/10] Submitting EXP05 - Ratio Sweep (15 jobs)..."
bsub < jobs/submit_exp05.sh
sleep 1

# EXP06: Duration Scan (9 jobs)
echo "[7/10] Submitting EXP06 - Duration Scan (9 jobs)..."
bsub < jobs/submit_exp06.sh
sleep 1

# EXP10: Compute Power (9 jobs)
echo "[8/10] Submitting EXP10 - Compute Power (9 jobs)..."
bsub < jobs/submit_exp10.sh
sleep 1

# EXP11: Physical DoF (6 jobs)
echo "[9/10] Submitting EXP11 - Physical DoF (6 jobs)..."
bsub < jobs/submit_exp11.sh
sleep 1

echo ""
echo "=========================================="
echo "ALL EXPERIMENTS SUBMITTED!"
echo "=========================================="
echo ""
echo "Total jobs: 60"
echo ""
echo "Core Experiments (21 jobs):"
echo "  - EXP00: 3 jobs"
echo "  - EXP01: 3 jobs"
echo "  - EXP02-04: 9 jobs"
echo "  - EXP07: 3 jobs"
echo "  - EXP09: 3 jobs"
echo ""
echo "Sweep Experiments (39 jobs):"
echo "  - EXP05: 15 jobs"
echo "  - EXP06: 9 jobs"
echo "  - EXP10: 9 jobs"
echo "  - EXP11: 6 jobs"
echo ""
echo "Monitor jobs with:"
echo "  bjobs"
echo "  bjobs -u $USER"
echo ""
echo "Check logs in:"
echo "  logs/"
echo ""
echo "Results will be in:"
echo "  data/results/"
echo ""
"""

with open(JOBS_DIR / "submit_complete.sh", 'w') as f:
    f.write(complete_master_script)
os.chmod(JOBS_DIR / "submit_complete.sh", 0o755)
print("✓ Created jobs/submit_complete.sh (complete master script)")

print()
print("="*70)
print("SWEEP EXPERIMENT SCRIPTS GENERATED")
print("="*70)
print()
print("Generated scripts:")
print("  - jobs/submit_exp05.sh     (EXP05: Ratio Sweep, 15 jobs)")
print("  - jobs/submit_exp06.sh     (EXP06: Duration Scan, 9 jobs)")
print("  - jobs/submit_exp10.sh     (EXP10: Compute Power, 9 jobs)")
print("  - jobs/submit_exp11.sh     (EXP11: Physical DoF, 6 jobs)")
print("  - jobs/submit_sweeps.sh    (Sweep master script)")
print("  - jobs/submit_complete.sh  (Complete master script)")
print()
print("Total sweep jobs: 39")
print("Total all jobs: 60 (21 core + 39 sweep)")
print()
print("To submit sweep experiments only:")
print("  bash jobs/submit_sweeps.sh")
print()
print("To submit ALL experiments:")
print("  bash jobs/submit_complete.sh")
print()
