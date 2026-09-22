#!/usr/bin/env python3
"""Re-download a previously-triggered PitchBook snapshot.

Note: lookup_company.py uses the synchronous /scrape endpoint and does NOT
produce a snapshot_id. This script is only needed if you triggered a job
directly via the /trigger endpoint. Snapshots are retained 16 days after
the original trigger — re-downloading within that window is free.
"""
from __future__ import annotations

import argparse
import sys

from client import download, emit, progress


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download an existing Bright Data PitchBook snapshot by id.",
    )
    ap.add_argument(
        "--snapshot-id",
        required=True,
        help="Snapshot id from a previous /trigger call, e.g. s_m4x7enmven8djfqak.",
    )
    ap.add_argument(
        "--format",
        default="json",
        choices=["json", "ndjson", "jsonl", "csv"],
        help="Download format (default: json).",
    )
    ap.add_argument(
        "--status-only",
        action="store_true",
        help="Only check /progress; don't attempt to download.",
    )
    args = ap.parse_args()

    try:
        if args.status_only:
            emit(progress(args.snapshot_id))
            return
        rows = download(args.snapshot_id, format=args.format)
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    emit({"snapshot_id": args.snapshot_id, "returned": len(rows), "rows": rows})


if __name__ == "__main__":
    main()
