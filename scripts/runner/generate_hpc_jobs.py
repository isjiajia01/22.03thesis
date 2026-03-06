#!/usr/bin/env python3
"""
Generate HPC job submission scripts for all experiments.
Supports sweeps and multi-seed runs.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List

# scripts.__init__ auto-injects REPO_ROOT into sys.path (A1 contract)
import scripts  # noqa: F401
REPO_ROOT = scripts.REPO_ROOT

from scripts.experiment_definitions import EXPERIMENTS


def _format_scalar(value):
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _variant(endpoint_key: str, **overrides) -> Dict[str, object]:
    return {"endpoint_key": endpoint_key, "overrides": overrides}


def expand_variants(exp_id: str, exp_config: Dict[str, object]) -> List[Dict[str, object]]:
    params = exp_config["params"]
    if not exp_config.get("is_sweep"):
        return [_variant("baseline")]

    if exp_id == "EXP05":
        return [_variant(f"max_trips_{mt}", max_trips=mt) for mt in params["max_trips_list"]]
    if exp_id == "EXP06":
        return [_variant(f"ratio_{ratio}", ratio=ratio) for ratio in params["ratios"]]
    if exp_id == "EXP07":
        variants = []
        for ratio in params["ratios"]:
            for use_risk_model in params["use_risk_model_list"]:
                variants.append(
                    _variant(
                        f"ratio_{ratio}_risk_{use_risk_model}",
                        ratio=ratio,
                        use_risk_model=use_risk_model,
                    )
                )
        return variants
    if exp_id == "EXP08":
        delta_off_ratio = params["delta_off_ratio"]
        return [
            _variant(
                f"delta_{delta_on}",
                risk_threshold_on=delta_on,
                risk_threshold_off=round(delta_on * delta_off_ratio, 6),
            )
            for delta_on in params["delta_on_list"]
        ]
    if exp_id == "EXP09":
        return [_variant(f"risk_{flag}", use_risk_model=flag) for flag in params["use_risk_model_list"]]
    if exp_id == "EXP10":
        return [_variant(f"ratio_{ratio}", ratio=ratio) for ratio in params["ratios"]]
    if exp_id == "EXP11":
        variants = []
        for flag in params["use_risk_model_list"]:
            for tl in params["time_limits"]:
                variants.append(
                    _variant(
                        f"risk_{flag}_tl_{tl}",
                        use_risk_model=flag,
                        base_compute=tl,
                        high_compute=tl,
                    )
                )
        return variants
    raise ValueError(f"No sweep expansion rule defined for {exp_id}")


def generate_job_script(exp_id, exp_config, output_dir="jobs", mode="proactive"):
    """Generate LSF job script for an experiment."""

    name = exp_config["name"]
    seeds = exp_config.get("seeds", [1])
    resource = exp_config.get("resource", "standard")
    mode = str(mode).lower()
    if mode not in {"proactive", "greedy"}:
        raise ValueError(f"Unsupported mode: {mode}")

    # Resource allocation
    if resource == "heavy":
        walltime = "04:00"
        mem = "8GB"
        slots = 2
    else:
        walltime = "01:00"
        mem = "4GB"
        slots = 1

    variants = expand_variants(exp_id, exp_config)
    seed_count = len(seeds)
    array_size = len(seeds) * len(variants)
    job_suffix = "" if mode == "proactive" else f"_{mode}"
    job_name = f"{exp_id}_{name}{job_suffix}"
    log_stem = f"{exp_id.lower()}{job_suffix}"
    use_risk_model_check = any(
        bool(v["overrides"].get("use_risk_model", exp_config["params"].get("use_risk_model", False)))
        for v in variants
    )

    case_lines = []
    for idx, variant in enumerate(variants):
        override_items = {"endpoint_key": variant["endpoint_key"], **variant["overrides"]}
        if mode != "proactive":
            override_items["mode"] = "greedy"
        override_tokens = []
        for key, value in override_items.items():
            override_tokens.append(f'--override "{key}={_format_scalar(value)}"')
        override_str = " ".join(override_tokens)
        case_lines.append(
            f"""{idx})
    ENDPOINT_KEY="{variant['endpoint_key']}"
    OVERRIDES=({override_str})
    ;;"""
        )
    case_block = "\n".join(case_lines)
    seeds_literal = " ".join(str(seed) for seed in seeds)

    # Script content (use raw strings to avoid escape issues)
    script = f"""#!/bin/bash
set -euo pipefail

#BSUB -J {job_name}[1-{array_size}]
#BSUB -q hpc
#BSUB -o logs/{log_stem}_%I.out
#BSUB -e logs/{log_stem}_%I.err
#BSUB -n {slots}
#BSUB -W {walltime}
#BSUB -R "rusage[mem={mem}]"
{ '#BSUB -R "span[hosts=1]"' if slots > 1 else '' }

# {exp_config['description']} ({mode})

PYTHON_BIN="${{PYTHON_BIN:-/usr/bin/python3}}"
EXPECTED_SKLEARN="${{EXPECTED_SKLEARN:-1.6.1}}"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "FATAL: Python runtime not found at $PYTHON_BIN" >&2
    exit 1
fi

export PYTHONPATH=".:src:${{PYTHONPATH:-}}"
export VRP_MAX_TRIPS_PER_VEHICLE=2

SEEDS=({seeds_literal})
SEED_COUNT={seed_count}
VARIANT_IDX=$(( (LSB_JOBINDEX - 1) / SEED_COUNT ))
SEED_IDX=$(( (LSB_JOBINDEX - 1) % SEED_COUNT ))
SEED=${{SEEDS[$SEED_IDX]}}

case $VARIANT_IDX in
{case_block}
*)
    echo "FATAL: unknown VARIANT_IDX=$VARIANT_IDX" >&2
    exit 1
    ;;
esac

echo "Starting {exp_id} - Seed $SEED"
echo "Job ID: $LSB_JOBID, Array Index: $LSB_JOBINDEX"
echo "Endpoint: $ENDPOINT_KEY"
"$PYTHON_BIN" - <<'PY'
import platform
import sys
import sklearn

print(f"Python executable: {{sys.executable}}")
print(f"Python version: {{platform.python_version()}}")
print(f"scikit-learn version: {{sklearn.__version__}}")
PY

if [[ "{use_risk_model_check}" == "True" ]]; then
    EXPECTED_SKLEARN="$EXPECTED_SKLEARN" "$PYTHON_BIN" - <<'PY'
import pathlib
import os
import sklearn

model_path = pathlib.Path("models/risk_model.joblib")
if not model_path.exists():
    raise SystemExit(f"FATAL: missing risk model at {{model_path}}")
expected = os.environ["EXPECTED_SKLEARN"]
if sklearn.__version__ != expected:
    raise SystemExit(
        f"FATAL: risk-model runs require scikit-learn {{expected}} on the cluster runtime; got {{sklearn.__version__}}"
    )
PY
fi

"$PYTHON_BIN" -m scripts.runner.master_runner --exp {exp_id} --seed $SEED "${{OVERRIDES[@]}}"

echo "Completed {exp_id} - Seed $SEED ($ENDPOINT_KEY)"
"""

    # Write script
    output_path = Path(output_dir) / f"submit_{log_stem}.sh"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(script)

    # Make executable
    os.chmod(output_path, 0o755)

    return output_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate HPC job scripts")
    parser.add_argument("--all", action="store_true", help="Generate all experiments")
    parser.add_argument("--exp", type=str, help="Generate specific experiment")
    parser.add_argument(
        "--mode",
        choices=["proactive", "greedy"],
        default="proactive",
        help="Policy mode for generated job scripts",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("HPC JOB SCRIPT GENERATOR")
    print("=" * 70)
    print()

    if args.all:
        print("Generating scripts for ALL experiments...")
        print()

        generated = []
        for exp_id, exp_config in EXPERIMENTS.items():
            print(f"  {exp_id}: {exp_config['name']} [{args.mode}]")
            script_path = generate_job_script(exp_id, exp_config, mode=args.mode)
            generated.append(exp_id)

        print()
        print(f"✅ Generated {len(generated)} job scripts")
        print()
        print("To submit all:")
        print("  bash jobs/submit_all.sh")

    elif args.exp:
        exp_id = args.exp.upper()
        if exp_id not in EXPERIMENTS:
            print(f"❌ Unknown experiment: {exp_id}")
            return 1

        exp_config = EXPERIMENTS[exp_id]
        script_path = generate_job_script(exp_id, exp_config, mode=args.mode)
        print(f"✅ Generated {script_path}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
