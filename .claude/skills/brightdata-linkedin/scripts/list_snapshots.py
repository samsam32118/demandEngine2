#!/usr/bin/env python3
"""List recent Bright Data snapshots for the LinkedIn datasets.

Handy for recovering a snapshot_id you forgot to save, or checking
what's still within the 16-day retention window. This endpoint is
metadata-only and does not bill anything.

Default scope is all four LinkedIn datasets (people, company, jobs,
posts). Pass --kind to narrow to a single dataset, or --all-datasets
to include non-LinkedIn ones on the same Bright Data account.
"""
from __future__ import annotations

import argparse
import sys

from client import DATASETS, emit, list_snapshots, resolve_dataset


def main() -> None:
    ap = argparse.ArgumentParser(
        description="List recent LinkedIn snapshots on this Bright Data account.",
    )
    ap.add_argument(
        "--kind",
        choices=sorted(DATASETS),
        help="Narrow to a single LinkedIn dataset (people|company|jobs|posts). "
        "Default: all four LinkedIn datasets.",
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
        help="Max snapshots to return per dataset (default: 20).",
    )
    ap.add_argument(
        "--all-datasets",
        action="store_true",
        help="Return snapshots for every dataset on this account, not just "
        "the LinkedIn four.",
    )
    args = ap.parse_args()

    try:
        if args.all_datasets:
            snapshots = list_snapshots(
                dataset_id=None, status=args.status, limit=args.limit
            )
            emit({"scope": "all_datasets", "count": len(snapshots), "snapshots": snapshots})
            return

        if args.kind:
            dataset_ids = {args.kind: resolve_dataset(args.kind)}
        else:
            dataset_ids = dict(DATASETS)

        grouped: dict[str, list] = {}
        total = 0
        for kind, ds_id in dataset_ids.items():
            snaps = list_snapshots(
                dataset_id=ds_id, status=args.status, limit=args.limit
            )
            grouped[kind] = snaps
            total += len(snaps)

        emit({"scope": "linkedin", "count": total, "by_kind": grouped})
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
