#!/usr/bin/env python3
"""Re-download a previously-triggered Crunchbase snapshot.

Use this to pull results from a snapshot_id you got back earlier —
either because you used --no-wait, because the poll timed out, or
because you want the data again without re-triggering (and re-billing)
the scrape. Snapshots are retained 16 days; after that this fails.
"""
from __future__ import annotations

import argparse
import sys

from client import download, emit, progress


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download an existing Bright Data snapshot by id.",
    )
    ap.add_argument(
        "--snapshot-id",
        required=True,
        help="Snapshot id from a previous trigger, e.g. s_m4x7enmven8djfqak.",
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
