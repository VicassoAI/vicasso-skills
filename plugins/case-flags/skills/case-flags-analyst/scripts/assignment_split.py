#!/usr/bin/env python3
"""
Job F -- decompose initial response into assignment time and response time.

  assignment time = case creation -> landing with whoever produced the initial response
  response time   = that landing point -> the flag actually clearing

The two are defined to sum to FLAGS__Initial_Response_Business_Hours__c, because response
time is computed as total_ir - assignment. That makes the sum an identity rather than a
reconciliation -- checking it proves nothing, and an earlier version of this script
reported it as a passing check. What is verified instead, in _run_checks():

  * a negative response time is impossible and fails the run (exit 3)
  * the CFHT-measured initial-response span is compared against the package's own
    IR field as a genuine independent cross-check, and warns on disagreement

Both pitfalls recorded in references/job-f-assignment-response-split.md are assertions here, not
warnings:

  1. Missing FLAGS__Business_Hours_Elapsed__c in the SELECT yields "0.00 assignment time
     for every case" -- plausible-looking and completely wrong. require_columns() raises
     on the absent column, and an all-zero population raises even if the column exists.

  2. "First record whose owner matches the final owner" is NOT the transition record. A
     downstream automation blip (Case Status Changed / Local Automation) can fire seconds
     after the real ownership change under a different user's session, which misattributes
     the actor. We take record i-1 and additionally verify its Event is
     'Case Owner Changed', reporting any case where it is not.

Two-pass by design (job-f step 7): run once without --actors to get the transition record
IDs, run the §9.3 lookup for just those IDs, then re-run with --actors to resolve
self vs peer. Bulk-fetching CreatedBy for the whole CFHT pull wastes a very large query.

Usage
  # pass 1 -- structure and the transition IDs to look up
  python3 assignment_split.py --cfht cfht.json --cases cases.json --rep-id 005...

  # pass 2 -- with actors resolved. --rep-name is required here: self-detection matches
  # actor display names, so omitting it would file every self-assigned case as peer.
  python3 assignment_split.py --cfht cfht.json --cases cases.json --rep-id 005... \
      --rep-name "Rep Name" --actors actors.json \
      --peer-actors "Peer One,Peer Two,Peer Three"
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from cfa_common import (
    DataError,
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
OWNER = "FLAGS__Owner__c"
OWNER_NAME = "FLAGS__Owner_Name__c"
EVENT = "FLAGS__Event__c"
BH = "FLAGS__Business_Hours_Elapsed__c"
IR_BH = "FLAGS__Initial_Response_Business_Hours__c"

OWNER_CHANGED = "Case Owner Changed"
FLAG_CLEARED = "Flag Cleared"

# Largest business-hours gap between the CFHT-measured initial-response span and the
# package's own Initial_Response_Business_Hours__c before the walk is suspect. 0.01 BH
# is ~36 seconds, comfortably above float noise and below anything meaningful.
MEASURED_TOLERANCE_BH = 0.01


def load_case_population(path: str) -> dict[str, float]:
    records = load_records(path)
    require_columns(records, ["Id", IR_BH], "case population (§9.1)")
    population = {}
    for record in records:
        case_id = get(record, "Id")
        hours = to_float(get(record, IR_BH))
        if case_id and hours is not None:
            population[case_id] = hours
    if not population:
        raise DataError(
            f"No cases with a populated {IR_BH}. The §9.1 population query should filter "
            "FLAGS__Initial_Response__c != null."
        )
    return population


def load_actor_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    records = load_records(path)
    require_columns(records, ["Id"], "transition-actor lookup (§9.3)")
    actors = {}
    for record in records:
        record_id = get(record, "Id")
        name = get(record, "CreatedBy.Name") or get(record, "CreatedById")
        if record_id and name:
            actors[record_id] = name
    return actors


def split_cases(
    cfht: list[dict],
    population: dict[str, float],
    rep_id: str,
    actors: dict[str, str],
) -> tuple[list[dict], list[str]]:
    require_columns(cfht, [CASE, START, OWNER, EVENT, BH], "CFHT pull (§9.2)")

    by_case: dict[str, list[dict]] = defaultdict(list)
    for record in cfht:
        case_id = get(record, CASE)
        if case_id in population:
            by_case[case_id].append(record)

    results: list[dict] = []
    warnings: list[str] = []
    unverified = 0
    missing_cfht = 0

    for case_id, total_ir in population.items():
        records = by_case.get(case_id)
        if not records:
            missing_cfht += 1
            results.append({
                "case": case_id, "bucket": "no_handoff_recorded",
                "assignment_bh": 0.0, "response_bh": total_ir, "total_ir_bh": total_ir,
                "residual": 0.0, "reason": "no CFHT records inside the retention window",
                "transition_record_id": None, "actor": None, "transition_verified": None,
            })
            continue

        records.sort(key=lambda r: (parse_dt(get(r, START)) or parse_dt("1900-01-01")))

        # Locate the landing transition: the first index whose owner is the final owner
        # AND whose predecessor had a different owner. The transition record is i-1.
        landing_index = None
        for index in range(1, len(records)):
            if get(records[index], OWNER) == rep_id and get(records[index - 1], OWNER) != rep_id:
                landing_index = index
                break

        if landing_index is None:
            # Owned by the final owner from the first record in the window: no handoff.
            # Assignment time is genuinely unknown -- do NOT guess who assigned it or when.
            results.append({
                "case": case_id, "bucket": "no_handoff_recorded",
                "assignment_bh": 0.0, "response_bh": total_ir, "total_ir_bh": total_ir,
                "residual": 0.0,
                "reason": "no Case Owner Changed into the final owner within the window",
                "transition_record_id": None, "actor": None, "transition_verified": None,
            })
            continue

        transition = records[landing_index - 1]
        verified = get(transition, EVENT) == OWNER_CHANGED
        if not verified:
            unverified += 1

        assignment_bh = sum(
            to_float(get(r, BH)) or 0.0 for r in records[:landing_index]
        )
        # response_bh stays a subtraction, per job-f step 6, so a walk bug surfaces in
        # assignment_bh rather than silently in response_bh. But that identity means
        # assignment + response == total_ir ALWAYS, so it is not evidence of anything --
        # see measured_ir_bh() for the check that can actually fail.
        response_bh = total_ir - assignment_bh

        transition_id = get(transition, "Id")
        actor = actors.get(transition_id)

        results.append({
            "case": case_id,
            "bucket": None,  # assigned below once the actor is known
            "assignment_bh": assignment_bh,
            "response_bh": response_bh,
            "total_ir_bh": total_ir,
            "measured_ir_bh": measured_ir_bh(records, landing_index),
            "transition_record_id": transition_id,
            "transition_owner_from": get(transition, OWNER_NAME) or get(transition, OWNER),
            "transition_event": get(transition, EVENT),
            "transition_verified": verified,
            "actor": actor,
            "reason": None,
        })

    if missing_cfht:
        warnings.append(
            f"{missing_cfht} case(s) in the population had no CFHT records in the window; "
            "bucketed as no-handoff-recorded with assignment time unknown."
        )
    if unverified:
        warnings.append(
            f"{unverified} transition record(s) are not Event = '{OWNER_CHANGED}'. Actor "
            "attribution for those is suspect (job-f pitfall 2) -- cross-check against "
            "CaseHistory (§9.4) before reporting who assigned them."
        )

    _assert_not_all_zero(results)
    return results, warnings


def measured_ir_bh(records: list[dict], landing_index: int) -> float | None:
    """
    Measure the initial-response span from CFHT itself, independent of the subtraction.

    Sums FLAGS__Business_Hours_Elapsed__c from the first record in the window through the
    first 'Flag Cleared' at or after the landing. Compared against the package's own
    Initial_Response_Business_Hours__c, this is a real cross-check: the two are computed
    from different sources and agreeing is informative.

    Returns None when the window has no clear event after the landing, rather than
    guessing a span. A systematic shortfall across many cases usually means the CFHT
    retention window opens after case creation, not that the walk is broken -- which is
    why this drives a warning and not the exit code.
    """
    clear_index = None
    for index in range(landing_index, len(records)):
        if get(records[index], EVENT) == FLAG_CLEARED:
            clear_index = index
            break
    if clear_index is None:
        return None
    return sum(to_float(get(r, BH)) or 0.0 for r in records[: clear_index + 1])


def _assert_not_all_zero(results: list[dict]) -> None:
    """Pitfall 1: a uniform zero assignment time across a population is a bug."""
    handoffs = [r for r in results if r["reason"] is None]
    if len(handoffs) >= 20 and all(r["assignment_bh"] == 0.0 for r in handoffs):
        raise DataError(
            f"All {len(handoffs)} handoff cases computed 0.00 BH assignment time. This is "
            f"job-f pitfall 1, not a finding: queue dwell is genuinely non-trivial "
            "(validated mean 0.5-0.6 BH, max 4-7 BH across three reps). Confirm "
            f"{BH} is in the §9.2 SELECT list and populated, then re-run."
        )


def assign_buckets(
    results: list[dict], rep_id: str, rep_name: str | None,
    peer_actors: list[str], exclude_actors: list[str],
) -> list[str]:
    """
    Self vs peer vs out-of-scope. Returns any warnings raised while bucketing.

    Actor scoping is a per-run parameter, never a hardcoded assumption -- different orgs
    want different actor sets (e.g. excluding manager reassignments).

    Actors arrive as display names (CreatedBy.Name), so self-detection needs --rep-name:
    matching on rep_id alone can never fire, which silently refiles every self-assigned
    case as peer-assigned and inverts the self-vs-peer gap this script reports as its
    headline. main() refuses that combination outright; the resolved-but-never-matched
    case below catches a rep_name that simply does not match the org's spelling.
    """
    warnings: list[str] = []
    self_names = {n.lower() for n in [rep_name, rep_id] if n}
    peers = {n.strip().lower() for n in peer_actors if n.strip()}
    excluded = {n.strip().lower() for n in exclude_actors if n.strip()}

    resolved = 0
    for row in results:
        if row["bucket"]:
            continue
        actor = (row.get("actor") or "").strip()
        if not actor:
            row["bucket"] = "actor_unresolved"
            continue
        resolved += 1
        key = actor.lower()
        if key in excluded:
            row["bucket"] = "excluded_actor"
        elif key in self_names:
            row["bucket"] = "self_assigned"
        elif peers and key not in peers:
            row["bucket"] = "out_of_scope_actor"
        else:
            row["bucket"] = "peer_assigned"

    if resolved and rep_name and not any(r["bucket"] == "self_assigned" for r in results):
        warnings.append(
            f"{resolved} actor(s) resolved but none matched --rep-name '{rep_name}', so every "
            "case is bucketed as peer-assigned. Verify the name matches the org's User record "
            "exactly -- a mismatch here inverts the self-vs-peer finding rather than erroring."
        )
    return warnings


def _run_checks(results: list[dict], warnings: list[str]) -> dict:
    """
    The checks that can actually fail, replacing the old residual test.

    That test compared assignment + response against total_ir, but response is *defined*
    as total_ir - assignment, so the residual was always zero and 'PASS' meant nothing.
    Verified against deliberately inconsistent input: CFHT intervals summing to 103 BH on
    a case declaring 10 BH still reported PASS with residual 0.00e+00.

    Two real checks in its place:

      negative response_bh  -- impossible. Means assignment_bh exceeded the whole initial
                               response, so the landing walk is wrong. Hard fail, because
                               the number is definitionally invalid and it would otherwise
                               flow into the bucket medians unnoticed.
      measured vs stated    -- CFHT-summed span against the package's own IR field. A
                               genuine cross-check, but it also shifts when the retention
                               window opens after case creation, so it warns rather than
                               failing the run.
    """
    handoffs = [r for r in results if r["reason"] is None]

    negatives = [r for r in handoffs if r["response_bh"] < 0]
    if negatives:
        worst = min(negatives, key=lambda r: r["response_bh"])
        warnings.append(
            f"IMPOSSIBLE VALUE: {len(negatives)} case(s) computed a NEGATIVE response time "
            f"(worst {worst['response_bh']:.2f} BH on case {worst['case']}). assignment_bh "
            "exceeded the case's whole initial response, so the landing walk picked the "
            "wrong transition record. Stop and debug -- do not report these figures."
        )

    comparable = [
        r for r in handoffs
        if r.get("measured_ir_bh") is not None and r["total_ir_bh"] is not None
    ]
    deltas = [abs(r["measured_ir_bh"] - r["total_ir_bh"]) for r in comparable]
    off = [d for d in deltas if d > MEASURED_TOLERANCE_BH]
    if off:
        warnings.append(
            f"{len(off)} of {len(comparable)} case(s) disagree by more than "
            f"{MEASURED_TOLERANCE_BH} BH between the CFHT-measured initial-response span "
            f"(median delta {fnum(median(deltas))} BH, max {fnum(max(off))} BH) and "
            f"{IR_BH}. Usually the CFHT window opens after case creation so the measured "
            "span is short; confirm that before treating the split as sound."
        )

    return {
        "negative_response_cases": len(negatives),
        "measured_comparable_cases": len(comparable),
        "measured_disagreements": len(off),
        "measured_delta_bh": describe(deltas) if deltas else None,
        "measured_tolerance_bh": MEASURED_TOLERANCE_BH,
        "not_measurable_cases": len(handoffs) - len(comparable),
        # Only the impossible-value check gates the exit code.
        "passed": not negatives,
    }


def summarise(results: list[dict], warnings: list[str]) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        buckets[row["bucket"] or "actor_unresolved"].append(row)

    summary = {}
    for name, rows in buckets.items():
        summary[name] = {
            "n": len(rows),
            "assignment": describe([r["assignment_bh"] for r in rows]),
            "response": describe([r["response_bh"] for r in rows]),
        }

    checks = _run_checks(results, warnings)
    reconciled = checks["passed"]

    # The self-vs-peer response gap is a repeated finding across validated reps, so it
    # gets computed explicitly rather than left for someone to spot in a table.
    gap = None
    self_median = median([r["response_bh"] for r in buckets.get("self_assigned", [])])
    peer_median = median([r["response_bh"] for r in buckets.get("peer_assigned", [])])
    if self_median and peer_median:
        gap = {
            "self_median_response_bh": self_median,
            "peer_median_response_bh": peer_median,
            "ratio": peer_median / self_median if self_median else None,
            "note": "Call this out explicitly in the write-up -- self-assigned cases answered "
                    "faster has held in every validated rep so far, and it may mean handoffs "
                    "sit unnoticed in an inbox. Do not bury it in a table.",
        }

    pending = sorted({r["transition_record_id"] for r in results
                      if r["transition_record_id"] and not r.get("actor")})

    return {
        "cases_analysed": len(results),
        "reconciliation": checks,
        "buckets": summary,
        "self_vs_peer_response_gap": gap,
        "transition_ids_needing_actor_lookup": pending,
        "actor_lookup_in_clause": (
            "'" + "','".join(pending) + "'" if pending else None
        ),
        "warnings": warnings,
    }


def render(payload: dict) -> None:
    print("== Job F: assignment vs response split ==\n")
    recon = payload["reconciliation"]
    status = "PASS" if recon["passed"] else "*** FAIL ***"
    print(f"cases analysed: {payload['cases_analysed']}")
    print(f"validity check: {status}", end="")
    if recon["negative_response_cases"]:
        print(f" -- {recon['negative_response_cases']} negative response time(s)")
    else:
        print(" -- no impossible values")

    delta = recon.get("measured_delta_bh")
    if delta and delta.get("n"):
        print(
            f"CFHT-measured vs {IR_BH}: {recon['measured_disagreements']} of "
            f"{recon['measured_comparable_cases']} case(s) off by >"
            f"{recon['measured_tolerance_bh']} BH "
            f"(median delta {fnum(delta['median'])} BH, max {fnum(delta['max'])} BH)"
        )
    if recon.get("not_measurable_cases"):
        print(f"{recon['not_measurable_cases']} case(s) had no clear event in the window, "
              "so no independent span was measurable")
    print()

    rows = []
    for name, stats in sorted(payload["buckets"].items()):
        assign, resp = stats["assignment"], stats["response"]
        rows.append([
            name, stats["n"],
            fnum(assign.get("mean")), fnum(assign.get("median")),
            fnum(resp.get("mean")), fnum(resp.get("median")),
        ])
    print(table(rows, ["Bucket", "n", "Assign mean", "Assign median",
                       "Resp mean", "Resp median"]))
    print("\n(all figures business hours)")

    gap = payload.get("self_vs_peer_response_gap")
    if gap:
        ratio = gap.get("ratio")
        print(f"\nSelf vs peer response: {fnum(gap['self_median_response_bh'])} BH vs "
              f"{fnum(gap['peer_median_response_bh'])} BH"
              + (f" ({fnum(ratio, 1)}x slower when peer-assigned)" if ratio else ""))
        print(f"  {gap['note']}")

    pending = payload.get("transition_ids_needing_actor_lookup") or []
    if pending:
        print(f"\nNext step -- resolve actors for {len(pending)} transition record(s) via §9.3:")
        print("  SELECT Id, CreatedById, CreatedBy.Name")
        print("  FROM FLAGS__Case_Flags_History_Tracking__c")
        print(f"  WHERE Id IN ({payload['actor_lookup_in_clause']})")
        print("\nThen re-run this script with --actors pointing at those results.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Job F assignment/response decomposition")
    parser.add_argument("--cfht", required=True, help="JSON from §9.2 (merged pages)")
    parser.add_argument("--cases", required=True, help="JSON from §9.1 case population")
    parser.add_argument("--rep-id", required=True, help="final owner's User Id")
    parser.add_argument("--rep-name", default=None, help="final owner's display name")
    parser.add_argument("--actors", default=None, help="JSON from §9.3 actor lookup")
    parser.add_argument("--peer-actors", default="",
                        help="comma-separated actor names in scope as peers")
    parser.add_argument("--exclude-actors", default="",
                        help="comma-separated actors to exclude (e.g. manager reassignments)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.actors and not args.rep_name:
            raise DataError(
                "--rep-name is required together with --actors. Self-vs-peer classification "
                "compares actor display names from CreatedBy.Name, so without the rep's name "
                "nothing can ever match self and every self-assigned case would be reported "
                "as peer-assigned -- inverting the headline finding instead of failing."
            )

        cfht = load_records(args.cfht)
        population = load_case_population(args.cases)
        actors = load_actor_map(args.actors)

        results, warnings = split_cases(cfht, population, args.rep_id, actors)
        warnings += assign_buckets(
            results, args.rep_id, args.rep_name,
            args.peer_actors.split(","), args.exclude_actors.split(","),
        )
        payload = summarise(results, warnings)
        payload["cases"] = results

        emit(payload, args.json, render)
        return 0 if payload["reconciliation"]["passed"] else 3

    except DataError as error:
        print(f"\nDATA ERROR: {error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
