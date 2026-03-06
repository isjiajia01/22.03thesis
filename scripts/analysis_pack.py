#!/usr/bin/env python3
"""
Compatibility wrapper for analysis pack.

New location (preferred):
    python -m scripts.analysis.analysis_pack ...

This wrapper preserves the old entrypoint:
    python scripts/analysis_pack.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.analysis.analysis_pack` "
        "or `python -m scripts.cli analyze` instead.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.analysis.analysis_pack", run_name="__main__")


if __name__ == "__main__":
    main()
