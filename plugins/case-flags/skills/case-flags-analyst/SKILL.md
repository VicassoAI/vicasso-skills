---
name: case-flags-analyst
license: Apache-2.0
compatibility: Requires a connected Salesforce MCP server with read access to the Case Flags managed package (FLAGS__), and Python 3.9+ for the bundled scripts.
description: Personal and managerial responsiveness analyst for the Vicasso Case Flags managed package, working over a connected Salesforce MCP. Use this whenever someone asks about their Case Flags work in plain language — "what's my day look like", "my flagged cases", "what should I work on", "am I overloaded / do I have a light day", "what's due today", "what's falling through the cracks" — or, for managers, "how is my team doing", "who's overloaded", "who needs help". Also use for Case Flags responsiveness questions - initial response time, ongoing responsiveness, interpreting Case Flags History Tracking, and going beyond the standard packaged reports. Trigger even when the person doesn't say "Case Flags" by name, as long as the org has Case Flags installed and the request is about flagged cases, follow-ups, response times, or triaging support work by urgency.
---

# Case Flags Analyst

Help a Case Flags user start their day with almost no input: tell them exactly what to work on, in the
right order, whether they can realistically clear it, and (for managers) which of their people need help.
Everything keys off the flag, which works like a countdown timer toward an SLA breach.

This skill is built to be portable across customer orgs: rely only on the managed-package schema
(`FLAGS__`, and optionally `FLAGS_METRICS__`), read the org's configuration before doing anything, and
adapt. Never hardcode anything org-specific (follow-up field names, aging thresholds, business-hours mode).

## How this skill is organized

SKILL.md holds only what every job needs: the preflight, the mental model, shared constants, and defaults.
Each job's full instructions live in its own reference file. **Identify the job, then read its file before
running any job queries** — do not work from memory of a job you haven't read this session.

| The person is asking… | Job | Read |
|---|---|---|
| "what's my day look like", "my flagged cases", "what should I work on", "what's due today" | A — My Day | `references/job-a-my-day.md` (also read job C for its banner) |
| "how is my team doing", "who's overloaded", "who needs help" | B — Manager / team view | `references/job-b-manager-view.md` |
| "am I overloaded", "do I have a light day" | C — Overload read | `references/job-c-overload.md` |
| "walk me through case X", "what's the history on this case", "background before I call this customer" | D — Timeline interpretation | `references/job-d-timeline-interpretation.md` |
| distributions, bottlenecks, recurrence rate, team analytics beyond packaged reports | E — Manager diagnostics | `references/job-e-manager-diagnostics.md` |
| "how long does it take to assign work vs respond", "time to assign vs time to respond", "does self-assigning skew our numbers", "split initial response into assignment time and response time" | F — Assignment/response decomposition | `references/job-f-assignment-response-split.md` |
| "run the Case Flags reports", "the packaged metrics", "average time to respond by owner", "current red/black flags by owner", "recreate the Case Flags dashboard", or any of the six shipped reports by name | G — Packaged reports | `references/job-g-packaged-reports.md` |
| "how has [account] experienced us", "account responsiveness", "how responsive is [account]", "responsiveness for [account] before the renewal", "which accounts are we slowest to", "which customers are least responsive to us", "how does [account] compare to normal / to our average" | H — Account responsiveness (two-sided) | `references/job-h-account-responsiveness.md` |
| "how much time do follow-ups cost me/us", "set up my time assumptions" — or automatically, once, the first time a follow-up-time-investment read is needed for someone who hasn't declared yet | Z — Setup: labor assumptions | `references/job-z-setup.md` |

Shared plumbing: `references/field-reference.md` is canonical for **field meanings and data
semantics** (including the run-based ongoing-response computation and recurrence detection). Ready
queries live in per-job SOQL files, section-numbered so any `§N` citation identifies both file and
section. **Read only the SOQL file(s) your job needs.**

| § | File | Covers |
|---|---|---|
| §1 | `references/soql-preflight.md` | Preflight config read, plus the `{UID}` / `{CF_SCOPE}` placeholder conventions every other SOQL file uses |
| §2–§4 | `references/soql-my-day.md` | Job A — flagged rings, follow-ups due today, stalest open cases |
| §5 | `references/soql-overload.md` | Job C — initial median, `labor_per_clear`, company-vs-customer split, intraday forecast |
| §6 | `references/soql-timeline.md` | Jobs D, E — single-case CFHT pull, compression, recurrence |
| §7 | `references/soql-team-view.md` | Job B — every roster input bulked across all direct reports |
| §8 | `references/soql-followup-investment.md` | Jobs C, E — raw ordered pull for opening-trigger classification |
| §9 | `references/soql-assignment-split.md` | Job F — case population, paginated CFHT pull, actor cross-check |
| §10 | `references/soql-account.md` | Job H — two-sided account rollup, concentration, compare-to-normal |

Job files point into these rather than restating them.

## Computation — prefer the scripts over doing it by hand

`scripts/` holds deterministic Python for the reductions this skill repeats. The reference files
stay canonical for *semantics*; the scripts own the *arithmetic*. **Order of preference:
SOQL aggregate → script → inline reasoning.** If a `GROUP BY` returns the number, never pull raw
rows to compute it; if it needs a sort or a stateful walk, use the script; reason inline only when
the answer is a judgment rather than a calculation.

| Need | Script |
|---|---|
| Merge paginated CFHT pages, dedupe, reconcile against `COUNT(Id)`, cache | `scripts/cfht_merge.py` |
| Contiguous flag-up runs → ongoing response, follow-up split, worst wait, customer turnaround | `scripts/run_stitch.py` |
| Job F assignment vs response decomposition | `scripts/assignment_split.py` |
| Any median / percentile / distribution, and `labor_per_clear` | `scripts/stats.py` |

Write connector results to JSON, then pass the path (`--input`, or `--pages`/`--cfht`/`--cases`).
Read `scripts/README.md` for the calling convention before first use. Two things worth knowing up
front: the scripts **raise rather than warn** on the silent-zero trap and on an impossible Job F
value such as a negative response time, so an error exit means stop and fix, not report with a
caveat; and pulls cached in the session cache directory (`cfht_merge.py` prints the path) should
be reused across jobs in a session instead of re-queried.

Not scripted on purpose: Preflight interpretation, business-hours inference, Job D's lens choice
and all narrative, the neutrality guardrails. Those are judgment.

`references/labor-assumptions.md` holds **declared, editable** per-clear time assumptions (CFHT can't
measure rep effort, only timestamps — see references/field-reference.md), and
`references/followup-time-investment.md`
is the shared computation both Job C's add-on and Job E's team rollup use to turn follow-up-clear volume
into an hours estimate. Edit `references/labor-assumptions.md` directly to change the numbers; Job Z
(`references/job-z-setup.md`) is how a person declares their own.

## What runs without history data

The personal **My Day** view (A), the **manager roster** (B), and the **overload** read (C, degraded) run
entirely off Case fields and standard objects, so they work in any org with Case Flags installed. Two
capabilities need the Case Flags History Tracking (CFHT) object — **single-case timeline interpretation**
(D) and the **manager diagnostic suite** (E) — plus the *precise* ongoing-response median in C, the
**follow-up time-investment** add-on (Job C/E, `references/followup-time-investment.md`), and the full two-sided
**account responsiveness** read (H). CFHT requires explicit object permissions and may not be reachable on a
given connection; probe lazily (below) and degrade gracefully rather than failing. Job H degrades to a
Case-field-only read (initial-response median + current flag-state snapshot) when CFHT is unavailable. Job Z
(declaring labor assumptions) itself needs no CFHT — it's a plain read/write against
`references/labor-assumptions.md` —
but there's little reason to run it before CFHT is confirmed available, since its output only feeds a
CFHT-dependent read.

**CFHT availability — probe lazily.** Only consider CFHT features if the Preflight shows
`FLAGS__Enable_History__c = true`. Don't spend a round trip on a standalone probe: attempt the first CFHT
query the job actually needs, and treat an object-access error ("sObject type … is not supported" / no
access) as CFHT-unavailable for the rest of the session — then follow that job's documented fallback.

---

## Step 1 — Preflight (always first)

Run the Preflight query (`references/soql-preflight.md` §1) and read the current user's identity from the
connection. From the Preflight, hold these for the rest of the session:

- **Processing mode** — if `FLAGS__Organization_Wide__c` is false the org is *selective*; scope every case
  query with `AND FLAGS__Enable_Case_Flags__c = true` so you don't list cases Case Flags ignores.
- **Follow-up field names** — `FLAGS__Follow_Up_On_Field__c` and `FLAGS__Next_Steps_Field__c` give the
  org-specific Case field API names. They cannot be guessed (one real org uses `Next_Step_s__c`), so always
  read them. If `FLAGS__Enable_Follow_Up_Process__c` is false, skip the follow-up bucket entirely.
- **History availability** — only consider CFHT features if `FLAGS__Enable_History__c` is true; the
  individual `Track_*` flags tell you which CFHT analyses are even possible. Bound every trend to
  `FLAGS__HistoryTrackingMonths__c`.
- **Business hours** — present age/timing in whatever dimension the org runs on; you never ask the user. Do
  **not** infer "no business hours" from a null `FLAGS__BusinessHoursId__c` at the org-default row: a null
  there is common even when business-hours mode is fully active (a per-speed or per-entitlement calendar
  applies). Confirm from the data instead — if `FLAGS__Business_Hours_Elapsed__c` runs well below
  `FLAGS__Hours_Elapsed__c`, BH is in effect; lead with BH.

Resolve case links from the org base URL: render `CaseNumber` as a link to
`/lightning/r/Case/{Id}/view`. If the base URL can't be determined, show the plain number.

## The mental model (why the ordering works)

A flag means the ball is in the org's court — the customer is waiting. Clearing it (a reply, a comment)
puts the ball back in the customer's court. When a flag is raised, four escalation datetimes populate:
`CaseFlagsEscalationTime1..4`. ET1 is the moment it was raised; ET4 is the SLA breach. The flag color/level
is just a visual readout of where the case sits on its own timer — it does **not** drive priority.

What drives priority is ET4. Sorting flagged cases by `FLAGS__CaseFlagsEscalationTime4__c` **ascending**
produces exactly the right work order in one step: cases whose breach time is furthest in the past sort
first (waiting longest past the buzzer), then you cross "now" into the cases about to breach soonest. Use
`FLAGS__ViewedFlag__c != null` as the "is it flagged" test (it is color-independent and reliable; the
escalation fields go null when the flag clears, so they never mis-sort a cleared case).

Compute the level for display from the current time vs the escalation datetimes: level = how many of
ET1..ET4 are at or before now (a speed can collapse early levels, so a case may be "born" above L1). The
breach timing is always measured against ET4.

---

## Tunable constants (single source — adjust here, nowhere else)

```
PROVISIONAL THRESHOLDS — tune against real data before treating as settled.

Overload bands (vs a flat 8-business-hour day; job C):
  Light       load <= 50%  (<= 4h)   spare capacity
  Balanced    50–100% (4–8h)         full but doable
  Heavy       100–150% (8–12h)       more than a day; prioritize or ask for help
  Overloaded  > 150% (> 12h)         can't reasonably clear today; needs help / reassignment

Median window (job C): trailing 90 days (do not extend even if retention allows).
labor_per_clear baseline (job C — replaces the old ongoing-median weight): needs a minimum of ~10
  distinct workdays of CFHT clear history in the trailing 90-day window for a stable estimate. Fewer than
  that → flag the read as low-confidence rather than presenting it at full authority.
Long-gap bar, flag-DOWN intervals (job D tag C): 16 business hours (~2 business days).
  (Flag-UP intervals compare against the case's own aging-threshold gaps, not a constant.)

Intraday forecast (job C — expected arrivals after the morning snapshot):
  Report cutoff: 8:30 AM local. Arrivals timestamped after this count as "intraday forecast,"
    not snapshot — don't double-count something already visible in the snapshot as also forecast.
  Weekday window: trailing 90 days, same as the medians above.
  No smoothing across weekdays — a rep with a thin history on a given weekday (new to the role, new
    to a queue) gets a noisier forecast number for that weekday. Let it read as low-confidence rather
    than quietly correcting it toward some other average; don't fabricate stability the data doesn't have.

Account outlier / concentration (job H — per side, our-court and customer-court):
  Concentration flag:  top case >= 30% of the side's total time, OR top-3 cases >= 50%.
    → the account's number is one (or a few) cases wearing a trenchcoat; say so and name them.
  Tail flag (mean vs median):  mean >= 1.5x median on that side → a tail exists; an outlier is
    present even when the median looks fine. Always report both and note the gap.
  Stall bar (single continuous interval):  >= the org's ET3 offset (FLAGS__TimeOffset3__c, the red
    band) — one wait long enough to age the flag into red on its own. Read the offset from Preflight;
    do NOT hardcode a number (one real org runs 0/5/10/20 BH → stall bar = 10 BH).
    A worst case whose largest single interval clears this bar is a STALL (a dropped ball);
    one whose time is spread across many intervals with no single interval reaching it is a
    VOLUME/ITERATION outlier (complex, many-round case — fast per reply, not neglected).
```

---

## Defaults, scope, and edge cases

- **Scope rings** default to all three (own + team + queue) for the flagged view; follow-ups and Open Cases
  are owned-only. If the user asks to narrow ("just my own"), honor it.
- **Selective orgs**: every bucket is scoped to `FLAGS__Enable_Case_Flags__c = true`.
- **Caps**: top 5 per section + "+N more"; offer to expand on request.
- **Aging-speed awareness**: never compare raw flag age across cases on different aging speeds as if equal;
  the speed is on `FLAGS__Aging_Speed__c`.
- **Empty states**: no flagged cases → say the queue is clear and move to follow-ups / Open Cases. No
  reports at all → confirm Case Flags is installed and the user owns cases.
- **Time**: present timing in the org/user's locale; small rounding is fine — this is an estimate.
- **Output style**: plain, scannable, sectioned tables (no interactive widget — that is what Switchboard is
  for, and plain output stays portable to other assistants).
- **Never** invent fields. If a referenced field errors, re-check the Preflight output and the field
  reference rather than guessing an alternative.
