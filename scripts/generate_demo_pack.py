#!/usr/bin/env python3
"""
Compatibility wrapper for demo visualization pack.

New location (preferred):
    python -m scripts.analysis.generate_demo_pack

This wrapper preserves the old entrypoint:
    python scripts/generate_demo_pack.py
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.analysis.generate_demo_pack` "
        "instead of `python scripts/generate_demo_pack.py`.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.analysis.generate_demo_pack", run_name="__main__")


if __name__ == "__main__":
    main()
