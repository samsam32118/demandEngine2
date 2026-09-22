"""Argparse flags shared by every TikTok task script.

Keeps --fields / --no-wait / --timeout / --poll-interval defined once so
the flags behave identically across scripts and the help text doesn't
drift.
"""
from __future__ import annotations

import argparse


def add_common_args(ap: argparse.ArgumentParser, *, timeout: float = 600.0) -> None:
    ap.add_argument(
        "--fields",
        help="Comma-separated subset of output fields. Defaults to the full "
        "record — leave it off unless context pressure forces a trim "
        "(trimming does not reduce billing).",
    )
    ap.add_argument(
        "--no-wait",
        action="store_true",
        help="Return the snapshot_id immediately without polling. Use "
        "get_snapshot.py later to fetch results.",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=timeout,
        help=f"Seconds to wait for the snapshot before giving up "
        f"(default: {timeout:.0f}).",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds between /progress polls (default: 10).",
    )


def add_limit_arg(ap: argparse.ArgumentParser, *, required: bool = True) -> None:
    ap.add_argument(
        "--limit-per-input",
        type=int,
        required=required,
        help="Max records returned per input. The main cost guard for "
        "discovery — start small (25) and expand only on request.",
    )
