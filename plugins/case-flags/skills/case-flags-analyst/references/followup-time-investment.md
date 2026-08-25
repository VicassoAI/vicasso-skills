# Follow-up time investment (shared: Job C add-on, Job E team rollup)

Answers "how much time is going into follow-up clears, and what would automating them buy back" — an
ROI/exposure question, not a load-model input. Keep this fully separate from `labor_per_clear`
(references/job-c-overload.md): that metric stays unified and effort-agnostic on purpose. This one exists
because a
manager or rep wants a defensible hours number for a business case, and CFHT can supply the *volume* half
of that (precisely) while `references/labor-assumptions.md` supplies the *time-per-clear* half (declared, not
measured).

CFHT-dependent — this is a lazy CFHT probe if nothing else in the session has already queried it.

## Step 1 — Classify genuine clears by opening trigger

This generalizes the recurrence-trigger classification in `references/field-reference.md` ("Recurrence") to
*every*
flag-up cycle, not just reopens after a close.

Pull CFHT for the scoped owner(s) over the trailing 90 days, ordered by Case then Start (same shape as
`references/soql-overload.md` §5's daily-clear-count query, but pulling `FLAGS__Case__c`, `FLAGS__Start__c`,
`FLAGS__End__c`, `FLAGS__Flag_Set__c`, `FLAGS__Event__c`, `FLAGS__Action__c` rather than a GROUP BY —
see §8 in `references/soql-followup-investment.md`). In code, per case:

1. Walk the ordered records; group each contiguous run of `FLAGS__Flag_Set__c = true` records — this is
   one flag-up cycle (same run definition as the ongoing-response-time method in
   `references/field-reference.md`).
2. **Opening trigger** = `FLAGS__Action__c` of the record *immediately before* the run starts (that
   record's `Event = 'Flag Set'` describes the transition into this run). If the run starts at the very
   first record for the case, there is no preceding record — the case was flagged at creation; exclude
   it from the follow-up/other split entirely (it's neither) rather than guessing.
3. **Genuine clear** = the run's last record has `Event = 'Flag Cleared'` AND `Action != 'Case Closed'`
   (excludes the housekeeping close shape — see references/field-reference.md "Close events come in two
   shapes").
4. Bucket genuine clears into `followup_clears` (opening trigger = `Follow-Up Process`) and
   `other_clears` (any other opening trigger, excluding the at-creation cases from step 2).

**Do not use the run's BH-elapsed for anything here.** It was tested directly against this exact
follow-up-vs-other split and the result contradicted a "follow-ups are fast" hypothesis (follow-up-
triggered runs actually ran *longer* on median, 23 vs 15 min, with near-identical means ~41 min) —
because BH-elapsed measures customer/queue wait time, not rep labor, for the same reason `labor_per_clear`
replaced it as the load weight. Only the **count** of follow-up vs. other genuine clears is a reliable
signal here; the time-per-clear has to come from the declared assumptions instead.

## Step 2 — Apply declared time

From `references/labor-assumptions.md`, look up the person's row (or the team default if none):

```
followup_hours = count(followup_clears) * minutes_per_followup_clear / 60
other_hours    = count(other_clears)    * minutes_per_other_clear    / 60
```

If `references/labor-assumptions.md` shows `source: default (not yet declared)` for this person, still compute
the
number but label it clearly as based on an unconfirmed default, and trigger Job Z
(`references/job-z-setup.md`) as a
short add-on to the same response rather than blocking it.

## Step 3 — Reality-check against observed batching (optional, informational)

Separately from the declared-hours estimate, compute the median gap between consecutive same-day
`followup_clears` timestamps (their run's final `FLAGS__End__c`), across the window. This tests whether
the person's *actual* pace when batching follow-ups looks faster or slower than their declared
`minutes_per_followup_clear` — e.g. a declared 6 minutes against an observed 3-minute median gap on
batching days is worth surfacing as a data point, not a correction:

> *On days where you clear 3+ follow-ups, they typically go out ~3 minutes apart — worth a look against
> your declared 6-minute estimate, though back-to-back timestamps can undercount true effort if you're
> drafting several at once before sending.*

Never silently adjust the declared number based on this — it's a prompt for the person to reconsider their
own declaration, not a model correction. State the batching pattern (or its absence) honestly either way;
plenty of people won't show a batching pattern at all, and that's a fine, unremarkable answer too.

## Output

**Job C add-on (individual banner):** one line beneath the load banner, e.g.:
> *Follow-ups: 42 clears this quarter (~4.2h at your declared 6 min each) — a solid automation candidate
> if you want to build the case for it.*

**Job E add-on (team rollup):** a small table, one row per report — follow-up clear count, declared/team
default minutes, resulting hours, and each person's `source` (`declared` vs `default`) so the manager can
see at a glance whose numbers are confirmed vs. assumed:

| Person | Follow-up clears (90d) | min/clear | Est. hours | Source |
|---|---|---|---|---|
| Sample Person | 42 | 6 | 4.2 | default (not yet declared) |

Sum the "Est. hours" column for a team total — this is the number that supports an automation business
case (same spirit as the existing E2CP/Case Split exposure write-ups, just for internal process rather
than a customer feature ask).
