"""
Experiment scripts package.

This package is organized into submodules such as:
- analysis: aggregation and analysis helpers
- audit: auditing and validation tools
- runner: experiment definitions and runners
- preflight: smoke tests and pre-HPC checks
- publish: publication and thesis-related helpers
- legacy: old or deprecated entrypoints kept for compatibility

DEPENDENCY CONTRACT (A1)
========================
Modules in ``scripts.runner`` (master_runner, etc.) import from the ``src``
package (``src.simulation``, ``src.experiments``, …).  ``src`` lives at
<REPO_ROOT>/code/ but is NOT an installed package — it is found via
``sys.path``.

This __init__.py automatically adds <REPO_ROOT> to sys.path so that
``import src.…`` works whenever any ``scripts.*`` module is imported.
If ``src`` is still not importable after the path fixup (e.g. the code/
directory was not checked out), ``ensure_src()`` will raise a clear error.

For HPC jobs:
    export PYTHON_BIN=/usr/bin/python3
    cd <REPO_ROOT>
    export PYTHONPATH=.:src:$PYTHONPATH
    $PYTHON_BIN -m scripts.cli run-exp --exp EXP04 --seed 1 --dry-run
    $PYTHON_BIN -m scripts.cli hpc-generate --exp EXP04
    bsub < jobs/submit_exp04.sh

The ``ensure_src()`` helper is also called by the preflight check
(``scripts/preflight/verify_repo_hygiene.py``) and can be imported
anywhere you need an early guard.
"""

import os
import sys
from pathlib import Path

# ── Auto-inject REPO_ROOT into sys.path ──────────────────────────────
# __file__ = <REPO_ROOT>/scripts/__init__.py  →  parents[1] = REPO_ROOT
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_FACADE_ROOT = _REPO_ROOT / "src"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if _SRC_FACADE_ROOT.exists() and str(_SRC_FACADE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_FACADE_ROOT))

REPO_ROOT = _REPO_ROOT  # public, so other modules can use scripts.REPO_ROOT


def ensure_src(*, verbose: bool = False) -> bool:
    """
    Verify that ``import src`` succeeds.

    Returns True on success.  Raises ImportError with a human-readable
    diagnostic on failure.

    Call this at the top of any heavy entry-point (runner, simulation,
    smoke test) to fail fast with a clear message instead of a cryptic
    traceback.
    """
    try:
        import src  # noqa: F401
        if verbose:
            print(f"[preflight] src package OK  (location: {src.__file__})")
        return True
    except ImportError:
        msg = (
            "\n"
            "=" * 70 + "\n"
            "FATAL: cannot import 'src' package.\n"
            "=" * 70 + "\n"
            "\n"
            "The scripts.runner and scripts.preflight modules depend on\n"
            "the 'src' package located at:\n"
            f"    {_REPO_ROOT / 'code'}\n"
            "\n"
            "Possible causes:\n"
            "  1) You are running from the wrong directory.\n"
            "     → cd to the repo root first.\n"
            "  2) The code/ directory is missing or incomplete.\n"
            "     → git checkout / pull the latest code.\n"
            "  3) PYTHONPATH does not include the repo root.\n"
            f"     → export PYTHONPATH={_REPO_ROOT}:$PYTHONPATH\n"
            "\n"
            "After fixing, re-run your command.\n"
            "=" * 70
        )
        raise ImportError(msg)
