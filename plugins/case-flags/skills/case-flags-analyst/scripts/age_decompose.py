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
  post_resolution  the flag-down interval that ENDS in the case's final close
                   (Action = 'Case Closed', Flag_Set = false): resolved, not yet closed
  closed_gap       flag-down intervals that START right after a non-final close and
                   run until the reopen -- the case sat closed, then came back

Modes
  case     per-case breakdown table (one row per case)
  cohort   medians/totals across cases, optional --group-by a Case field
  status   time in each status split by court (needs CFHT status tracking)
  backlog  OPEN cases from Case rows only (no CFHT): age buckets x flagged / follow-up /
           forgotten. Pass --cases only.

Required CFHT SELECT: FLAGS__Case__c, FLAGS__Start__c, FLAGS__End__c, FLAGS__Flag_Set__c,
FLAGS__Event__c, FLAGS__Action__c, FLAGS__Business_Hours_Elapsed__c, FLAGS__Hours_Elapsed__c.
Recommended: FLAGS__Owner_Name__c, FLAGS__Queue_Id__c, FLAGS__Case_Status__c,
FLAGS__Business_Hours_in_Age_4__c, FLAGS__Hours_in_Age_4__c.

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
HRS_L4 = "FLAGS__Hours_in_Age_4__c"

CASE_CLOSED = "Case Closed"
OWNER_CHANGED = "Case Owner Changed"

BUCKETS = ["our_court", "customer_court", "post_resolution", "closed_gap"]
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


def decompose_case(case_id: str, records: list[dict]) -> dict:
    """Walk one case's intervals in Start order and assign each to a bucket."""
    records.sort(key=lambda r: parse_dt(get(r, START)) or parse_dt("1900-01-01"))

    close_idx = [i for i, r in enumerate(records) if get(r, ACTION) == CASE_CLOSED]
    final_close = close_idx[-1] if close_idx else None
    after_close = {i + 1 for i in close_idx if final_close is not None and i != final_close}

    bh = {b: 0.0 for b in BUCKETS}
    cal = {b: 0.0 for b in BUCKETS}
    queue_bh = queue_cal = 0.0
    past_sla_bh = past_sla_cal = 0.0
    open_tail_cal = 0.0
    owners: list[str] = []
    handoffs = 0

    for i, rec in enumerate(records):
        rec_bh = to_float(get(rec, BH))
        rec_cal = to_float(get(rec, HRS))
        if get(rec, END) is None:
            # The interval still running on an open case: CFHT has no elapsed yet.
            # Calendar time is measurable; business hours are not, so keep it apart.
            open_tail_cal += hours_between(parse_dt(get(rec, START)), now_utc()) or 0.0
            rec_bh, rec_cal = 0.0, 0.0
        rec_bh = rec_bh or 0.0
        rec_cal = rec_cal or 0.0
        if rec_bh < 0 or rec_cal < 0:
            raise ValueError(f"negative elapsed on case {case_id} record {i}")

        if truthy(get(rec, FLAG_SET)):
            bucket = "our_court"
            if get(rec, QUEUE):
                queue_bh += rec_bh
                queue_cal += rec_cal
            past_sla_bh += to_float(get(rec, BH_L4)) or 0.0
            past_sla_cal += to_float(get(rec, HRS_L4)) or 0.0
        elif i == final_close:
            bucket = "post_resolution"
        elif i in after_close:
            bucket = "closed_gap"
        else:
            bucket = "customer_court"
        bh[bucket] += rec_bh
        cal[bucket] += rec_cal

        if get(rec, EVENT) == OWNER_CHANGED:
            handoffs += 1
        owner = get(rec, OWNER)
        if owner and (not owners or owners[-1] != owner):
            owners.append(owner)

    returns = sum(1 for k, o in enumerate(owners) if o in owners[:k])
    first = records[0] if records else {}
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
        "past_sla_cal": past_sla_cal,
        "open_tail_cal": open_tail_cal,
        "closes": len(close_idx),
        "handoffs": handoffs,
        "owner_returns": returns,
        "history_start": get(first, START),
    }


def decompose_all(cfht: list[dict]) -> list[dict]:
    require_columns(cfht, [CASE, START, END, FLAG_SET, EVENT, ACTION, BH, HRS], "age_decompose")
    by_case: dict[str, list[dict]] = defaultdict(list)
    for rec in cfht:
        if get(rec, CASE):
            by_case[get(rec, CASE)].append(rec)
    try:
        return [decompose_case(cid, recs) for cid, recs in by_case.items()]
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
            if abs(row["rollup_our_bh"] - row["bh"]["our_court"]) > ROLLUP_TOLERANCE_BH:
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
        age = sum(totals.values()) or None
        our = [m["bh"]["our_court"] for m in members]
        ratio = [m["cal_total"] / m["bh_total"] for m in members if m["bh_total"] > 0]
        out[key] = {
            "cases": len(members),
            "total_bh": totals,
            "share": {b: (totals[b] / age if age else None) for b in BUCKETS},
            "controllable_bh": describe(our, min_n=10),
            "customer_bh": describe([m["bh"]["customer_court"] for m in members], min_n=10),
            "past_sla_bh_total": sum(m["past_sla_bh"] for m in members),
            "cases_past_sla": sum(1 for m in members if m["past_sla_bh"] > 0),
            "queue_bh_total": sum(m["queue_bh"] for m in members),
            "handoffs_median": describe([m["handoffs"] for m in members])["median"],
            "cases_with_owner_return": sum(1 for m in members if m["owner_returns"]),
            "reopened": sum(1 for m in members if m["closes"] > 1),
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
                    fnum(r["bh"]["closed_gap"]), fnum(r["open_tail_cal"]), r["handoffs"],
                    "partial" if r.get("history_gap_h") else "",
                ])
            print(table(rows, ["Case", "Std Age h", "Cal h", "Total BH", "Our BH", "  queue",
                               "  past SLA", "Cust BH", "Post-res", "Closed gap", "Running cal h",
                               "Handoffs",
                               "History"]))
            if len(payload["cases"]) > 40:
                print(f"\n+{len(payload['cases']) - 40} more (use --json)")
        elif mode == "cohort":
            for key, g in sorted(payload["groups"].items()):
                print(f"\n### {payload['group_by'] or 'Cohort'}: {key} ({g['cases']} cases)")
                rows = [[b, fnum(g["total_bh"][b]),
                         f"{(g['share'][b] or 0) * 100:.0f}%"] for b in BUCKETS]
                print(table(rows, ["Bucket", "Total BH", "Share of age"]))
                c = g["controllable_bh"]
                print(f"controllable (our-court) BH per case: median {fnum(c['median'])} | "
                      f"p90 {fnum(c.get('p90'))} | mean {fnum(c['mean'])} | "
                      f"tail {fnum(c.get('tail_ratio'))}"
                      + (f"  [{c['low_confidence']}]" if c.get("low_confidence") else ""))
                print(f"past SLA: {g['cases_past_sla']} case(s), {fnum(g['past_sla_bh_total'])} BH | "
                      f"queue: {fnum(g['queue_bh_total'])} BH | owner returns: "
                      f"{g['cases_with_owner_return']} | reopened: {g['reopened']} | "
                      f"calendar h per BH: {fnum(g['calendar_per_bh']['median'])}")
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
                rows = decompose_all(cfht)
                warn = check_variance([r["bh_total"] for r in rows], "total BH per case")
                if warn:
                    warnings.append(warn)
                if args.cases:
                    attach_cases(rows, load_records(args.cases), warnings)
                payload = mode_case(rows) if args.mode == "case" else mode_cohort(rows, args.group_by)
        payload["warnings"] = warnings
        emit(payload, args.json, render_factory(args.bh_per_day))
        return 0
    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
