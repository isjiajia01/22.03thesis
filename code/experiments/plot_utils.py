# -*- coding: utf-8 -*-
"""
plot_utils.py — minimal plotting helpers (matplotlib only)

Notes
- Uses a non-interactive backend ("Agg") so it won't hang on headless runs.
- Keeps the API intentionally small and stable across experiments.
"""
from __future__ import annotations

from typing import Optional, Sequence

import os
import matplotlib
matplotlib.use("Agg")  # IMPORTANT: avoid UI backend freezes
import matplotlib.pyplot as plt
import pandas as pd


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def plot_bars(
    df: pd.DataFrame,
    x: str,
    y: str,
    out_path: str,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    yerr: Optional[str] = None,
):
    """
    Simple bar plot helper.

    Parameters
    ----------
    df : DataFrame
        Must contain columns [x, y] and optionally [yerr].
    x, y : str
        Column names.
    out_path : str
        Output png path.
    yerr : Optional[str]
        Column name for error bars (std). If provided, NaN will be treated as 0.
    """
    _ensure_dir(out_path)
    data = df.copy().sort_values(by=[x]).reset_index(drop=True)

    err = None
    if yerr is not None and yerr in data.columns:
        err = data[yerr].fillna(0.0).astype(float).tolist()

    xs = data[x].astype(str).tolist()
    ys = data[y].astype(float).tolist()

    plt.figure()
    plt.bar(xs, ys, yerr=err, capsize=6 if err is not None else 0)

    if title:
        plt.title(title)
    plt.xlabel(xlabel or x)
    plt.ylabel(ylabel or y)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_lines(
    df: pd.DataFrame,
    x: str,
    y: str,
    group: Optional[str],
    out_path: str,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    x_rotate: int = 45,
    marker: str = "o",
):
    """
    Multi-line plot helper.

    Parameters
    ----------
    df : DataFrame
        Must contain columns [x, y] and optionally [group].
    group : Optional[str]
        If provided, draws one line per unique value in df[group].
        If None, draws a single line.
    """
    _ensure_dir(out_path)
    data = df.copy()

    # preserve x ordering (assume x is already ordered), else sort
    try:
        data = data.sort_values(by=[x] + ([group] if group else []))
    except Exception:
        data = data.sort_values(by=[x])

    plt.figure()

    if group is None:
        plt.plot(data[x].astype(str), data[y].astype(float), marker=marker)
    else:
        for g, sub in data.groupby(group):
            plt.plot(sub[x].astype(str), sub[y].astype(float), marker=marker, label=str(g))
        plt.legend()

    if title:
        plt.title(title)
    plt.xlabel(xlabel or x)
    plt.ylabel(ylabel or y)
    plt.xticks(rotation=x_rotate)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()
