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

Facts below are from Salesforce Help and the linked KB articles:

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
- **Holidays.** CFHT business-hours elapsed **does skip holidays** (verified on production
  data): an interval spanning a holiday counts no hours for that day. It runs on each case's own
  aging-speed calendar.
- **SLA bands.** Band time per interval (`Business_Hours_in_Age_1..4`), so "past SLA" is measured, not
  inferred.

## Units — never repeat Salesforce's ÷24 trap

Report business time as **BH**, and where it helps also as **working days** = BH ÷ the hours in that
calendar's business day. Read those hours from the `BusinessHours` record (for example 08:00–18:00 = 10)
and pass it to the script as `--bh-per-day`. Never divide BH by 24. Show calendar time as hours or
days and label it "calendar". When cases on different aging speeds use different calendars, say that
working days aren't directly comparable across them (SKILL.md: never compare raw across aging speeds).

**Aging speed is per interval, not per case.** Each CFHT record's BH follows the calendar of the aging
speed in effect for that interval (verified on cases that changed calendars partway through).
`Case.FLAGS__Aging_Speed__c`
holds only the latest speed. So:
- Segment by `FLAGS__Aging_Speed__c` on **CFHT** (§11.2 aggregate), not on Case.
- For cases the script marks `mixed-speed`, don't convert BH to working days with a single divisor.
  Show BH and say the case changed calendars partway through.

**Holidays follow each calendar's own holiday list.** An independent recompute matched CFHT across
weekends, short days and holidays, except where a holiday wasn't attached to a calendar: that calendar
counted the day as a working day. Case Flags does what the calendar says. If BH looks high around a holiday, check the calendar's holiday list before doubting the
data, and mention it as a possible configuration gap.

## The buckets

Every CFHT interval lands in exactly one bucket. The script owns the walk: `scripts/age_decompose.py`.

| Bucket | Meaning | How it is identified |
|---|---|---|
| **Our court** | The customer is waiting on us; this is the controllable part | `Flag_Set = true` |
| ↳ of which **in a queue** | Waiting with no named owner | flag up and `Queue_Id__c` populated |
| ↳ of which **past SLA** | Time in the L4 band | `Business_Hours_in_Age_4__c` on flag-up intervals. **Never** the calendar-band `Hours_in_Age_4__c` / `Case.FLAGS__Hours_Age_4__c`: those apply the thresholds in calendar hours (a case can show many calendar hours "past SLA" with no BH past SLA) |
| **Customer court** | We are waiting on them | `Flag_Set = false`, not one of the next two |
| **Post-resolution** | The final wait before the case closed | the flag-down **stretch** that ends in the **final** `Action = 'Case Closed'` (all contiguous flag-down records, so a status change minutes before the close doesn't leave a stub customer wait), plus flag-down time in any `--resolved-statuses` |
| **Closed gap** | The case sat closed, then reopened | flag-down records from a **non-final** close until the reopen: the flag going up, or the status change that reopens it |
| **After close** | Work done while the case stayed closed | every interval **after** the final close; flag-up time inside it is reported separately |

**After close is real.** Production data shows cases whose history continues past `ClosedDate` with
no reopen, for example:
- A customer emailed an automation-closed case, the flag went up, the rep replied, and the case stayed
  closed.
- A case was parked in a status the org defines as closed while work continued.

Salesforce's Age stops at `ClosedDate`, so this time is outside it. Keep it out of resolution time and
out of the controllable median, and report it as its own line. It often signals a closed status used as
a parking spot, or closed cases that customers still write in on. The Case band rollups include
after-close flag-up time; the script accounts for that in its cross-check.

`Action = 'Case Closed'` is the close test regardless of `Event` (see `references/field-reference.md`).
**Org-specific resolved statuses.** Many orgs have a status that means "resolved, waiting out a close
timer" (for example "Pending Closure"). Flag-down time in that status isn't the customer's move. Pass
it with `--resolved-statuses "<status>"` so that time counts as post-resolution wherever it occurs,
not only in the final interval. Flag-up time in that status stays in our court, because the customer
wrote back. Read the status names off `--mode status`, and ask the person before applying this: it's
their definition, not the package's.

The post-resolution stretch is kept separate because a long "resolved, waiting to close"
dwell inflates Age without anyone waiting on anyone. Present it neutrally: it may be a deliberate
confirmation window.

**Controllable resolution time** = the case's our-court BH. That is the part of resolution time the
team owns, and it is the figure to coach on, not raw Age.

## Three lenses

### (a) Single case: "why is case 00012345 old?"

Pull §6 (`references/soql-timeline.md`) plus the Case row (§11.2
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

Run the §11.2 aggregate first for a rough headline in one query. It overstates the customer share because it can't separate resolved, closed and after-close time, so label it approximate.
For medians, segments or the finer buckets, pull §11.2 rows plus §11.3, then
`--mode cohort [--group-by Priority|Origin|Type|Reason|Owner.Name]`. `--group-by` reads Case fields, so
don't group by `FLAGS__Aging_Speed__c` here: a case whose speed changed would land under its current
speed only. Segment aging speed on CFHT instead (see Units). Lead with:

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
  script reports the count, the average and longest wait, the highest flag level it reached
  (`· L3`, from the case's ET offsets), and how each one ended:
  - **reply:** a clear from Email Sent, Internal Comment Added or Chatter Post Sent;
  - **manual:** the Clear Flag button. That is a product feature for a response made some other way
    (a phone call, a meeting), so describe it neutrally, never as "nothing was sent";
  - **other:** any other genuine clear (e.g. Local Automation, Task Completed).
  A clear by `Case Closed` or `Automatically Cleared` is housekeeping, not a response, so it isn't
  counted as cleared.
- **We waited on the customer:** each contiguous flag-down stretch of customer-court time is one wait,
  stitched across status and owner changes. Resolved-status time inside it is left out without
  splitting it. A close, a closed gap or after-close time ends it. The script reports the count, the
  average and longest wait, and how each ended: by the **customer** (an inbound email, comment,
  attachment or Chatter post), by the **Follow-Up Process** (the customer still hadn't replied), or by
  **org automation** (`Local Automation`: a Flow, trigger or other process outside the package, e.g.
  one that re-flags a case on assignment). Label org-automation-ended waits as such; they aren't the
  customer moving.

Wait totals always equal the our-court and customer-court buckets (built in the same pass). Use them to
tell the case shapes apart:
- **Many short rounds:** an old case driven by back-and-forth.
- **Few long silences:** a customer who only moves when the follow-up nudges them.
- **Slow replies on our side:** a long average or longest wait on us.

Cohort output gives the per-case medians.

### Signals (any lens; case mode prints a "Signals" table)

Facts the script finds in the history that are worth a line, all product-generic:
- **Rep-logged:** the flag was genuinely cleared within a minute of the case's creation (pass
  `CreatedDate` in `--cases`; without it, only when the first record is the case's first, so partial
  history never qualifies). Someone on our
  side logged the case (often after a call); it wasn't a customer waiting for a first answer. Say so
  beside the initial response, and leave such cases out of the skill's own initial-response medians
  (never out of Job G's packaged-report reproductions).
- **Customer contact while resolved or closed:** each inbound contact (`Flag Set` with a customer
  Action) is placed in the bucket it arrived in. A flag going up on a closed case is the product working
  as designed (the customer wrote back); report when it came, how long until a genuine clear, and the
  level reached. Don't call it a reopen unless the status reopened.
- **Resolved status reverted on reply:** a resolved status (one the person named with
  `--resolved-statuses`) changed to a non-resolved status within a minute of a genuine clear, with no
  customer contact since it was set. Case Flags never changes Status, so this is the org's own
  automation reacting to the reply. Report it only when resolved statuses were named, and attribute it
  to org automation.
- **Close fallback:** no `Case Closed` Action was found, so the close came from the transition into a
  closed status (`--closed-statuses`) or the record ending at `ClosedDate`. This happens when the org
  has "Clear flag on case close" turned off. Say the close was inferred.
- **Inactive owners:** owners on the history whose user is now inactive (`FLAGS__Owner_Is_Active__c`).
  Name them so nobody tries to follow up with them.

### Case spotlight: "which case had the most interesting story?"

For "the case worth reviewing for each person last week" and similar asks:
1. **Activity** = CFHT records owned by the person (`FLAGS__Owner__c`) whose `End` falls in the window.
   A case they touched counts, whoever owns it now.
2. **Score** each case: the number of takeaway triggers that fire, the highest flag level reached on
   any wait, reopens, priority or aging-speed changes, and returns to a previous owner. Break ties by
   our-court BH.
3. **Exclude** long-running case types the person names (e.g. onboarding or project cases); they win on
   every measure without being interesting.
4. Present the winner with Job D's timeline and the evidence behind each point of its score.

This is for learning from cases, not ranking people. The Case Flags best-practice guide says history
tracking should not be used for punitive tracking of agent performance; say that if a spotlight is
being used to compare people.

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
- **Patterns are said once.** A trigger that fires on a quarter or more of the cases in a review is a
  pattern, not an exception: state it once for the review with its count, and don't repeat it as each
  case's takeaway. The same goes for things like a status still reading "With Customer" during most of
  the waiting-on-us time on every case.
- **Group them in long reviews.** With many cases, group takeaways by kind (slow replies, long silences,
  slow to close, lifecycle) with the case links, rather than one paragraph per case.
- **One sentence per case.** If more than one matters, use a second sentence, not a list.
- **Signals can be takeaways.** A customer contact while closed, and a resolved status reverted on reply
  (org automation; only when resolved statuses were named), are triggers too (see SKILL.md).

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
- **Reopened cases.** Salesforce clears `ClosedDate` on reopen (verified: open cases with close events
  in CFHT have a null `ClosedDate`), so their Age runs from creation to now. Only a case that is
  closed **now** has a final close. Pass `--cases` with `IsClosed`, so a reopened open case's earlier
  closes count as closed gaps rather than putting everything after them in "after close". Without
  `--cases`, the script infers the state only when it's unambiguous: no close means open, and history
  ending on a close means closed. A close followed by more activity stops the run until `IsClosed` is
  supplied.
- **Open cases: the current stretch isn't in CFHT.** CFHT writes a record only when something changes.
  It never writes a running interval (verified: open cases have no record with a null `End`). The time from the last record's `End` to now is therefore missing from every CFHT total and
  from the Case rollups. The script reports it as "Since last change (calendar h, court)". The court
  comes from `Case.FLAGS__ViewedFlag__c`, so include that field in `--cases`. Business hours aren't
  recorded for it. Say so, and never fold it into the BH buckets or call it zero.
- **Neutrality.** Customer-court time is not a customer failing, and post-resolution time is not
  neglect. Report shares and let the numbers speak, just as Job H does. Vicasso's Case Flags
  best-practice guide says history tracking "should not be used for punitive tracking of agent
  performance"; True Case Age explains cases, it doesn't grade people.
- **Close detection.** The close test is `Action = 'Case Closed'`, which needs the "Clear flag on case
  close" setting. If an org has it off, pass `--closed-statuses` (the org's closed status names) with
  `--cases` so the script can fall back to the status transition or `ClosedDate`; it warns when it
  does, and refuses `--closed-statuses` without `--cases`, since the history alone can't tell open from
  closed there. `--closed-statuses` also keeps a closed gap open across a move between two closed
  statuses.
- **Links.** Render case numbers as links per SKILL.md.
- **Aggregate before raw.** If the question only needs a rough our-vs-customer split, the §11.2 aggregate is enough (labelled approximate). Anything presented as the customer share, a per-case number or a wait count needs the script.
