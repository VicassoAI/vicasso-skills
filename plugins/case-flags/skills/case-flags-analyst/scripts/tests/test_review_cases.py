#!/usr/bin/env python3
"""
Regression tests for the edge cases found in code review of the True Case Age work.

Synthetic CFHT records only (no org data). Run from the scripts directory:
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import age_decompose as ad  # noqa: E402
import assignment_split as asp  # noqa: E402
import run_stitch as rs  # noqa: E402
from cfa_common import DataError, require_columns  # noqa: E402

T0 = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def history(case: str, steps: list[tuple], start: datetime = T0, first_number: int = 1) -> list[dict]:
    """
    Build a case's CFHT records. Each step is
    (hours, flag_set, event, action, status, owner_id, owner_name[, queue_id]).
    BH = calendar hours, which is all these tests need.
    """
    out, t = [], start
    for n, step in enumerate(steps):
        hours, flag, event, action, status, owner, owner_name = step[:7]
        queue = step[7] if len(step) > 7 else None
        end = t + timedelta(hours=hours)
        out.append({
            "Id": f"{case}-{n}", "FLAGS__Case__c": case,
            "FLAGS__Case__r": {"CaseNumber": case},
            "FLAGS__Case_Flag_History_Number__c": str(first_number + n),
            "FLAGS__Start__c": iso(t), "FLAGS__End__c": iso(end),
            "FLAGS__Flag_Set__c": flag, "FLAGS__Event__c": event, "FLAGS__Action__c": action,
            "FLAGS__Case_Status__c": status, "FLAGS__Owner__c": owner,
            "FLAGS__Owner_Name__c": owner_name, "FLAGS__Queue_Id__c": queue,
            "FLAGS__Business_Hours_Elapsed__c": hours, "FLAGS__Hours_Elapsed__c": hours,
            "FLAGS__Business_Hours_in_Age_4__c": 0.0, "FLAGS__Aging_Speed__c": "P3",
        })
        t = end
    return out


REP, REP_NAME = "005REP", "Rep One"
SET, CLR = "Flag Set", "Flag Cleared"
STAT, OWN = "Case Status Changed", "Case Owner Changed"


class RunStitch(unittest.TestCase):
    def test_followup_split_credits_the_owner_who_cleared(self):
        recs = history("C1", [
            (1, False, SET, "Email Received", "New", None, "Support Queue", "00GQ"),
            (2, True, OWN, "Local Automation", "New", None, "Support Queue", "00GQ"),
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (1, False, STAT, "Local Automation", "Working", REP, REP_NAME),
        ])
        out = rs.mode_followup_split(rs.build_runs(recs), "FLAGS__Owner__c")
        self.assertEqual(list(out["groups"]), [REP])

    def test_followup_split_owner_filter(self):
        recs = history("C2", [
            (1, False, SET, "Email Received", "New", "005OTHER", "Other"),
            (1, True, CLR, "Email Sent", "Working", "005OTHER", "Other"),
            (1, False, SET, "Email Received", "Working", REP, REP_NAME),
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (1, False, STAT, "Local Automation", "Working", REP, REP_NAME),
        ])
        out = rs.mode_followup_split(rs.build_runs(recs), None, owners=frozenset({REP}))
        self.assertEqual(out["groups"]["all"]["other_clears"], 1)

    def test_automatically_cleared_run_is_not_a_worst_wait(self):
        recs = history("C3", [
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (1, False, CLR, "Case Closed", "Closed", REP, REP_NAME),
            (40, True, CLR, "Automatically Cleared", "Closed", REP, REP_NAME),
            (30, False, STAT, "Local Automation", "Closed", REP, REP_NAME),
        ])
        out = rs.mode_worst_run(rs.build_runs(recs), None)
        self.assertEqual(out["worst_run"]["bh_total"], 1)
        down = rs.mode_down_intervals(recs)
        self.assertEqual(down["waits"], 0)

    def test_resolved_statuses_need_the_status_column(self):
        recs = history("C4", [(1, False, SET, "Email Received", "With Customer", REP, REP_NAME)])
        for r in recs:
            del r["FLAGS__Case_Status__c"]
        path = _write(recs)
        sys.argv = ["run_stitch.py", "--input", path, "--mode", "down-intervals",
                    "--resolved-statuses", "Pending Closure"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(rs.main(), 2)


class AgeDecompose(unittest.TestCase):
    def test_customer_reply_during_resolved_status_is_labelled_customer(self):
        recs = history("A1", [
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (5, False, STAT, "Local Automation", "With Customer", REP, REP_NAME),
            (3, False, SET, "Email Received", "Pending Closure", REP, REP_NAME),
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
        ])
        row = ad.decompose_case("A1", recs, is_closed=False,
                                resolved_statuses=frozenset({"Pending Closure"}))
        w = row["waits_on_customer"]
        self.assertEqual((w["ended_by_customer"], w["ended_by_org_automation"]), (1, 0))

    def test_closed_date_fallback_finds_one_close(self):
        recs = history("A2", [
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (5, False, STAT, "Local Automation", "Pending Closure", REP, REP_NAME),
            (0, False, STAT, "Local Automation", "Pending Closure", REP, REP_NAME),
        ])
        closed = datetime.fromisoformat(recs[-1]["FLAGS__End__c"].replace(".000+0000", "+00:00"))
        row = ad.decompose_case("A2", recs, is_closed=True, closed_date=closed,
                                closed_statuses=frozenset({"Closed"}))
        self.assertEqual(row["closes"], 1)
        self.assertAlmostEqual(row["bh"]["post_resolution"], 5)

    def test_closed_gap_survives_a_move_between_closed_statuses(self):
        recs = history("A3", [
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (2, False, CLR, "Case Closed", "Working", REP, REP_NAME),
            (4, False, STAT, "Local Automation", "Closed", REP, REP_NAME),
            (6, False, SET, "Email Received", "Bug Fix Pending", REP, REP_NAME),
            (1, True, STAT, "Local Automation", "Working", REP, REP_NAME),
        ])
        row = ad.decompose_case("A3", recs, is_closed=False,
                                closed_statuses=frozenset({"Closed", "Bug Fix Pending"}))
        self.assertAlmostEqual(row["bh"]["closed_gap"], 10)
        # Only the 2 h before the close is a customer wait; none of the closed time is.
        self.assertAlmostEqual(row["bh"]["customer_court"], 2)
        self.assertAlmostEqual(row["waits_on_customer"]["total_bh"], 2)

    def test_reverted_on_reply_after_reopen(self):
        pc = "Pending Closure"
        recs = history("A4", [
            (1, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (2, False, CLR, "Case Closed", pc, REP, REP_NAME),
            (3, False, SET, "Email Received", "Closed", REP, REP_NAME),
            (1, True, STAT, "Local Automation", "Working", REP, REP_NAME),
            (0, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (2, False, STAT, "Local Automation", pc, REP, REP_NAME),
            (1, False, SET, "Email Received", pc, REP, REP_NAME),
            (1, True, CLR, "Email Sent", pc, REP, REP_NAME),
            (0, False, STAT, "Local Automation", pc, REP, REP_NAME),
            (1, False, STAT, "Local Automation", "Working", REP, REP_NAME),
        ])
        # Second Pending Closure stretch: a customer email inside it, so no revert...
        row = ad.decompose_case("A4", recs, is_closed=False, resolved_statuses=frozenset({pc}))
        self.assertEqual(row["resolved_reverted_on_reply"], 0)
        # ...and without that email, the reply-driven revert is found despite the
        # closed-gap email earlier in the case.
        recs2 = [r for r in recs if r["Id"] != "A4-6"]
        row2 = ad.decompose_case("A4", recs2, is_closed=False, resolved_statuses=frozenset({pc}))
        self.assertEqual(row2["resolved_reverted_on_reply"], 1)

    def test_rep_logged_ignores_partial_history(self):
        created = T0 - timedelta(days=200)
        recs = history("A5", [
            (0.001, True, CLR, "Email Sent", "Working", REP, REP_NAME),
            (5, False, STAT, "Local Automation", "With Customer", REP, REP_NAME),
        ], first_number=40)
        self.assertFalse(ad.decompose_case("A5", recs, is_closed=False,
                                           created_date=created)["rep_logged"])
        self.assertFalse(ad.decompose_case("A5", recs, is_closed=False)["rep_logged"])
        recs[0]["FLAGS__Case_Flag_History_Number__c"] = "1"
        self.assertTrue(ad.decompose_case("A5", recs, is_closed=False,
                                          created_date=T0)["rep_logged"])

    def test_closed_statuses_need_cases(self):
        path = _write(history("A6", [(1, True, CLR, "Email Sent", "Working", REP, REP_NAME)]))
        sys.argv = ["age_decompose.py", "--cfht", path, "--closed-statuses", "Closed"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(ad.main(), 2)


class Common(unittest.TestCase):
    def test_null_relationship_counts_as_selected(self):
        require_columns([{"Id": "1", "Account": None}, {"Id": "2", "Account": {"Name": "X"}}],
                        ["Account.Name"])
        with self.assertRaises(DataError):
            require_columns([{"Id": "1"}], ["Account.Name"])

    def test_small_all_zero_handoff_group_is_allowed(self):
        asp._assert_not_all_zero([{"reason": None, "assignment_bh": 0.0}] * 6)


def _write(records: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(records, f)
    return path


if __name__ == "__main__":
    unittest.main()
