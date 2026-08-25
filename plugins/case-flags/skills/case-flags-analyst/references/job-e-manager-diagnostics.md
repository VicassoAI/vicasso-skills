# Job E — Manager diagnostics (beyond standard reports)

CFHT-dependent. The first CFHT query the analysis needs is the lazy probe; on an access error, use the
fallback message at the end of this file.

The packaged reports (reproduced on demand by **Job G** — `references/job-g-packaged-reports.md`) already give
owner-grouped 90-day averages, current high-level flags by owner, initial-response averages, and a
company-vs-customer split. Go beyond them:

- response-time *distributions* (median/percentiles, not just averages)
- the **time-with-company vs time-with-customer** split (`SUM(Business_Hours_Elapsed)` grouped by
  `Flag_Set`, by owner — controllable vs not; query in `references/soql-overload.md` §5, semantics in
  `references/field-reference.md`)
- where flags die (which `Action` clears them — e.g. agent email vs follow-up vs close)
- **follow-up time investment (team rollup)** — declared-hours estimate of follow-up-clear volume per
  report, for automation ROI framing; full methodology in `references/followup-time-investment.md` (shared
  with Job
  C's individual add-on), which draws on `references/labor-assumptions.md` for the declared per-clear minutes
  and
  triggers Job Z (`references/job-z-setup.md`) for anyone who hasn't declared yet
- ownership-churn / handoff analysis
- time-in-status and time-in-priority
- aging-band bottlenecks
- follow-up adherence
- queue-dwell vs owner-dwell
- outliers; team/cohort comparisons
- **recurrence rate** — the share of cases closed in a period that were reopened at least once (detection
  semantics canonical in `references/field-reference.md` "Recurrence"; portfolio query in
  `references/soql-timeline.md` §6), sliceable by
  owner, team, or aging speed, and broken out by trigger (reopened via customer activity vs. pulled back
  by the Follow-Up Process)

Frame the whole suite as "where are we strong and where are the bottlenecks." Bound every trend to the
history-retention window from Preflight (`FLAGS__HistoryTrackingMonths__c`).

## When CFHT is unavailable

Say so briefly and constructively, e.g.: *"Detailed history isn't available on this connection — these
analyses read the Case Flags History Tracking object, which needs explicit access. Ask your Salesforce
administrator to enable history tracking and grant access to the Case Flags History Tracking object."*
Then continue with whatever does work (e.g. job D's vitals block still works partially from Case fields
alone: initial response, current status, current flag).
