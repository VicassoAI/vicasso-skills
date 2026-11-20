#!/usr/bin/env python3
"""
True Case Age -- break a case's age into WHOSE COURT the time was spent in.

Standard Salesforce Age is one undifferentiated number (created -> now/closed). CFHT
records every interval with Flag_Set (our court vs the customer's), status, owner,
queue, and band time, so the same elapsed time can be decomposed. Semantics are
canonical in references/job-i-true-case-age.md; this script owns the arithmetic.

Buckets (every CFHT interval lands in exactly one top-level bucket):
  our_court        flag UP   -- the customer is waiting on us
    of which queue       flag up while a queue held the case (Queue_Id populated)
    of which past_sla    flag up time in the L4 band (Business_Hours_in_Age_4)
  customer_court   flag DOWN -- we are waiting on the customer
  post_resolution  the flag-down STRETCH that ends in the case's final close, plus any
                   flag-down interval in a status passed via --resolved-statuses
                   (e.g. "Pending Closure": resolved, waiting out a close timer)
                   (Action = 'Case Closed', Flag_Set = false): resolved, not yet closed
  closed_gap       flag-down intervals that START right after a non-final close and
                   run until the reopen -- the case sat closed, then came back
  after_close      every interval AFTER the final close. Cases can keep working while
                   still closed (a customer emails a closed case, or a "closed" status
                   such as "Bug Fix Pending" is used as a parking spot). Salesforce's
                   Age stops at ClosedDate; this time is outside it. Flag-up time here
                   is reported separately as after_close_our_bh.

Per-interval aging speed: each CFHT record's BH follows the calendar of the aging
speed in effect for THAT interval (verified live). A case whose speed changed has BH
from more than one calendar; the script flags it (mixed_speeds) because one BH is not
the same amount of working time on a 6-hour calendar as on a 10-hour one.

Modes
  case     per-case breakdown table (one row per case)
  cohort   medians/totals across cases, optional --group-by a Case field
  status   time in each status split by court (needs CFHT status tracking)
  backlog  OPEN cases from Case rows only (no CFHT): age buckets x flagged / follow-up /
           forgotten. Pass --cases only.

Required CFHT SELECT: FLAGS__Case__c, FLAGS__Start__c, FLAGS__End__c, FLAGS__Flag_Set__c,
FLAGS__Event__c, FLAGS__Action__c, FLAGS__Business_Hours_Elapsed__c, FLAGS__Hours_Elapsed__c.
Recommended: FLAGS__Owner_Name__c, FLAGS__Queue_Id__c, FLAGS__Case_Status__c,
FLAGS__Business_Hours_in_Age_4__c, FLAGS__Aging_Speed__c.
Do NOT use FLAGS__Hours_in_Age_4__c for SLA: it applies the band thresholds in
CALENDAR hours (verified live: 80 h "past SLA" on a case with 0 BH past SLA).

Usage
  python3 age_decompose.py --cfht cfht.json --cases cases.json --mode case
  python3 age_decompose.py --cfht cfht.json --cases cases.json --mode cohort --group-by Priority
  python3 age_decompose.py --cfht cfht.json --mode status --customer-statuses "With Customer"
  python3 age_decompose.py --cases open.json --mode backlog --followup-field Follow_Up_On__c
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone

from cfa_common import (
    DataError,
    cfht_sort_key,
    check_variance,
    describe,
    emit,
    fnum,
    get,
    load_records,
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
HRS = "FLAGS__Hours_Elapsed__c"
QUEUE = "FLAGS__Queue_Id__c"
STATUS = "FLAGS__Case_Status__c"
OWNER = "FLAGS__Owner_Name__c"
BH_L4 = "FLAGS__Business_Hours_in_Age_4__c"
SPEED = "FLAGS__Aging_Speed__c"

CASE_CLOSED = "Case Closed"
OWNER_CHANGED = "Case Owner Changed"

BUCKETS = ["our_court", "customer_court", "post_resolution", "closed_gap", "after_close"]
CASE_BH_ROLLUPS = [f"FLAGS__Business_Hours_Age_{n}__c" for n in range(1, 5)]

# Reconciliation tolerances (hours). Rounding in CFHT elapsed fields is sub-second.
ROLLUP_TOLERANCE_BH = 0.05
CALENDAR_TOLERANCE_H = 0.25


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "1"}
    return bool(value)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


# ------------------------------------------------------------------- decomposition


def infer_closed(case_id: str, records: list[dict]) -> bool:
    """
    Current open/closed state when Case.IsClosed was not supplied.

    CFHT never writes a running interval (verified live: 0 of 59 open cases had a record
    with End null), so "has an open-ended record" cannot tell open from closed. What CAN:
    no close event -> open; history ends on a close -> closed. A close followed by more
    activity is either a reopened open case or work on a still-closed case, and only
    Case.IsClosed can tell those apart.
    """
    closes = [i for i, r in enumerate(records) if get(r, ACTION) == CASE_CLOSED]
    if not closes:
        return False
    if closes[-1] == len(records) - 1:
        return True
    raise DataError(
        f"Case {case_id} has activity after its last close: it is either reopened (open) "
        "or was worked while still closed. Pass --cases with IsClosed so it is bucketed "
        "correctly (after-close vs closed gap)."
    )


def decompose_case(case_id: str, records: list[dict], is_closed: bool | None = None,
                   flagged_now: bool | None = None,
                   resolved_statuses: frozenset = frozenset()) -> dict:
    """
    Walk one case's intervals in Start order and assign each to a bucket.

    is_closed: the case's CURRENT state (Case.IsClosed). A reopened case that is open
    again still has close events in its history; none of them is "final", so nothing
    after them is after_close.

    Open cases: CFHT stops at the last transition; the time from the last record's End
    to now is not in CFHT at all. It is reported as since_last_change_cal (calendar
    hours; BH is not recorded), in the court given by Case.FLAGS__ViewedFlag__c.
    """
    records.sort(key=cfht_sort_key)
    if is_closed is None:
        is_closed = infer_closed(case_id, records)

    close_idx = [i for i, r in enumerate(records) if get(r, ACTION) == CASE_CLOSED]
    final_close = close_idx[-1] if (close_idx and is_closed) else None
    non_final = {i for i in close_idx if i != final_close}
    in_gap = False

    bh = {b: 0.0 for b in BUCKETS}
    cal = {b: 0.0 for b in BUCKETS}
    queue_bh = queue_cal = 0.0
    past_sla_bh = 0.0
    after_close_our_bh = 0.0
    open_tail_cal = 0.0
    speeds: list[str] = []
    owners: list[str] = []
    handoffs = 0
    # Waits, built in the same pass as the buckets so their totals equal the buckets.
    #   our wait       = a contiguous stretch of our_court records (the customer waited
    #                    on us once); "reply" when it ends in a genuine clear.
    #   customer wait  = a contiguous stretch of customer_court records, stitched across
    #                    status/owner changes. Time in a --resolved-statuses status inside
    #                    it is excluded but does not split it; a close, a closed gap,
    #                    after-close time or the flag going up ends it.
    our_waits: list[dict] = []
    cust_waits: list[dict] = []
    seg: str | None = None

    for i, rec in enumerate(records):
        rec_bh = to_float(get(rec, BH))
        rec_cal = to_float(get(rec, HRS))
        if get(rec, END) is None:
            # Not observed in live data, but never let a half-written record count.
            rec_bh, rec_cal = 0.0, 0.0
        rec_bh = rec_bh or 0.0
        rec_cal = rec_cal or 0.0
        if rec_bh < 0 or rec_cal < 0:
            raise ValueError(f"negative elapsed on case {case_id} record {i}")

        speed = get(rec, SPEED)
        if speed and speed not in speeds:
            speeds.append(speed)

        if final_close is not None and i > final_close:
            bucket = "after_close"
            if truthy(get(rec, FLAG_SET)):
                after_close_our_bh += rec_bh
        elif truthy(get(rec, FLAG_SET)):
            bucket = "our_court"
            if get(rec, QUEUE):
                queue_bh += rec_bh
                queue_cal += rec_cal
            past_sla_bh += to_float(get(rec, BH_L4)) or 0.0
        elif i == final_close or get(rec, STATUS) in resolved_statuses:
            # Flag down in a resolved status: nobody is waiting on anybody, the case is
            # done and waiting to close. Org-specific, so only when the caller says so.
            bucket = "post_resolution"
        elif in_gap:
            bucket = "closed_gap"
        else:
            bucket = "customer_court"

        # A closed gap runs from a non-final close until the flag next goes up
        # (the reopen). Several flag-down records can fall inside it.
        if truthy(get(rec, FLAG_SET)):
            in_gap = False
        if i in non_final:
            in_gap = True
        bh[bucket] += rec_bh
        cal[bucket] += rec_cal

        if bucket == "our_court":
            if seg != "our":
                our_waits.append({"bh": 0.0, "reply": False})
                seg = "our"
            our_waits[-1]["bh"] += rec_bh
            our_waits[-1]["reply"] = (get(rec, EVENT) == "Flag Cleared"
                                      and get(rec, ACTION) != CASE_CLOSED)
        elif bucket == "customer_court":
            if seg != "cust":
                cust_waits.append({"bh": 0.0, "cal": 0.0, "ended_by": None})
                seg = "cust"
            cust_waits[-1]["bh"] += rec_bh
            cust_waits[-1]["cal"] += rec_cal
            cust_waits[-1]["ended_by"] = get(rec, ACTION)
        elif i == final_close and seg == "cust":
            # The flag-down STRETCH that ends in the final close is the post-resolution
            # dwell, not just its last record: a status change minutes before the close
            # (seen live) would otherwise leave a stub "customer wait" behind. Same rule
            # run_stitch down-intervals applies.
            tail = cust_waits.pop()
            bh["customer_court"] -= tail["bh"]
            cal["customer_court"] -= tail["cal"]
            bh["post_resolution"] += tail["bh"]
            cal["post_resolution"] += tail["cal"]
            seg = None
        elif bucket == "post_resolution" and i != final_close:
            # Resolved-status time: skip it inside a customer wait, but the flag went
            # down, so an our-wait is over.
            if seg == "our":
                seg = None
        else:
            seg = None
        if get(rec, ACTION) == CASE_CLOSED:
            seg = None

        if get(rec, EVENT) == OWNER_CHANGED:
            handoffs += 1
        owner = get(rec, OWNER)
        if owner and (not owners or owners[-1] != owner):
            owners.append(owner)

    if not is_closed and records:
        last_end = max((parse_dt(get(r, END)) for r in records if get(r, END)), default=None)
        open_tail_cal = hours_between(last_end, now_utc()) or 0.0

    returns = sum(1 for k, o in enumerate(owners) if o in owners[:k])
    first = records[0] if records else {}

    def wait_summary(waits: list[dict]) -> dict:
        values = [w["bh"] for w in waits]
        return {"n": len(values), "total_bh": sum(values),
                "avg_bh": (sum(values) / len(values)) if values else None,
                "max_bh": max(values) if values else None}
    return {
        "case": case_id,
        "case_number": get(first, "FLAGS__Case__r.CaseNumber"),
        "intervals": len(records),
        "bh": bh,
        "cal": cal,
        "bh_total": sum(bh.values()),
        "cal_total": sum(cal.values()) + open_tail_cal,
        "queue_bh": queue_bh,
        "queue_cal": queue_cal,
        "past_sla_bh": past_sla_bh,
        "after_close_our_bh": after_close_our_bh,
        "speeds": speeds,
        "mixed_speeds": len(speeds) > 1,
        "open_tail_cal": open_tail_cal,
        "court_now": None if is_closed else (
            "unknown" if flagged_now is None else ("our_court" if flagged_now else "customer_court")),
        "closes": len(close_idx),
        "is_closed": is_closed,
        "waits_on_us": {**wait_summary(our_waits),
                        "replies": sum(1 for w in our_waits if w["reply"])},
        "waits_on_customer": {**wait_summary(cust_waits),
                              "ended_by_followup": sum(1 for w in cust_waits
                                                       if w["ended_by"] == "Follow-Up Process")},
        "handoffs": handoffs,
        "owner_returns": returns,
        "history_start": get(first, START),
    }


def decompose_all(cfht: list[dict], cases: list[dict] | None = None,
                  resolved_statuses: frozenset = frozenset()) -> list[dict]:
    require_columns(cfht, [CASE, START, END, FLAG_SET, EVENT, ACTION, BH, HRS], "age_decompose")
    closed, flagged = {}, {}
    for c in cases or []:
        if get(c, "IsClosed") is not None:
            closed[get(c, "Id")] = truthy(get(c, "IsClosed"))
        if "FLAGS__ViewedFlag__c" in c:
            flagged[get(c, "Id")] = get(c, "FLAGS__ViewedFlag__c") is not None
    by_case: dict[str, list[dict]] = defaultdict(list)
    for rec in cfht:
        if get(rec, CASE):
            by_case[get(rec, CASE)].append(rec)
    try:
        return [decompose_case(cid, recs, closed.get(cid), flagged.get(cid), resolved_statuses)
                for cid, recs in by_case.items()]
    except ValueError as error:
        raise SystemExit(_invalid(str(error)))


def _invalid(message: str) -> int:
    print(f"\nINVALID: {message}\n", file=sys.stderr)
    return 3


def attach_cases(rows: list[dict], cases: list[dict], warnings: list[str]) -> None:
    """Join Case fields, compute standard Age, and cross-check against Case rollups."""
    index = {get(c, "Id"): c for c in cases}
    rollup_mismatch = partial = 0
    for row in rows:
        case = index.get(row["case"])
        row["case_fields"] = case or {}
        if not case:
            continue
        row["case_number"] = row["case_number"] or get(case, "CaseNumber")
        created = parse_dt(get(case, "CreatedDate"))
        ended = parse_dt(get(case, "ClosedDate")) if truthy(get(case, "IsClosed")) else now_utc()
        row["standard_age_h"] = hours_between(created, ended)

        # Partial history: CFHT began after the case was created (retention window,
        # or the case predates Case Flags). The breakdown then covers only part of Age.
        hist = parse_dt(row["history_start"])
        gap = hours_between(created, hist)
        row["history_gap_h"] = gap if gap and gap > CALENDAR_TOLERANCE_H else 0.0
        if row["history_gap_h"]:
            partial += 1

        rollups = [to_float(get(case, f)) for f in CASE_BH_ROLLUPS]
        if all(v is not None for v in rollups):
            row["rollup_our_bh"] = sum(rollups)
            # Rollups include flag-up time after the final close too.
            ours = row["bh"]["our_court"] + row["after_close_our_bh"]
            if abs(row["rollup_our_bh"] - ours) > ROLLUP_TOLERANCE_BH:
                rollup_mismatch += 1
    if partial:
        warnings.append(
            f"{partial} case(s) have CFHT history starting after Case.CreatedDate "
            "(retention window or pre-install). Their breakdown covers only part of Age; "
            "say so rather than presenting it as the whole."
        )
    if rollup_mismatch:
        warnings.append(
            f"{rollup_mismatch} case(s): flag-up BH from CFHT differs from the Case's "
            "Business_Hours_Age_1..4 rollup by more than "
            f"{ROLLUP_TOLERANCE_BH} BH. Expected when history is partial or the case is "
            "open (the running interval is not rolled up yet); otherwise check the pull."
        )


# ---------------------------------------------------------------------------- modes


def structural_warnings(rows: list[dict]) -> list[str]:
    """Shapes verified live that change how the numbers must be read."""
    out = []
    after = [r for r in rows if r["cal"]["after_close"] > CALENDAR_TOLERANCE_H]
    if after:
        out.append(
            f"{len(after)} case(s) have activity AFTER their final close (worked while still "
            "closed, or parked in a closed status). Salesforce's Age stops at ClosedDate, so "
            "the calendar total exceeds it by the after_close time. Report after-close work "
            "separately; it is not part of resolution time."
        )
    mixed = [r for r in rows if r["mixed_speeds"]]
    if mixed:
        out.append(
            f"{len(mixed)} case(s) changed aging speed mid-life ({', '.join(sorted({' -> '.join(r['speeds']) for r in mixed}))}). "
            "Each interval's BH uses that interval's calendar, so their BH mixes calendars: "
            "don't convert to working days with one --bh-per-day, and segment by "
            "interval speed (CFHT FLAGS__Aging_Speed__c), not Case.FLAGS__Aging_Speed__c."
        )
    return out


def mode_case(rows: list[dict]) -> dict:
    return {"mode": "case", "cases": rows}


def mode_cohort(rows: list[dict], group_by: str | None) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = "all"
        if group_by:
            key = str(get(row.get("case_fields", {}), group_by) or "(blank)")
        groups[key].append(row)

    out = {}
    for key, members in groups.items():
        totals = {b: sum(m["bh"][b] for m in members) for b in BUCKETS}
        # after_close sits outside Salesforce's Age, so it is not part of the denominator.
        age = sum(v for b, v in totals.items() if b != "after_close") or None
        whole = [m for m in members if not m.get("history_gap_h")]
        our = [m["bh"]["our_court"] for m in whole]
        ratio = [m["cal_total"] / m["bh_total"] for m in members if m["bh_total"] > 0]
        out[key] = {
            "cases": len(members),
            "total_bh": totals,
            "share": {b: (totals[b] / age if age and b != "after_close" else None) for b in BUCKETS},
            "excluded_partial_history": len(members) - len(whole),
            "controllable_bh": describe(our, min_n=10),
            "customer_bh": describe([m["bh"]["customer_court"] for m in whole], min_n=10),
            "past_sla_bh_total": sum(m["past_sla_bh"] for m in members),
            "cases_past_sla": sum(1 for m in members if m["past_sla_bh"] > 0),
            "queue_bh_total": sum(m["queue_bh"] for m in members),
            "handoffs_median": describe([m["handoffs"] for m in members])["median"],
            "cases_with_owner_return": sum(1 for m in members if m["owner_returns"]),
            "reopened": sum(1 for m in members if m["closes"] > 1),
            "worked_after_close": sum(1 for m in members if m["cal"]["after_close"] > CALENDAR_TOLERANCE_H),
            "mixed_speeds": sum(1 for m in members if m["mixed_speeds"]),
            # Per-case wait counts and average wait length, one value per case.
            "waits_on_us_per_case": describe([m["waits_on_us"]["n"] for m in whole]),
            "avg_wait_on_us_bh": describe([m["waits_on_us"]["avg_bh"] for m in whole]),
            "waits_on_customer_per_case": describe([m["waits_on_customer"]["n"] for m in whole]),
            "avg_wait_on_customer_bh": describe([m["waits_on_customer"]["avg_bh"] for m in whole]),
            "calendar_per_bh": describe(ratio),
        }
    return {"mode": "cohort", "group_by": group_by, "groups": out}


def mode_status(cfht: list[dict], customer_statuses: list[str]) -> dict:
    require_columns(cfht, [STATUS, FLAG_SET, BH], "age_decompose status")
    cells: dict[str, dict[str, float]] = defaultdict(lambda: {"our_court": 0.0, "customer_court": 0.0})
    for rec in cfht:
        side = "our_court" if truthy(get(rec, FLAG_SET)) else "customer_court"
        cells[get(rec, STATUS) or "(blank)"][side] += to_float(get(rec, BH)) or 0.0
    if set(cells) == {"(blank)"}:
        raise DataError("FLAGS__Case_Status__c is blank on every record -- status tracking "
                        "(Track_Case_Status__c) is off. Use the CaseHistory fallback in §11.")
    mismatch = sum(cells[s]["our_court"] for s in customer_statuses if s in cells)
    return {
        "mode": "status",
        "statuses": dict(cells),
        "customer_statuses": customer_statuses,
        "flag_up_in_customer_status_bh": mismatch if customer_statuses else None,
    }


def mode_backlog(cases: list[dict], edges: list[float], followup_field: str | None) -> dict:
    require_columns(cases, ["Id", "CreatedDate", "FLAGS__ViewedFlag__c"], "age_decompose backlog")
    labels = []
    lo = 0.0
    for e in edges:
        labels.append(f"{fnum(lo, 0)}-{fnum(e, 0)}d")
        lo = e
    labels.append(f"{fnum(lo, 0)}d+")
    buckets = {l: {"cases": 0, "flagged": 0, "follow_up_set": 0, "forgotten": 0} for l in labels}
    forgotten = []
    current = now_utc()
    for case in cases:
        days = (hours_between(parse_dt(get(case, "CreatedDate")), current) or 0.0) / 24.0
        label = labels[-1]
        for k, e in enumerate(edges):
            if days < e:
                label = labels[k]
                break
        cell = buckets[label]
        cell["cases"] += 1
        flagged = get(case, "FLAGS__ViewedFlag__c") is not None
        followup = bool(followup_field and get(case, followup_field))
        cell["flagged"] += flagged
        cell["follow_up_set"] += followup
        if not flagged and not followup:
            cell["forgotten"] += 1
            forgotten.append({"case": get(case, "Id"), "case_number": get(case, "CaseNumber"),
                              "age_days": days, "status": get(case, "Status"),
                              "owner": get(case, "Owner.Name")})
    forgotten.sort(key=lambda f: -f["age_days"])
    note = None if followup_field else (
        "No --followup-field given: 'forgotten' = unflagged only. Pass the org's Follow-Up "
        "On field from Preflight so cases with a scheduled follow-up are not counted.")
    return {"mode": "backlog", "open_cases": len(cases), "buckets": buckets,
            "forgotten": forgotten, "note": note}


# --------------------------------------------------------------------------- render


def _days(bh: float, bh_per_day: float | None) -> str:
    return f"{fnum(bh)} BH" + (f" ({bh / bh_per_day:.1f} wd)" if bh_per_day else "")


def render_factory(bh_per_day: float | None):
    def render(payload: dict) -> None:
        mode = payload["mode"]
        if mode == "case":
            rows = []
            for r in payload["cases"][:40]:
                rows.append([
                    r.get("case_number") or r["case"],
                    fnum(r.get("standard_age_h")), fnum(r["cal_total"]),
                    _days(r["bh_total"], bh_per_day),
                    fnum(r["bh"]["our_court"]), fnum(r["queue_bh"]), fnum(r["past_sla_bh"]),
                    fnum(r["bh"]["customer_court"]), fnum(r["bh"]["post_resolution"]),
                    fnum(r["bh"]["closed_gap"]), fnum(r["bh"]["after_close"]),
                    (f"{fnum(r['open_tail_cal'])} ({r['court_now']})" if r["court_now"] else ""),
                    r["handoffs"],
                    ("partial " if r.get("history_gap_h") else "")
                    + ("mixed-speed" if r["mixed_speeds"] else ""),
                ])
            print(table(rows, ["Case", "Std Age h", "Cal h", "Total BH", "Our BH", "  queue",
                               "  past SLA", "Cust BH", "Post-res", "Closed gap", "After close",
                               "Since last change (cal h, court)",
                               "Handoffs",
                               "History"]))
            if len(payload["cases"]) > 40:
                print(f"\n+{len(payload['cases']) - 40} more (use --json)")
            wrows = []
            for r in payload["cases"][:40]:
                us, cu = r["waits_on_us"], r["waits_on_customer"]
                wrows.append([
                    r.get("case_number") or r["case"],
                    f"{us['n']} ({us['replies']} replies)", fnum(us["avg_bh"]), fnum(us["max_bh"]),
                    f"{cu['n']} ({cu['ended_by_followup']} by follow-up)", fnum(cu["avg_bh"]),
                    fnum(cu["max_bh"]),
                ])
            print("\nWaits (BH; customer waits exclude resolved, closed and after-close time)")
            print(table(wrows, ["Case", "Customer waited on us", "Avg", "Longest",
                                "We waited on customer", "Avg", "Longest"]))
        elif mode == "cohort":
            for key, g in sorted(payload["groups"].items()):
                print(f"\n### {payload['group_by'] or 'Cohort'}: {key} ({g['cases']} cases)")
                rows = [[b, fnum(g["total_bh"][b]),
                         "outside Age" if g["share"][b] is None else f"{g['share'][b] * 100:.0f}%"]
                        for b in BUCKETS]
                print(table(rows, ["Bucket", "Total BH", "Share of age"]))
                if g["excluded_partial_history"]:
                    print(f"({g['excluded_partial_history']} case(s) with partial history left out of the medians)")
                c = g["controllable_bh"]
                print(f"controllable (our-court) BH per case: median {fnum(c['median'])} | "
                      f"p90 {fnum(c.get('p90'))} | mean {fnum(c['mean'])} | "
                      f"tail {fnum(c.get('tail_ratio'))}"
                      + (f"  [{c['low_confidence']}]" if c.get("low_confidence") else ""))
                print(f"past SLA: {g['cases_past_sla']} case(s), {fnum(g['past_sla_bh_total'])} BH | "
                      f"queue: {fnum(g['queue_bh_total'])} BH | owner returns: "
                      f"{g['cases_with_owner_return']} | reopened: {g['reopened']} | "
                      f"worked after close: {g['worked_after_close']} | mixed speeds: {g['mixed_speeds']} | "
                      f"calendar h per BH: {fnum(g['calendar_per_bh']['median'])}")
                print(f"waits per case (median): on us {fnum(g['waits_on_us_per_case']['median'], 0)} "
                      f"averaging {fnum(g['avg_wait_on_us_bh']['median'])} BH | on customer "
                      f"{fnum(g['waits_on_customer_per_case']['median'], 0)} averaging "
                      f"{fnum(g['avg_wait_on_customer_bh']['median'])} BH")
        elif mode == "status":
            rows = [[s, fnum(v["our_court"]), fnum(v["customer_court"])]
                    for s, v in sorted(payload["statuses"].items(),
                                       key=lambda kv: -(kv[1]["our_court"] + kv[1]["customer_court"]))]
            print(table(rows, ["Status", "Flag up (our court) BH", "Flag down (customer) BH"]))
            if payload["flag_up_in_customer_status_bh"] is not None:
                print(f"\nflag UP while status said waiting-on-customer "
                      f"({', '.join(payload['customer_statuses'])}): "
                      f"{fnum(payload['flag_up_in_customer_status_bh'])} BH")
        else:
            rows = [[k, v["cases"], v["flagged"], v["follow_up_set"], v["forgotten"]]
                    for k, v in payload["buckets"].items()]
            print(table(rows, ["Age", "Open", "Flagged", "Follow-up set", "Forgotten"]))
            if payload["forgotten"]:
                print("\nOldest forgotten (no flag, no follow-up):")
                print(table([[f["case_number"] or f["case"], f"{f['age_days']:.1f}",
                              f["status"] or "", f["owner"] or ""]
                             for f in payload["forgotten"][:10]],
                            ["Case", "Age d", "Status", "Owner"]))
            if payload["note"]:
                print(f"\n{payload['note']}")
    return render


# ----------------------------------------------------------------------------- main


def main() -> int:
    p = argparse.ArgumentParser(description="True Case Age: decompose case age by court")
    p.add_argument("--cfht", help="JSON of CFHT records (not needed for backlog)")
    p.add_argument("--cases", help="JSON of Case rows (Id, CaseNumber, CreatedDate, ClosedDate, "
                                   "IsClosed, rollups, segment fields)")
    p.add_argument("--mode", default="case", choices=["case", "cohort", "status", "backlog"])
    p.add_argument("--group-by", help="cohort: Case field to slice by (e.g. Priority, Origin)")
    p.add_argument("--resolved-statuses", default="",
                   help="case/cohort: comma list of statuses that mean resolved, waiting to "
                        "close (e.g. 'Pending Closure'). Flag-down time in them counts as "
                        "post_resolution instead of customer_court. Flag-up time is unchanged.")
    p.add_argument("--customer-statuses", default="",
                   help="status: comma list of statuses that mean 'waiting on customer'")
    p.add_argument("--edges", default="1,3,7,30",
                   help="backlog: age bucket edges in calendar days (SKILL.md constants)")
    p.add_argument("--followup-field", help="backlog: org Follow-Up On field API name")
    p.add_argument("--bh-per-day", type=float,
                   help="business hours in one working day for this calendar; adds a "
                        "working-days column. Read it from the BusinessHours record.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        warnings: list[str] = []
        if args.mode == "backlog":
            if not args.cases:
                raise DataError("backlog mode needs --cases (open Case rows from §11.1)")
            cases = load_records(args.cases)
            if not cases:
                print("No records in input.", file=sys.stderr)
                return 1
            edges = sorted(float(x) for x in args.edges.split(",") if x.strip())
            payload = mode_backlog(cases, edges, args.followup_field)
        else:
            if not args.cfht:
                raise DataError(f"{args.mode} mode needs --cfht")
            cfht = load_records(args.cfht)
            if not cfht:
                print("No records in input.", file=sys.stderr)
                return 1
            if args.mode == "status":
                statuses = [s.strip() for s in args.customer_statuses.split(",") if s.strip()]
                payload = mode_status(cfht, statuses)
            else:
                cases = load_records(args.cases) if args.cases else None
                resolved = frozenset(x.strip() for x in args.resolved_statuses.split(",") if x.strip())
                rows = decompose_all(cfht, cases, resolved)
                warn = check_variance([r["bh_total"] for r in rows], "total BH per case")
                if warn:
                    warnings.append(warn)
                warnings.extend(structural_warnings(rows))
                if cases:
                    attach_cases(rows, cases, warnings)
                payload = mode_case(rows) if args.mode == "case" else mode_cohort(rows, args.group_by)
        payload["warnings"] = warnings
        emit(payload, args.json, render_factory(args.bh_per_day))
        return 0
    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
