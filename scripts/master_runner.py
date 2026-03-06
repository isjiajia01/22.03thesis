#!/usr/bin/env python3
"""
Compatibility wrapper for thesis master runner.

New location (preferred):
    python -m scripts.runner.master_runner ...

This wrapper preserves the old entrypoint:
    python scripts/master_runner.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.runner.master_runner` "
        "or `python -m scripts.cli run-exp --exp EXPID --dry-run` "
        "plus HPC submission instead.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.runner.master_runner", run_name="__main__")


if __name__ == "__main__":
    main()
