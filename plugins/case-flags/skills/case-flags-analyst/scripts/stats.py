#!/usr/bin/env python3
"""
Distribution statistics for every "compute the median in code" instruction in the skill.

The skill asks for a median in roughly a dozen places (§5 initial median, §7.3 per-owner
medians, §7.4 and §5 daily clear counts, §10.3 per-case means, §10.4 account initial,
§10.6 customer turnaround, Job E distributions, Job F per-bucket figures). All of them
want the same thing: a sorted-value reduction with n carried alongside so a thin sample
can be labelled low-confidence rather than presented at full authority.

Modes
  describe          median/mean/percentiles for a field, optionally grouped by another
  labor-per-clear   the Job C / Job B load weight, from §5 or §7.4 daily-clear-count rows

Why mean is reported next to median everywhere: the mean/median ratio is the tail signal
Job H thresholds at 1.5x, and a clean median sitting on one catastrophic case is the most
misleading read available. Both, always.

Usage
  python3 stats.py --input ir.json --field FLAGS__Initial_Response_Business_Hours__c
  python3 stats.py --input ir.json --field FLAGS__Initial_Response_Business_Hours__c \
      --group-by OwnerId --min-n 10
  python3 stats.py --input clears.json --mode labor-per-clear --group-by FLAGS__Owner__c
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from cfa_common import (
    MIN_WORKDAYS_FOR_CONFIDENCE,
    WORKDAY_HOURS,
    DataError,
    check_variance,
    describe,
    emit,
    fnum,
    get,
    load_records,
    median,
    require_columns,
    table,
    to_float,
)


def mode_describe(records, field, group_by, min_n) -> dict:
    require_columns(records, [field], f"stats --field {field}")
    if group_by:
        require_columns(records, [group_by], f"stats --group-by {group_by}")

    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        key = str(get(record, group_by, "(none)")) if group_by else "all"
        value = to_float(get(record, field))
        if value is not None:
            groups[key].append(value)

    if not groups:
        raise DataError(f"No numeric values found for {field}.")

    warnings = []
    for key, values in groups.items():
        variance = check_variance(values, f"{field} for {key}")
        if variance:
            warnings.append(variance)

    return {
        "mode": "describe",
        "field": field,
        "group_by": group_by,
        "groups": {k: describe(v, min_n) for k, v in sorted(groups.items())},
        "warnings": warnings,
    }


def mode_labor_per_clear(records, group_by, min_n) -> dict:
    """
    labor_per_clear = 8h / median(per-day clear count), per owner.

    Input is the §5 / §7.4 GROUP BY result: one row per owner per day with a clear count.
    Days with zero clears never appear in a GROUP BY, which is exactly the exclusion the
    metric wants -- weekends, PTO and OOO drop out with no extra filter.

    The median (not the mean) is deliberate: a backlog-clearing day or a half-day before
    PTO should not reshape what a typical workday looks like.
    """
    # Without this guard a typo'd --group-by falls through get()'s default and collapses
    # every owner into one bucket named "all", yielding a single pooled labor_per_clear
    # that looks entirely legitimate. describe mode has always checked this; this mode
    # silently did not.
    if group_by:
        require_columns(records, [group_by], f"stats --group-by {group_by}")

    count_field = None
    for candidate in ("clears", "expr0", "COUNT(Id)", "cnt", "count"):
        if any(candidate in r for r in records[:20]):
            count_field = candidate
            break
    if count_field is None:
        raise DataError(
            "Could not find the clear-count column. Expected an alias like 'clears' "
            "(as in `COUNT(Id) clears`) or the connector's default 'expr0'. "
            f"Columns present: {sorted(records[0])[:10]}"
        )

    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        key = str(get(record, group_by, "all")) if group_by else "all"
        value = to_float(get(record, count_field))
        if value is not None:
            groups[key].append(value)

    results = {}
    warnings = []
    for key, counts in sorted(groups.items()):
        workdays = len(counts)
        typical = median(counts)
        entry = {
            "distinct_workdays": workdays,
            "median_daily_clears": typical,
            "mean_daily_clears": (sum(counts) / workdays) if workdays else None,
            "labor_per_clear_hours": (WORKDAY_HOURS / typical) if typical else None,
            "clears_total": int(sum(counts)),
        }
        if workdays < min_n:
            entry["low_confidence"] = (
                f"only {workdays} distinct workdays in the window (threshold {min_n}) -- "
                "present this as low-confidence, not at full authority"
            )
            warnings.append(f"{key}: {entry['low_confidence']}")
        if not typical:
            entry["error"] = "median daily clears is zero -- cannot derive labor_per_clear"
        results[key] = entry

    return {
        "mode": "labor-per-clear",
        "workday_hours": WORKDAY_HOURS,
        "count_field_used": count_field,
        "groups": results,
        "note": "labor_per_clear is a throughput ratio, not a measured effort time. "
                "estimatedLoadHours = totalLoadSetCount * labor_per_clear.",
        "warnings": warnings,
    }


def render(payload: dict) -> None:
    if payload["mode"] == "labor-per-clear":
        print("== labor_per_clear (8h / median daily clears) ==\n")
        rows = []
        for key, entry in payload["groups"].items():
            flag = "low-conf" if "low_confidence" in entry else ""
            rows.append([
                key, entry["distinct_workdays"], entry["clears_total"],
                fnum(entry["median_daily_clears"], 1),
                fnum(entry["labor_per_clear_hours"]), flag,
            ])
        print(table(rows, ["Owner", "Workdays", "Clears", "Median/day",
                           "labor_per_clear (h)", "Note"]))
        print(f"\n{payload['note']}")
        return

    print(f"== {payload['field']} ==\n")
    rows = []
    for key, stats in payload["groups"].items():
        if not stats.get("n"):
            continue
        rows.append([
            key, stats["n"], fnum(stats["median"]), fnum(stats["mean"]),
            fnum(stats["p75"]), fnum(stats["p90"]), fnum(stats["max"]),
            fnum(stats["tail_ratio"], 1) + ("  tail" if (stats["tail_ratio"] or 0) >= 1.5 else ""),
            "low-conf" if "low_confidence" in stats else "",
        ])
    print(table(rows, ["Group", "n", "Median", "Mean", "p75", "p90", "Max",
                       "Mean/median", "Note"]))
    if any((s.get("tail_ratio") or 0) >= 1.5 for s in payload["groups"].values()):
        print("\nA mean/median ratio at or above 1.5 means a tail exists -- an outlier is "
              "present even where the median looks clean. Report both figures.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Distribution stats for case-flags-analyst")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mode", default="describe", choices=["describe", "labor-per-clear"])
    parser.add_argument("--field", default=None, help="numeric field to summarise")
    parser.add_argument("--group-by", default=None)
    parser.add_argument("--min-n", type=int, default=MIN_WORKDAYS_FOR_CONFIDENCE,
                        help=f"low-confidence threshold (default {MIN_WORKDAYS_FOR_CONFIDENCE})")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        records = load_records(args.input)
        if not records:
            print("No records in input.", file=sys.stderr)
            return 1

        if args.mode == "labor-per-clear":
            payload = mode_labor_per_clear(records, args.group_by, args.min_n)
        else:
            if not args.field:
                raise DataError("--field is required for describe mode")
            payload = mode_describe(records, args.field, args.group_by, args.min_n)

        emit(payload, args.json, render)
        return 0

    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
