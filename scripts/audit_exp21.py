#!/usr/bin/env python3
"""
Compatibility wrapper for EXP21 audit.

New location (preferred):
    python -m scripts.audit.audit_exp21 ...

This wrapper preserves the old entrypoint:
    python scripts/audit_exp21.py ...
"""

import runpy
import warnings


def main():
    warnings.warn(
        "DEPRECATED: use `python -m scripts.audit.audit_exp21` "
        "or `python -m scripts.cli audit exp21` instead.",
        FutureWarning,
        stacklevel=2,
    )
    # Re-run the real module as if it were executed as a script
    runpy.run_module("scripts.audit.audit_exp21", run_name="__main__")


if __name__ == "__main__":
    main()

