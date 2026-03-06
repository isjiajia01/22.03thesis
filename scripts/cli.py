#!/usr/bin/env python3
"""
Unified CLI entrypoint for thesis tooling.

Usage examples:
    # Inspect an experiment config locally (official runs must go through HPC)
    python -m scripts.cli run-exp --exp EXP01 --seed 1 --dry-run

    # Audit key experiments
    python -m scripts.cli audit exp21
    python -m scripts.cli audit exp15c

    # Publication / thesis helpers
    python -m scripts.cli publish exp13b

    # Smoke / preflight checks
    python -m scripts.cli smoke phase-a
    python -m scripts.cli smoke local

    # HPC job script generation and submission
    python -m scripts.cli hpc-generate --all

    # Analysis pack
    python -m scripts.cli analyze
"""

import argparse
import sys
from typing import List


def _run_module(mod: str, argv: List[str]) -> int:
    """
    Helper to dispatch into an existing module's CLI.
    We emulate `python -m module ...` by resetting sys.argv.
    """
    import runpy

    old_argv = sys.argv[:]
    try:
        sys.argv = [mod] + argv
        runpy.run_module(mod, run_name="__main__")
        return 0
    except SystemExit as e:  # argparse typically exits with SystemExit
        code = e.code if isinstance(e.code, int) else 1
        return code
    finally:
        sys.argv = old_argv


def cmd_run_exp(args: argparse.Namespace) -> int:
    # Thin wrapper around scripts.runner.master_runner
    argv: List[str] = ["--exp", args.exp]
    if args.seed is not None:
        argv += ["--seed", str(args.seed)]
    for ov in args.override or []:
        argv += ["--override", ov]
    if args.override_json:
        argv += ["--override_json", args.override_json]
    if args.dry_run:
        argv.append("--dry-run")
    return _run_module("scripts.runner.master_runner", argv)


def cmd_analyze(args: argparse.Namespace) -> int:
    return _run_module("scripts.analysis.analysis_pack", [])


def cmd_audit(args: argparse.Namespace) -> int:
    # Map friendly names to concrete audit entrypoints
    if args.target.lower() == "exp21":
        return _run_module("scripts.audit.audit_exp21", [])
    if args.target.lower() == "exp15c":
        return _run_module("scripts.audit.audit_exp15c", [])
    print(f"Unknown audit target: {args.target!r}. Supported: exp21, exp15c.")
    return 1


def cmd_publish(args: argparse.Namespace) -> int:
    if args.target.lower() in {"exp13b", "exp13b-final"}:
        return _run_module("scripts.publish.publish_exp13b_final_decision", [])
    print(f"Unknown publish target: {args.target!r}. Supported: exp13b.")
    return 1


def cmd_smoke(args: argparse.Namespace) -> int:
    if args.which == "phase-a":
        return _run_module("scripts.smoke_test_phase_a", [])
    if args.which == "local":
        return _run_module("scripts.local_smoke_test", [])
    if args.which == "regression":
        return _run_module("scripts.regression_test", [])
    if args.which == "hpc-accept":
        return _run_module("scripts.hpc_acceptance_test", [])
    print(
        f"Unknown smoke target: {args.which!r}. "
        "Supported: phase-a, local, regression, hpc-accept."
    )
    return 1

def cmd_hpc_generate(args: argparse.Namespace) -> int:
    argv: List[str] = []
    if args.all:
        argv.append("--all")
    if args.exp:
        argv += ["--exp", args.exp]
    if args.mode:
        argv += ["--mode", args.mode]
    return _run_module("scripts.runner.generate_hpc_jobs", argv)


def cmd_preflight(args: argparse.Namespace) -> int:
    return _run_module("scripts.preflight.verify_repo_hygiene", [])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Thesis tooling unified CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # run-exp
    p_run = sub.add_parser(
        "run-exp",
        help="Run a main-matrix experiment via master_runner (EXP00–EXP11)",
    )
    p_run.add_argument("--exp", required=True, help="Experiment ID, e.g. EXP01")
    p_run.add_argument("--seed", type=int, default=1, help="Random seed")
    p_run.add_argument(
        "--override",
        action="append",
        help="Override parameter (key=value), can repeat",
    )
    p_run.add_argument(
        "--override_json",
        help="Path to JSON file with overrides",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and exit without running simulation",
    )
    p_run.set_defaults(func=cmd_run_exp)

    # analyze
    p_analyze = sub.add_parser(
        "analyze",
        help="Run analysis pack aggregation",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Run key audits (EXP21 / EXP15c)",
    )
    p_audit.add_argument(
        "target",
        help="Which audit to run: exp21, exp15c",
    )
    p_audit.set_defaults(func=cmd_audit)

    # publish
    p_pub = sub.add_parser(
        "publish",
        help="Generate publication / thesis-ready bundles",
    )
    p_pub.add_argument(
        "target",
        help="Which publication helper to run: exp13b",
    )
    p_pub.set_defaults(func=cmd_publish)

    # smoke / preflight
    p_smoke = sub.add_parser(
        "smoke",
        help="Run local/preflight smoke tests",
    )
    p_smoke.add_argument(
        "which",
        choices=["phase-a", "local", "regression", "hpc-accept"],
        help="phase-a | local | regression | hpc-accept",
    )
    p_smoke.set_defaults(func=cmd_smoke)

    # hpc-generate
    p_hpc = sub.add_parser(
        "hpc-generate",
        help="Generate HPC job submission scripts",
    )
    p_hpc.add_argument(
        "--all",
        action="store_true",
        help="Generate scripts for all experiments",
    )
    p_hpc.add_argument(
        "--exp",
        help="Generate scripts for a single experiment (e.g., EXP05)",
    )
    p_hpc.add_argument(
        "--mode",
        choices=["proactive", "greedy"],
        default="proactive",
        help="Policy mode for generated job scripts",
    )
    p_hpc.set_defaults(func=cmd_hpc_generate)

    # preflight
    p_pre = sub.add_parser(
        "preflight",
        help="Run repo-hygiene acceptance test (wrappers, CLI, src contract)",
    )
    p_pre.set_defaults(func=cmd_preflight)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
