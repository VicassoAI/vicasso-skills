#!/usr/bin/env python3
"""
Merge, dedupe and validate paginated CFHT pulls, then cache the result for the session.

Named "merge" rather than "fetch" deliberately: this script cannot query Salesforce. The
MCP connector holds the authenticated session, so records arrive through the connector and
get written to JSON; this handles everything mechanical that happens after that.

What it enforces (references/soql-assignment-split.md §9.2, job-f "Pagination trap"):
  * dedupe by record Id across pages -- overlapping pages are normal with the
    LIMIT 2000 / OFFSET 2000 / DESC-tail pattern
  * confirm the deduped count against a separate COUNT(Id), which job-f requires before
    trusting any split numbers
  * fail on absent required columns (the silent-zero trap) before anything downstream
    computes a wrong answer from them
  * report the FLAGS__Start__c span actually covered, so a page gap is visible rather
    than quietly shortening the window

Caching matters for real token cost: references/soql-followup-investment.md §8 advises pulling once and reusing
across jobs in a session, but with no mechanism that stayed aspirational. Writing a
canonical file into the session cache makes reuse actual -- a My Day read followed by a
follow-up question does not need to re-pull and re-emit the same 4,000 records. The cache
is a per-user 0700 directory under the OS temp dir and the run prints its path; see
cfa_common.session_cache_dir() for why it is not a fixed /tmp path.

Usage
  python3 cfht_merge.py --pages p1.json p2.json p3.json \
      --expect-count 4193 --label rep-90d
  python3 cfht_merge.py --pages p1.json --require FLAGS__Owner__c --label owner-90d
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from cfa_common import (
    DataError,
    emit,
    get,
    load_records,
    parse_dt,
    require_columns,
    session_cache_dir,
    table,
    write_json_private,
)

DEFAULT_REQUIRED = [
    "Id",
    "FLAGS__Case__c",
    "FLAGS__Start__c",
    "FLAGS__Business_Hours_Elapsed__c",
]


def merge(paths: list[str]) -> tuple[list[dict], dict]:
    seen: dict[str, dict] = {}
    per_page = []
    duplicates = 0
    missing_id = 0

    for path in paths:
        records = load_records(path)
        page_new = 0
        for record in records:
            record_id = get(record, "Id")
            if not record_id:
                # Without an Id there is no dedupe key; keep it but flag it, since an
                # aggregate query result should not be going through this script at all.
                missing_id += 1
                continue
            if record_id in seen:
                duplicates += 1
            else:
                seen[record_id] = record
                page_new += 1
        per_page.append({"file": os.path.basename(path), "rows": len(records),
                         "new": page_new})

    stats = {
        "pages": per_page,
        "rows_read": sum(p["rows"] for p in per_page),
        "unique_records": len(seen),
        "duplicates_dropped": duplicates,
        "rows_without_id": missing_id,
    }
    return list(seen.values()), stats


def window_coverage(records: list[dict]) -> dict:
    stamps = sorted(
        s for s in (parse_dt(get(r, "FLAGS__Start__c")) for r in records) if s
    )
    if not stamps:
        return {"earliest_start": None, "latest_start": None, "days_spanned": None}
    return {
        "earliest_start": stamps[0].isoformat(),
        "latest_start": stamps[-1].isoformat(),
        "days_spanned": (stamps[-1].date() - stamps[0].date()).days + 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and validate paginated CFHT pulls")
    parser.add_argument("--pages", nargs="+", required=True, help="page JSON files in any order")
    parser.add_argument("--expect-count", type=int, default=None,
                        help="COUNT(Id) from the same WHERE clause, for reconciliation")
    parser.add_argument("--require", nargs="*", default=None,
                        help=f"required columns (default: {' '.join(DEFAULT_REQUIRED)})")
    parser.add_argument("--label", default="cfht",
                        help="cache filename stem, e.g. rep-90d")
    parser.add_argument("--out", default=None, help="explicit output path (overrides --label)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        records, stats = merge(args.pages)
        if not records:
            raise DataError("No records with an Id across the supplied pages.")

        required = args.require if args.require is not None else DEFAULT_REQUIRED
        require_columns(records, required, "merged CFHT pull")

        if args.out:
            out_path = args.out
        else:
            out_path = os.path.join(session_cache_dir(), f"{args.label}.json")
        # 0600: the cache holds real case data, not scratch.
        write_json_private(out_path, records)

        warnings = []
        if stats["rows_without_id"]:
            warnings.append(
                f"{stats['rows_without_id']} row(s) had no Id and were dropped -- aggregate "
                "query results should not go through this script."
            )

        reconciliation = None
        if args.expect_count is not None:
            delta = len(records) - args.expect_count
            reconciliation = {
                "expected": args.expect_count,
                "merged": len(records),
                "delta": delta,
                "passed": delta == 0,
            }
            if delta < 0:
                warnings.append(
                    f"MISSING {abs(delta)} record(s): merged {len(records)} against a COUNT(Id) "
                    f"of {args.expect_count}. Pull the remaining page(s) before computing "
                    "anything -- job-f requires this check to pass first. If two pages already "
                    "reach ~4000, use the ORDER BY ... DESC LIMIT n tail query."
                )
            elif delta > 0:
                warnings.append(
                    f"{delta} MORE record(s) than the COUNT(Id) of {args.expect_count}. Usually "
                    "the count and the pages were run against different WHERE clauses or "
                    "windows -- verify they match."
                )

        # A single page landing exactly on the cap almost always means more pages exist.
        for page in stats["pages"]:
            if page["rows"] == 2000:
                warnings.append(
                    f"{page['file']} returned exactly 2000 rows -- the hard page cap. There is "
                    "almost certainly another page; OFFSET is itself capped at 2000, so use the "
                    "DESC-tail query beyond ~4000 records."
                )

        payload = {
            "merge": stats,
            "coverage": window_coverage(records),
            "reconciliation": reconciliation,
            "cache_path": out_path,
            "columns": sorted({k for r in records[:50] for k in r}),
            "cases": len(Counter(get(r, "FLAGS__Case__c") for r in records)),
            "warnings": warnings,
        }

        def render(data: dict) -> None:
            print("== CFHT merge ==\n")
            print(table(
                [[p["file"], p["rows"], p["new"]] for p in data["merge"]["pages"]],
                ["Page", "Rows", "New"],
            ))
            merge_stats = data["merge"]
            print(f"\nread {merge_stats['rows_read']} rows -> "
                  f"{merge_stats['unique_records']} unique "
                  f"({merge_stats['duplicates_dropped']} duplicates dropped)")
            print(f"distinct cases: {data['cases']}")

            recon = data["reconciliation"]
            if recon:
                verdict = "PASS" if recon["passed"] else f"*** OFF BY {recon['delta']:+d} ***"
                print(f"count reconciliation: {verdict} "
                      f"(expected {recon['expected']}, merged {recon['merged']})")

            cover = data["coverage"]
            if cover["earliest_start"]:
                print(f"Start span: {cover['earliest_start'][:10]} -> "
                      f"{cover['latest_start'][:10]} ({cover['days_spanned']} days)")
            print(f"\ncached: {data['cache_path']}")
            print("Reuse this path for other jobs this session instead of re-pulling.")

        emit(payload, args.json, render)
        if reconciliation and not reconciliation["passed"]:
            return 3
        return 0

    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
