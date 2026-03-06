#!/usr/bin/env python3
"""
Minimal acceptance test for the repo-hygiene restructuring.

This script verifies:
  1. All ``__init__.py`` markers exist  (package structure intact)
  2. All compatibility wrappers at old locations contain ``runpy``
  3. The unified CLI parses each subcommand (--help exits 0)
  4. Every new-location module can be *located* by importlib
  5. ``scripts.ensure_src()`` contract is callable
  6. Optional: if ``src`` is importable, validate the full path chain

Run:
    python -m scripts.preflight.verify_repo_hygiene        # from repo root
    python scripts/preflight/verify_repo_hygiene.py         # also works

Exit 0  = all checks pass
Exit 1  = at least one failure (details printed to stderr)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

# ── Resolve repo root ────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PASS = 0
FAIL = 0


def _pass(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    msg = f"  [FAIL] {label}"
    if detail:
        msg += f"  — {detail}"
    print(msg, file=sys.stderr)


# ── 1. Package __init__.py markers ───────────────────────────────────
def check_init_files() -> None:
    print("\n1. Package __init__.py markers")
    expected = [
        "scripts/__init__.py",
        "scripts/analysis/__init__.py",
        "scripts/audit/__init__.py",
        "scripts/runner/__init__.py",
        "scripts/preflight/__init__.py",
        "scripts/publish/__init__.py",
        "scripts/legacy/__init__.py",
    ]
    for rel in expected:
        p = REPO_ROOT / rel
        if p.is_file():
            _pass(rel)
        else:
            _fail(rel, "missing")


# ── 2. Compatibility wrappers contain runpy ──────────────────────────
def check_wrappers() -> None:
    print("\n2. Compatibility wrappers (old locations → runpy redirect)")
    wrappers = {
        "scripts/audit_exp21.py":                 "scripts.audit.audit_exp21",
        "scripts/audit_exp15c.py":                "scripts.audit.audit_exp15c",
        "scripts/master_runner.py":               "scripts.runner.master_runner",
        "scripts/generate_hpc_jobs.py":           "scripts.runner.generate_hpc_jobs",
        "scripts/analysis_pack.py":               "scripts.analysis.analysis_pack",
        "scripts/generate_demo_pack.py":          "scripts.analysis.generate_demo_pack",
        "scripts/publish_exp13b_final_decision.py": "scripts.publish.publish_exp13b_final_decision",
    }
    for rel, target_mod in wrappers.items():
        p = REPO_ROOT / rel
        if not p.is_file():
            _fail(f"wrapper {rel}", "file not found")
            continue
        text = p.read_text()
        ok = True
        if "runpy" not in text:
            _fail(f"wrapper {rel}", "'runpy' not found in wrapper")
            ok = False
        if target_mod not in text:
            _fail(f"wrapper {rel}", f"target module '{target_mod}' not referenced")
            ok = False
        if "FutureWarning" not in text and "DeprecationWarning" not in text:
            _fail(f"wrapper {rel}", "no deprecation warning found")
            ok = False
        if ok:
            _pass(f"wrapper {rel}  →  {target_mod}")


# ── 3. CLI subcommand parsing (--help) ───────────────────────────────
def check_cli_parsing() -> None:
    print("\n3. CLI subcommand parsing (scripts.cli --help)")
    subcommands = [
        [],                     # top-level help
        ["run-exp", "--help"],
        ["audit", "--help"],
        ["publish", "--help"],
        ["smoke", "--help"],
        ["hpc-generate", "--help"],
    ]
    python = sys.executable
    for args in subcommands:
        label = "cli " + " ".join(args) if args else "cli (top-level --help)"
        cmd = [python, "-m", "scripts.cli"] + (args if args else ["--help"])
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                timeout=15,
                cwd=str(REPO_ROOT),
            )
            # argparse --help exits with 0
            if r.returncode == 0:
                _pass(label)
            else:
                _fail(label, f"exit {r.returncode}: {r.stderr.decode()[:200]}")
        except Exception as exc:
            _fail(label, str(exc))


# ── 4. New-location modules can be found by importlib ─────────────────
def check_modules_locatable() -> None:
    print("\n4. New-location modules locatable (importlib.util.find_spec)")
    modules = [
        "scripts.analysis.aggregate_exp15b",
        "scripts.analysis.analysis_pack",
        "scripts.analysis.generate_demo_pack",
        "scripts.audit.audit_exp21",
        "scripts.audit.audit_exp15c",
        "scripts.runner.master_runner",
        "scripts.runner.generate_hpc_jobs",
        "scripts.publish.publish_exp13b_final_decision",
        "scripts.cli",
    ]
    for mod in modules:
        spec = importlib.util.find_spec(mod)
        if spec is not None:
            _pass(f"find_spec({mod})")
        else:
            _fail(f"find_spec({mod})", "returned None")


# ── 5. ensure_src() contract ─────────────────────────────────────────
def check_ensure_src() -> None:
    print("\n5. scripts.ensure_src() contract")
    try:
        from scripts import ensure_src
        _pass("ensure_src is importable")
    except ImportError as e:
        _fail("ensure_src importable", str(e))
        return

    try:
        ensure_src(verbose=True)
        _pass("ensure_src() → src found")
    except ImportError:
        # Not fatal for the hygiene check — src may not be available
        # in every environment (CI, lightweight checkout, etc.)
        print("  [WARN] src package not importable (OK for hygiene-only check)")


# ── 6. REPO_ROOT exposed by scripts package ──────────────────────────
def check_repo_root() -> None:
    print("\n6. scripts.REPO_ROOT contract")
    try:
        import scripts as s
        rr = getattr(s, "REPO_ROOT", None)
        if rr is not None and Path(rr).is_dir():
            _pass(f"scripts.REPO_ROOT = {rr}")
        else:
            _fail("scripts.REPO_ROOT", f"value: {rr}")
    except Exception as exc:
        _fail("scripts.REPO_ROOT", str(exc))


# ── main ─────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 60)
    print("  Repo-hygiene acceptance test")
    print("=" * 60)

    check_init_files()
    check_wrappers()
    check_cli_parsing()
    check_modules_locatable()
    check_ensure_src()
    check_repo_root()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
