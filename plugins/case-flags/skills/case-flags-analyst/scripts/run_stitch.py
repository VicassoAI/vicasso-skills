#!/usr/bin/env python3
"""
Reconstruct contiguous flag-up RUNS from raw CFHT records.

One implementation of the walk that references/field-reference.md ("Ongoing-response time --
compute per RUN, not per record"), references/followup-time-investment.md (opening-trigger
classification), job-d (vitals) and job-h (worst wait, customer turnaround) all
describe separately in prose.

A run = a maximal contiguous stretch of FLAGS__Flag_Set__c = true records for one
case, read in FLAGS__Start__c order. Its BH total is the sum of the intervals, which
is the real response time for that cycle -- a per-record reading understates it
whenever a status or owner change split the cycle mid-flight.

Modes
  runs            every reconstructed run (inspection / feeding other steps)
  ongoing         ongoing-response time, both documented methods side by side:
                  (a) median of per-case means, (b) median of run totals
  followup-split  genuine clears bucketed by opening trigger (Follow-Up Process vs
                  other), per owner, plus the same-day batching gap
  worst-run       longest run per case and overall (job-h worst wait)
  down-intervals  customer-court turnaround: flag-DOWN interval stats, excluding the
                  trailing post-resolution dwell

Input: JSON from references/soql-followup-investment.md §8 (or references/soql-account.md
§10.6 / references/soql-timeline.md §6), ordered by case then Start.
Required SELECT: FLAGS__Case__c, FLAGS__Start__c, FLAGS__Flag_Set__c, FLAGS__Event__c,
FLAGS__Action__c, and -- for anything involving duration --
FLAGS__Business_Hours_Elapsed__c.

Usage
  python3 run_stitch.py --input cfht.json --mode ongoing
  python3 run_stitch.py --input cfht.json --mode followup-split --group-by FLAGS__Owner__c
  python3 run_stitch.py --input cfht.json --mode worst-run --json
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from cfa_common import (
    DataError,
    check_variance,
    describe,
    emit,
    fnum,
    get,
    load_records,
    median,
    parse_dt,
    require_columns,
    table,
    to_float,
)

CASE = "FLAGS__Case__c"
START = "FLAGS__Start__c"
END = "FLAGS__End__c"
FLAG_SET = "FLAGS__Flag_Set__c"
EVENT = "FLAGS__Event__c"
ACTION = "FLAGS__Action__c"
BH = "FLAGS__Business_Hours_Elapsed__c"

FOLLOW_UP_TRIGGER = "Follow-Up Process"
CASE_CLOSED = "Case Closed"
FLAG_CLEARED = "Flag Cleared"


def truthy(value) -> bool:
    """Flag_Set arrives as a real bool from most connectors, as a string from some."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "1"}
    return bool(value)


def build_runs(records: list[dict], need_bh: bool = True) -> list[dict]:
    """
    Group records into per-case flag-up runs.

    Each run carries its opening trigger (the Action of the record immediately BEFORE
    the run began -- that record's Event = 'Flag Set' describes the transition into
    this run) and its closing shape, so downstream modes never re-walk the raw data.

    A run starting at the case's very first record has no preceding record, so it has
    no readable opening trigger: flagged at creation. references/field-reference.md is explicit
    that these are excluded from the follow-up/other split rather than guessed at.
    """
    require_columns(records, [CASE, START, FLAG_SET, EVENT, ACTION], "run_stitch")
    if need_bh:
        require_columns(records, [BH], "run_stitch (duration mode)")

    by_case: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        case_id = get(record, CASE)
        if case_id:
            by_case[case_id].append(record)

    runs: list[dict] = []
    for case_id, case_records in by_case.items():
        # Re-sort defensively: relying on the caller's ORDER BY is how off-by-one
        # walks creep in, and sorting a few thousand rows is free.
        case_records.sort(key=lambda r: (parse_dt(get(r, START)) or parse_dt("1900-01-01")))

        index = 0
        total = len(case_records)
        while index < total:
            if not truthy(get(case_records[index], FLAG_SET)):
                index += 1
                continue

            start_index = index
            while index < total and truthy(get(case_records[index], FLAG_SET)):
                index += 1
            run_records = case_records[start_index:index]
            last = run_records[-1]

            preceding = case_records[start_index - 1] if start_index > 0 else None
            closing_event = get(last, EVENT)
            closing_action = get(last, ACTION)
            is_close = closing_action == CASE_CLOSED

            runs.append(
                {
                    "case": case_id,
                    "case_number": get(run_records[0], "FLAGS__Case__r.CaseNumber"),
                    "owner": get(run_records[0], "FLAGS__Owner__c"),
                    "owner_name": get(run_records[0], "FLAGS__Owner_Name__c"),
                    "start": get(run_records[0], START),
                    "end": get(last, END),
                    "intervals": len(run_records),
                    "bh_total": sum(to_float(get(r, BH)) or 0.0 for r in run_records),
                    "max_interval_bh": max(
                        (to_float(get(r, BH)) or 0.0) for r in run_records
                    ),
                    "opening_trigger": get(preceding, ACTION) if preceding else None,
                    "flagged_at_creation": preceding is None,
                    "closing_event": closing_event,
                    "closing_action": closing_action,
                    # A genuine clear is a human reply. The Flag Cleared + Case Closed
                    # shape is close housekeeping and is excluded everywhere.
                    "genuine_clear": closing_event == FLAG_CLEARED and not is_close,
                    "housekeeping_close": is_close,
                    "closed_run": is_close,
                }
            )

    runs.sort(key=lambda r: (str(r["case"]), str(r["start"])))
    return runs


def collect_warnings(runs: list[dict], records: list[dict]) -> list[str]:
    warnings = []
    variance = check_variance([r["bh_total"] for r in runs], "run BH total")
    if variance:
        warnings.append(variance)
    if runs and all(r["bh_total"] == 0 for r in runs):
        warnings.append(
            f"All {len(runs)} runs computed to 0.00 BH. Confirm {BH} was in the SELECT "
            "list and actually populated -- an all-zero column is a data bug, not a finding."
        )
    orphans = sum(1 for r in runs if r["flagged_at_creation"])
    if orphans:
        warnings.append(
            f"{orphans} run(s) start at the case's first record (flagged at creation) so they "
            "have no readable opening trigger; excluded from the follow-up/other split."
        )
    return warnings


# ------------------------------------------------------------------------------- modes


def mode_ongoing(runs: list[dict]) -> dict:
    """
    Ongoing-response time by both documented methods.

    (a) median of per-case means -- reconciles with the two-GROUP-BY approximation.
    (b) median of run totals     -- the precise per-cycle figure.
    Reporting both makes the gap visible instead of implicit.
    """
    genuine = [r for r in runs if r["genuine_clear"]]

    per_case: dict[str, list[float]] = defaultdict(list)
    for run in genuine:
        per_case[run["case"]].append(run["bh_total"])

    case_means = [sum(v) / len(v) for v in per_case.values() if v]

    return {
        "mode": "ongoing",
        "runs_total": len(runs),
        "genuine_clear_runs": len(genuine),
        "cases_with_genuine_clears": len(per_case),
        "method_a_median_of_per_case_means": median(case_means),
        "method_a_detail": describe(case_means),
        "method_b_median_of_run_totals": median([r["bh_total"] for r in genuine]),
        "method_b_detail": describe([r["bh_total"] for r in genuine]),
    }


def mode_followup_split(runs: list[dict], group_by: str | None) -> dict:
    """
    Bucket genuine clears by opening trigger, per group.

    Counts only. references/field-reference.md and references/followup-time-investment.md both record that
    run BH-elapsed does NOT separate follow-up from other clears (tested live: medians
    23 vs 15 min, means ~41 both ways) because it measures wait, not labour. So the
    time-per-clear half comes from references/labor-assumptions.md, never from here.
    """
    groups: dict[str, dict] = defaultdict(
        lambda: {"followup_clears": 0, "other_clears": 0, "excluded_at_creation": 0,
                 "followup_end_times": []}
    )

    for run in runs:
        key = (run.get("owner_name") or run.get("owner") or "all") if group_by else "all"
        bucket = groups[key]

        if not run["genuine_clear"]:
            continue
        if run["flagged_at_creation"]:
            bucket["excluded_at_creation"] += 1
            continue

        if run["opening_trigger"] == FOLLOW_UP_TRIGGER:
            bucket["followup_clears"] += 1
            bucket["followup_end_times"].append(run["end"])
        else:
            bucket["other_clears"] += 1

    results = {}
    for key, bucket in groups.items():
        results[key] = {
            "followup_clears": bucket["followup_clears"],
            "other_clears": bucket["other_clears"],
            "excluded_at_creation": bucket["excluded_at_creation"],
            "batching": batching_gap(bucket["followup_end_times"]),
        }

    return {"mode": "followup-split", "groups": results,
            "note": "Counts only -- apply declared minutes from references/labor-assumptions.md "
                    "to convert to hours. Run BH is NOT a labour proxy."}


def batching_gap(end_times: list) -> dict:
    """
    Median gap between consecutive same-day follow-up clears (3+ on a day).

    references/followup-time-investment.md step 3: informational only. Never silently adjust the
    declared minutes from this -- it is a prompt for the person to reconsider their own
    number, and back-to-back timestamps undercount effort when several are drafted
    before sending.
    """
    by_day: dict[str, list] = defaultdict(list)
    for value in end_times:
        parsed = parse_dt(value)
        if parsed:
            by_day[parsed.date().isoformat()].append(parsed)

    gaps: list[float] = []
    batch_days = 0
    for stamps in by_day.values():
        if len(stamps) < 3:
            continue
        batch_days += 1
        stamps.sort()
        gaps.extend(
            (stamps[i] - stamps[i - 1]).total_seconds() / 60.0 for i in range(1, len(stamps))
        )

    if not gaps:
        return {"batching_days": 0, "median_gap_minutes": None,
                "note": "no days with 3+ follow-up clears -- no batching pattern, which is "
                        "a perfectly ordinary result"}
    return {"batching_days": batch_days, "median_gap_minutes": median(gaps),
            "gaps_sampled": len(gaps),
            "note": "informational only -- do not adjust declared minutes from this"}


def mode_worst_run(runs: list[dict], stall_bar: float | None) -> dict:
    """
    Longest continuous our-court wait (job-h). A worst RUN, not a worst interval.

    When a stall bar is supplied (the org's ET3 offset from Preflight -- never a
    hardcoded number), classify the worst case as stall vs volume/iteration.
    """
    candidates = [r for r in runs if not r["housekeeping_close"]]
    if not candidates:
        return {"mode": "worst-run", "note": "no non-housekeeping runs"}

    worst = max(candidates, key=lambda r: r["bh_total"])

    per_case: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "intervals": 0, "max_run": 0.0})
    for run in candidates:
        entry = per_case[run["case"]]
        entry["total"] += run["bh_total"]
        entry["intervals"] += run["intervals"]
        entry["max_run"] = max(entry["max_run"], run["bh_total"])
        entry["case_number"] = run.get("case_number")

    ranked = sorted(per_case.items(), key=lambda kv: kv[1]["total"], reverse=True)
    side_total = sum(v["total"] for v in per_case.values())

    result = {
        "mode": "worst-run",
        "worst_run": {k: worst[k] for k in
                      ("case", "case_number", "start", "end", "intervals", "bh_total")},
        "side_total_bh": side_total,
        "top_cases": [
            {"case": case, "case_number": v.get("case_number"), "total_bh": v["total"],
             "intervals": v["intervals"], "longest_run_bh": v["max_run"],
             "share_of_side": (v["total"] / side_total) if side_total else None}
            for case, v in ranked[:5]
        ],
    }

    if stall_bar is not None:
        longest = worst["bh_total"]
        result["stall_bar_bh"] = stall_bar
        result["classification"] = "stall" if longest >= stall_bar else "volume/iteration"
        result["classification_note"] = (
            f"longest continuous wait {fnum(longest)} BH >= stall bar {fnum(stall_bar)} BH: one "
            "unbroken wait long enough to age into red -- a genuine dropped ball"
            if longest >= stall_bar else
            f"longest continuous wait {fnum(longest)} BH is under the {fnum(stall_bar)} BH stall "
            "bar: heavy total spread across many rounds, fast per reply -- NOT a dropped ball"
        )
    return result


def mode_down_intervals(records: list[dict]) -> dict:
    """
    Customer-court turnaround: flag-DOWN interval stats.

    Excludes the trailing post-resolution dwell (Action = 'Case Closed'), which would
    otherwise inflate the account's apparent slowness with pending-closure time.
    """
    require_columns(records, [FLAG_SET, ACTION, BH], "run_stitch down-intervals")

    values, excluded = [], 0
    for record in records:
        if truthy(get(record, FLAG_SET)):
            continue
        if get(record, ACTION) == CASE_CLOSED:
            excluded += 1
            continue
        value = to_float(get(record, BH))
        if value is not None:
            values.append(value)

    return {
        "mode": "down-intervals",
        "excluded_post_resolution": excluded,
        "turnaround": describe(values),
        "worst_gap_bh": max(values) if values else None,
    }


# ------------------------------------------------------------------------------ render


def render(payload: dict) -> None:
    mode = payload.get("mode")
    print(f"== run_stitch: {mode} ==\n")

    if mode == "ongoing":
        print(f"runs {payload['runs_total']} | genuine clears {payload['genuine_clear_runs']} "
              f"| cases {payload['cases_with_genuine_clears']}\n")
        print(table(
            [
                ["(a) median of per-case means",
                 fnum(payload["method_a_median_of_per_case_means"]),
                 payload["method_a_detail"].get("n")],
                ["(b) median of run totals",
                 fnum(payload["method_b_median_of_run_totals"]),
                 payload["method_b_detail"].get("n")],
            ],
            ["Method", "BH", "n"],
        ))
        detail = payload["method_b_detail"]
        if detail.get("n"):
            print(f"\nrun totals: p25 {fnum(detail['p25'])} | p75 {fnum(detail['p75'])} "
                  f"| p90 {fnum(detail['p90'])} | max {fnum(detail['max'])} "
                  f"| tail ratio {fnum(detail['tail_ratio'])}")

    elif mode == "followup-split":
        rows = []
        for key, value in sorted(payload["groups"].items()):
            gap = value["batching"]["median_gap_minutes"]
            rows.append([
                key, value["followup_clears"], value["other_clears"],
                value["excluded_at_creation"],
                f"{fnum(gap, 1)} min" if gap is not None else "none",
            ])
        print(table(rows, ["Group", "Follow-up clears", "Other clears",
                           "Excluded (at creation)", "Batching gap"]))
        print(f"\n{payload['note']}")

    elif mode == "worst-run":
        if "worst_run" in payload:
            worst = payload["worst_run"]
            print(f"worst continuous wait: {fnum(worst['bh_total'])} BH "
                  f"({worst['intervals']} interval(s)) on case "
                  f"{worst.get('case_number') or worst['case']}")
            if "classification" in payload:
                print(f"classification: {payload['classification'].upper()}")
                print(f"  {payload['classification_note']}")
            print(f"\nside total {fnum(payload['side_total_bh'])} BH\n")
            print(table(
                [[c.get("case_number") or c["case"], fnum(c["total_bh"]), c["intervals"],
                  fnum(c["longest_run_bh"]),
                  f"{(c['share_of_side'] or 0) * 100:.1f}%"] for c in payload["top_cases"]],
                ["Case", "Total BH", "Intervals", "Longest run", "Share"],
            ))
        else:
            print(payload.get("note", ""))

    elif mode == "down-intervals":
        stats = payload["turnaround"]
        print(f"excluded post-resolution dwell rows: {payload['excluded_post_resolution']}\n")
        print(f"n {stats.get('n')} | median {fnum(stats.get('median'))} BH "
              f"| mean {fnum(stats.get('mean'))} BH | worst gap "
              f"{fnum(payload.get('worst_gap_bh'))} BH")

    else:
        rows = [[r.get("case_number") or r["case"], r["intervals"], fnum(r["bh_total"]),
                 r["opening_trigger"] or "(at creation)",
                 "yes" if r["genuine_clear"] else "no"] for r in payload["runs"][:40]]
        print(table(rows, ["Case", "Intervals", "BH", "Opening trigger", "Genuine clear"]))
        if len(payload["runs"]) > 40:
            print(f"\n+{len(payload['runs']) - 40} more runs (use --json for all)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stitch CFHT records into flag-up runs")
    parser.add_argument("--input", required=True, help="JSON file of CFHT records")
    parser.add_argument("--mode", default="ongoing",
                        choices=["runs", "ongoing", "followup-split", "worst-run",
                                 "down-intervals"])
    parser.add_argument("--group-by", default=None,
                        help="group followup-split by owner (pass FLAGS__Owner__c)")
    parser.add_argument("--stall-bar", type=float, default=None,
                        help="worst-run: org ET3 offset in BH from Preflight "
                             "(FLAGS__TimeOffset3__c). Never hardcode this.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        records = load_records(args.input)
        if not records:
            print("No records in input.", file=sys.stderr)
            return 1

        if args.mode == "down-intervals":
            payload = mode_down_intervals(records)
            payload["warnings"] = []
        else:
            runs = build_runs(records)
            warnings = collect_warnings(runs, records)
            if args.mode == "runs":
                payload = {"mode": "runs", "runs": runs}
            elif args.mode == "ongoing":
                payload = mode_ongoing(runs)
            elif args.mode == "followup-split":
                payload = mode_followup_split(runs, args.group_by)
            else:
                payload = mode_worst_run(runs, args.stall_bar)
            payload["warnings"] = warnings

        emit(payload, args.json, render)
        return 0

    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
