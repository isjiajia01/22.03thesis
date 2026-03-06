#!/usr/bin/env python3
"""
Compatibility wrapper for HPC job generator.

New location (preferred):
    python -m scripts.runner.generate_hpc_jobs ...

This wrapper preserves the old entrypoint:
    python scripts/generate_hpc_jobs.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.runner.generate_hpc_jobs` "
        "or `python -m scripts.cli hpc-generate --all` instead.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.runner.generate_hpc_jobs", run_name="__main__")


if __name__ == "__main__":
    main()

