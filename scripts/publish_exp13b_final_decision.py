#!/usr/bin/env python3
"""
Compatibility wrapper for EXP13b final decision publisher.

New location (preferred):
    python -m scripts.publish.publish_exp13b_final_decision ...

This wrapper preserves the old entrypoint:
    python scripts/publish_exp13b_final_decision.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.publish.publish_exp13b_final_decision` "
        "or `python -m scripts.cli publish exp13b` instead.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.publish.publish_exp13b_final_decision", run_name="__main__")


if __name__ == "__main__":
    main()

