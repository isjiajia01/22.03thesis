#!/usr/bin/env python3
"""
Compatibility wrapper for EXP15c audit.

New location (preferred):
    python -m scripts.audit.audit_exp15c ...

This wrapper preserves the old entrypoint:
    python scripts/audit_exp15c.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.audit.audit_exp15c` "
        "or `python -m scripts.cli audit exp15c` instead.",
        FutureWarning,
        stacklevel=2,
    )
    runpy.run_module("scripts.audit.audit_exp15c", run_name="__main__")


if __name__ == "__main__":
    main()

