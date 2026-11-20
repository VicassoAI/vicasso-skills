# Job I — True Case Age ("why is this case old?")

Triggers: "true case age", "case age report", "why is this case so old", "how old is our backlog",
"aging backlog", "how long were we sitting on it", "time in status", "controllable resolution time",
"how much of our resolution time is us vs the customer", "which old cases is nobody watching".

Salesforce's Age is one number: created → now (open) or created → closed. True Case Age keeps that
number and **breaks it down by whose court the ball was in**, using Case Flags History Tracking (CFHT).
"True" means *complete*, not "Salesforce is wrong". Always show the standard figure beside the
breakdown, labelled "what Salesforce's Age shows", and never call it inaccurate. The calendar total,
minus any after-close time, reconciles to it.

## Why this beats the standard options (say this when someone asks "why not just use Age?")

Facts below are from Salesforce Help and the linked KB articles, read 2026-11-20:

- **Age** is report-only. It is not a real field (it can't go on layouts or list views), it can be shown
  in days, hours or minutes, and it **ignores holidays**.
- **Business Hours Age** has to be **activated by Salesforce Support** (KB 000387290). It can't be used in
  orgs whose default business hours are 24/7. It is only available on standard Case report types, not
  custom report types, and it **can't be filtered or bucketed**. Users without access to Closed
  Date/Time lose it. Its "days" unit is **business hours ÷ 24** (KB 000382808): a case open 14 working
  days at 9 h/day shows as **5.25 days**. Holidays are ignored here too.
- **Formula-field workarounds** (KB 000388264) are calendar-only.
- **Standard Case History** reports carry old/new values and "business hours since last update", but
  they can't give time in each status out of the box. The Salesforce Labs "Case Age and Status Changes"
  app adds time in status only, through an unmanaged trigger.

What Case Flags adds:
- **Court.** CFHT records whether the customer was waiting on us (`Flag_Set = true`) or we were waiting
  on them.
- **Holidays.** CFHT business-hours elapsed **does skip holidays**. Verified live on 2026-11-20: a
  Thursday-to-Tuesday interval spanning the org's Jul 3 holiday counted 19.2 BH (Thursday, Monday and a
  sliver of Tuesday, with Friday excluded). It runs on each case's own aging-speed calendar.
- **SLA bands.** Band time per interval (`Business_Hours_in_Age_1..4`), so "past SLA" is measured, not
  inferred.

## Units — never repeat Salesforce's ÷24 trap

Report business time as **BH**, and where it helps also as **working days** = BH ÷ the hours in that
calendar's business day. Read those hours from the `BusinessHours` record (for example 08:00–18:00 = 10)
and pass it to the script as `--bh-per-day`. Never divide BH by 24. Show calendar time as hours or
days and label it "calendar". When cases on different aging speeds use different calendars, say that
working days aren't directly comparable across them (SKILL.md: never compare raw across aging speeds).

**Aging speed is per interval, not per case.** Each CFHT record's BH follows the calendar of the aging
speed in effect for that interval. Verified 2026-11-20: 22 of 22 intervals on two cases that moved from
a 10-hour calendar to a 6-hour one matched their own interval's calendar. `Case.FLAGS__Aging_Speed__c`
holds only the latest speed. So:
- Segment by `FLAGS__Aging_Speed__c` on **CFHT** (§11.2 aggregate), not on Case.
- For cases the script marks `mixed-speed`, don't convert BH to working days with a single divisor.
  Show BH and say the case changed calendars partway through.

**Holidays follow each calendar's own holiday list.** In the same check, 28 of 30 cases matched an
independent recompute to within 0.01 BH across weekends, a short-Friday calendar and four holidays; the
other 2 were the mixed-speed cases above. Two calendars skipped all four holidays. One 07:00–23:00
calendar did **not** skip Juneteenth, because that holiday wasn't attached to it. Case Flags does what the
calendar says. If BH looks high around a holiday, check the calendar's holiday list before doubting the
data, and mention it as a possible configuration gap.

## The buckets

Every CFHT interval lands in exactly one bucket. The script owns the walk: `scripts/age_decompose.py`.

| Bucket | Meaning | How it is identified |
|---|---|---|
| **Our court** | The customer is waiting on us; this is the controllable part | `Flag_Set = true` |
| ↳ of which **in a queue** | Waiting with no named owner | flag up and `Queue_Id__c` populated |
| ↳ of which **past SLA** | Time in the L4 band | `Business_Hours_in_Age_4__c` on flag-up intervals. **Never** the calendar-band `Hours_in_Age_4__c` / `Case.FLAGS__Hours_Age_4__c`: those apply the thresholds in calendar hours (one live case showed 80 h "past SLA" against 0 BH) |
| **Customer court** | We are waiting on them | `Flag_Set = false`, not one of the next two |
| **Post-resolution** | The final wait before the case closed | the flag-down **stretch** that ends in the **final** `Action = 'Case Closed'` (all contiguous flag-down records, so a status change minutes before the close doesn't leave a stub customer wait), plus flag-down time in any `--resolved-statuses` |
| **Closed gap** | The case sat closed, then reopened | flag-down interval starting right after a **non-final** close |
| **After close** | Work done while the case stayed closed | every interval **after** the final close; flag-up time inside it is reported separately |

**After close is real and common.** The 2026-11-20 check of 30 live cases found 2 cases with history
continuing past `ClosedDate` and no reopen:
- A customer emailed an automation-closed case, the flag went up, the rep replied, and the case stayed
  closed.
- A case was parked in a status the org defines as closed ("Bug Fix Pending") while work continued for
  a week.

Salesforce's Age stops at `ClosedDate`, so this time is outside it. Keep it out of resolution time and
out of the controllable median, and report it as its own line. It often signals a closed status used as
a parking spot, or closed cases that customers still write in on. The Case band rollups include
after-close flag-up time; the script accounts for that in its cross-check.

`Action = 'Case Closed'` is the close test regardless of `Event` (see `references/field-reference.md`).
**Org-specific resolved statuses.** Many orgs have a status that means "resolved, waiting out a close
timer" (one live org: "Pending Closure"). Flag-down time in that status isn't the customer's move. Pass
it with `--resolved-statuses "Pending Closure"` so that time counts as post-resolution wherever it occurs,
not only in the final interval. Flag-up time in that status stays in our court, because the customer
wrote back. Read the status names off `--mode status`, and ask the person before applying this: it's
their definition, not the package's.

The trailing post-resolution interval is kept separate because a long "resolved, waiting to close"
dwell inflates Age without anyone waiting on anyone. Present it neutrally: it may be a deliberate
confirmation window.

**Controllable resolution time** = the case's our-court BH. That is the part of resolution time the
team owns, and it is the figure to coach on, not raw Age.

## Three lenses

### (a) Single case: "why is case 00012345 old?"

Pull §6 (`references/soql-timeline.md`, adding the two `in_Age_4` fields) plus the Case row (§11.2
fields), then run `age_decompose.py --mode case`. Render:

1. **One line:** "Salesforce's Age shows 8.1 days. Of the 60.6 business hours inside that, 15.6 were
   waiting on us (none past SLA) and 45 were waiting on the customer."
2. A small table of the buckets in BH, working days and share.
3. The waits on each side (count, replies or follow-up-ended, average, longest), from the script's
   waits table.
4. What drove it: handoffs, owner returns (a case going back to a previous owner), the longest single
   wait (`run_stitch.py --mode worst-run`), and reopens. If Job D's narrative is wanted, hand off to it
   rather than duplicating it.
5. A **takeaway**, only if the case trips a trigger (see "Takeaways" below).

### (b) Open backlog: "how old is our backlog?" / "what is nobody watching?"

Case fields only, no CFHT needed. Run §11.1, then `--mode backlog`. Bucket edges come from SKILL.md
constants. Per age bucket, show: open cases, flagged (failing loudly, the customer is waiting),
follow-up set (we're waiting, with a scheduled check-in), and **forgotten** (not flagged and no
follow-up date, so nothing will bring it back to anyone's attention). List the oldest forgotten cases as
links, with owner and status. Forgotten is the actionable list. Present it as "nothing is scheduled to
surface these", not as blame.

For flagged backlog cases, the band rollups give our-court time up to the last recorded change. The
time since then isn't in CFHT or the rollups.

### (c) Closed cohort: "how much of our resolution time is us?"

Run the §11.2 aggregate first. It answers the headline (our-court vs customer-court share) in one query.
For medians, segments or the finer buckets, pull §11.2 rows plus §11.3, then
`--mode cohort [--group-by Priority|Origin|Type|Reason|FLAGS__Aging_Speed__c|Owner.Name]`. Lead with:

- **Share of age by bucket**, and **controllable BH per case** (median, p90, mean and tail ratio; the
  mean/median tail rule from SKILL.md applies).
- **SLA exposure:** the number of cases with any past-SLA time and the total BH past SLA.
- **Handoff tax:** median handoffs, and the cases where ownership returned to a previous owner.
- **Calendar vs business gap:** calendar hours per BH. High values mean a case aged mostly outside
  working hours (weekends, overnight); that is exposure, not neglect.
- **Reopened** count. Recurrence detail belongs to Job E.

### Waits on each side (any lens)

Every case row also counts the back-and-forth:
- **Customer waited on us:** each contiguous flag-up stretch inside Salesforce's Age is one wait. The
  script reports the count, how many ended in a genuine reply, and the average and longest wait.
- **We waited on the customer:** each contiguous flag-down stretch of customer-court time is one wait,
  stitched across status and owner changes. Resolved-status time inside it is left out without
  splitting it. A close, a closed gap or after-close time ends it. The script reports the count, how
  many were ended by the Follow-Up Process (the customer still hadn't replied), and the average and
  longest wait.

Wait totals always equal the our-court and customer-court buckets (built in the same pass). Use them to
tell the case shapes apart:
- **Many short rounds:** an old case driven by back-and-forth.
- **Few long silences:** a customer who only moves when the follow-up nudges them.
- **Slow replies on our side:** a long average or longest wait on us.

Cohort output gives the per-case medians.

### Takeaways (any per-case output: this job, Job D, multi-case reviews)

When a case has something **outside the normal** about it, end its entry with one **Takeaway:** sentence
that says what drove the case's age or what to look at. When nothing is unusual, write no takeaway line:
no filler like "nothing notable", because the absence is the signal. The triggers and their thresholds
are in SKILL.md's constants ("Takeaway triggers"). Evaluate every trigger; if several fire, lead with the
one that explains the most time.

How to write one:
- **Explain, with the numbers.** For example: *"Old because of the number of rounds (27 each way), not
  slow replies: our waits averaged 0.8 BH."* Or: *"Every customer wait ended only when the follow-up
  re-flagged it; the customer never wrote back on their own."*
- **Neutral, like the rest of the skill.** Describe the shape; don't judge a person. Customer silence
  isn't the customer's failing, and a parked status may be deliberate. Say what's worth checking,
  for example "if On Hold here means parked on our side, the customer share overstates it".
- **Org-wide patterns are said once.** If a pattern shows up across most cases (one live org had its
  status still reading "With Customer" during ~60% of waiting-on-us time on every case), say it once
  for the review, not on every case.
- **One sentence per case.** If more than one matters, use a second sentence, not a list.

### Time in status (any lens, needs `Track_Case_Status__c`)

`--mode status --customer-statuses "<statuses that mean waiting on customer>"` splits each status's time
by court. Read the status names off the table and choose the waiting-on-customer ones from their
names. Ask only if it is genuinely ambiguous. **Flag up while the status says "waiting on customer"**
means the case is labelled as the customer's move when the customer is actually waiting on us. Report
it as a labelling or automation question, not as a rep failing. One common, benign cause is a status
that doesn't change on an inbound email: the flag goes up, but the status still reads "With Customer".

If status tracking is off, use the §11.4 `CaseHistory` fallback (calendar only, no court) and label it.

## Degraded read (CFHT unavailable)

Say so briefly, using Job E's message. Then still deliver:
- the full backlog lens (b);
- per closed case: Salesforce Age (calendar, from `CreatedDate`/`ClosedDate`), **our-court BH = sum of
  `Business_Hours_Age_1..4`**, past-SLA BH = `Business_Hours_Age_4`, and initial response
  (`FLAGS__Initial_Response_Business_Hours__c`).

Customer-court time, queue time, post-resolution time, handoffs and status splits all need CFHT, so name
them as unavailable rather than estimating them. Don't derive customer time as calendar minus our-court
BH, because that mixes calendar hours with business hours.

## Guardrails

- **Partial history.** If CFHT starts after `Case.CreatedDate` (retention window or pre-install), the
  script warns. Say the breakdown covers only part of Age and keep those cases out of cohort medians, or
  bound the cohort to cases created inside the window. Apply Job G's post-install cutoff the same way.
- **Reopened cases.** Salesforce clears `ClosedDate` on reopen (verified live: open cases with close
  events in CFHT have a null `ClosedDate`), so their Age runs from creation to now. Only a case that is
  closed **now** has a final close. Pass `--cases` with `IsClosed`, so a reopened open case's earlier
  closes count as closed gaps rather than putting everything after them in "after close". Without
  `--cases`, the script infers the state only when it's unambiguous: no close means open, and history
  ending on a close means closed. A close followed by more activity stops the run until `IsClosed` is
  supplied.
- **Open cases: the current stretch isn't in CFHT.** CFHT writes a record only when something changes.
  It never writes a running interval (verified live: 0 of 59 open cases had a record with a null
  `End`). The time from the last record's `End` to now is therefore missing from every CFHT total and
  from the Case rollups. The script reports it as "Since last change (calendar h, court)". The court
  comes from `Case.FLAGS__ViewedFlag__c`, so include that field in `--cases`. Business hours aren't
  recorded for it. Say so, and never fold it into the BH buckets or call it zero.
- **Neutrality.** Customer-court time is not a customer failing, and post-resolution time is not
  neglect. Report shares and let the numbers speak, just as Job H does.
- **Links.** Render case numbers as links per SKILL.md.
- **Aggregate before raw.** If the §11.2 aggregate answers the question, stop there.
