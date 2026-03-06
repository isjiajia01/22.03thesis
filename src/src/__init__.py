"""
Lightweight facade package for ``src.*`` imports.

Core implementation code physically lives under:

    <REPO_ROOT>/code/

This package maps imports like:

    from src.simulation.rolling_horizon_integrated import run_rolling_horizon

onto:

    <REPO_ROOT>/code/simulation/rolling_horizon_integrated.py

so that callers can consistently depend on the logical package name
``src`` while the repository keeps its code under ``code/``.
"""

from pathlib import Path

# Resolve the repo root from this file:
#   <REPO_ROOT>/src/src/__init__.py -> parents[2] = <REPO_ROOT>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CODE_ROOT = _REPO_ROOT / "code"

# Critical trick:
#   We treat ``src`` as a namespace whose search path points at ``code/``.
#   Then ``src.simulation`` resolves to ``code/simulation``.
__path__ = [str(_CODE_ROOT)]
