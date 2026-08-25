# Job B — Manager / team view (role-aware)

Triggers: "how is my team doing", "who's overloaded", "who needs help".

Resolve direct reports via the standard hierarchy (`User.ManagerId`) — `references/soql-team-view.md` §7. If
the person isn't a
manager (no direct reports), say so and offer the individual My Day instead.

## Query team-wide, not per person

Do **not** loop the individual queries once per report — that scales linearly with team size. Run the
team-wide variants in `references/soql-team-view.md` §7, each covering *all* reports in one call with `OwnerId
IN ({REPORT_IDS})`
(or `FLAGS__Owner__c IN (...)` on CFHT), then group per owner in code:

1. **Flagged roster inputs** — one Ring-1-style query across all reports (§7.1); group by `OwnerId`.
2. **Follow-ups due today** — one query across all reports (§7.2); count per owner.
3. **Initial medians** — one query pulling `FLAGS__Initial_Response_Business_Hours__c` for all reports over
   the trailing 90 days (§7.3); compute each owner's median in code.
4. **labor_per_clear** — the daily-clear-count method across all reports (§7.4), grouped per owner per
   day. This is the session's lazy CFHT probe: if it errors with an access error, CFHT is unavailable —
   fall back to each owner's initial median in its place and label the load estimates accordingly. Flag
   any owner with fewer than ~10 workdays of sample as low-confidence.
5. **Intraday forecast** — net-new and re-flag arrival inputs across all reports (§7.5), banded per person
   the same way as the individual view (`references/job-c-overload.md`, "Intraday forecast term"). Net-new
   works even
   without CFHT; drop the re-flag half only on a CFHT access error.
6. **With-Customer soft warning** — per-owner counts and same-day re-flag rates (§7.6). Informational only;
   never added into the roster's load-hours column.

**Integration users in the hierarchy.** API/integration accounts (e.g. an "… API User") can appear as
direct reports. If a report has zero case activity across every input, drop them from the roster with a
one-line note rather than showing an empty row.

## Output

Produce a roster: per person — flag count, # overdue (ET4 in the past), follow-ups due today, snapshot
load hours, forecast load hours (shown side by side, not merged — `references/job-c-overload.md` banner format),
band, and a With-Customer same-day-bounce-back note where relevant. Band on the forecast total, not the
snapshot alone — a person showing empty right now may still be Balanced or Heavy once the day's typical
arrivals are counted, and that's exactly the read a manager needs before reassigning work.

Surface a team-level "Start here" (most overdue case across the team) and call out the imbalance — who is
overloaded and who is light — since that is where reassignment decisions get made (complementing the
Switchboard's visual reassignment, not replacing it).
