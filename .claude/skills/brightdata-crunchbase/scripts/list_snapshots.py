#!/usr/bin/env python3
"""List recent Bright Data snapshots for the Crunchbase dataset.

Handy for recovering a snapshot_id you forgot to save, or checking
what's still within the 16-day retention window. This endpoint is
metadata-only and does not bill anything.
"""
from __future__ import annotations

import argparse
import sys

from client import CRUNCHBASE_DATASET_ID, emit, list_snapshots


def main() -> None:
    ap = argparse.ArgumentParser(
        description="List recent Crunchbase snapshots on this Bright Data account.",
    )
    ap.add_argument(
        "--status",
        choices=["ready", "running", "failed", "starting"],
        help="Filter snapshots by status.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max snapshots to return (default: 20).",
    )
    ap.add_argument(
        "--all-datasets",
        action="store_true",
        help="Return snapshots for every dataset, not just Crunchbase.",
    )
    args = ap.parse_args()

    dataset_id = None if args.all_datasets else CRUNCHBASE_DATASET_ID
    try:
        snapshots = list_snapshots(
            dataset_id=dataset_id, status=args.status, limit=args.limit
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    emit({"count": len(snapshots), "snapshots": snapshots})


if __name__ == "__main__":
    main()
