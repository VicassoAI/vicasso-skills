# SOQL — Overload inputs (Job C)

Initial-response median, `labor_per_clear`, the company-vs-customer split, load classification, the intraday
forecast, and the With-Customer soft warning.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 5. Overload inputs

### Initial-response median (always available; no CFHT)
```sql
SELECT FLAGS__Initial_Response_Business_Hours__c
FROM Case
WHERE OwnerId = '{UID}'
  AND FLAGS__Initial_Response__c != null
  AND FLAGS__Initial_Response__c = LAST_N_DAYS:90
```
Compute the median (in business hours) of the returned values.

### labor_per_clear (CFHT; this is the lazy probe) — replaces the old ongoing-response median

**Why this replaced BH-elapsed:** the old ongoing median measured *customer wait time* (how long a flag
sat before being cleared), not *rep labor time* — a flag aging for 2.5 BH before clearing didn't cost the
rep 2.5h of work; it cost them however long the actual clearing action took, while the rest of that time
they were working other cases. `labor_per_clear` sidesteps measuring effort directly and instead uses
throughput: a rep who clears fewer cases per day is naturally doing more per clear (deep technical work,
escalations, live calls); a rep clearing many lightweight cases per day is naturally doing less per clear.
It's self-calibrating per rep without needing to classify case complexity at all.

**Daily clear count (per rep, per calendar day):**
```sql
SELECT FLAGS__Owner__c, DAY_ONLY(FLAGS__Start__c) clear_day, COUNT(Id) clears
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c = '{UID}' AND FLAGS__Event__c = 'Flag Cleared'
  AND FLAGS__Action__c != 'Case Closed' AND FLAGS__Start__c = LAST_N_DAYS:90
GROUP BY FLAGS__Owner__c, DAY_ONLY(FLAGS__Start__c)
```
Excluding `Action = 'Case Closed'` matters here for the same reason as the old model — a closed-case clear
is housekeeping, not a responsiveness action, and would inflate the count on cleanup days. Days with zero
clears (weekends, PTO, OOO) simply don't appear in the GROUP BY result, which is exactly the exclusion the
metric wants — no separate filter needed for that part.

`avg_daily_clear_count` = **median** of the returned per-day clear counts (not the mean) — the same
robustness reasoning the old model used for BH elapsed applies here: a couple of unusually heavy or
unusually light days (a backlog-clearing day, a half-day before PTO) shouldn't skew what a "typical"
workday looks like. If you want to use the mean instead for some reason, first drop days more than 2× or
less than 0.5× the rep's own median day — but the median already achieves this without an extra step, so
default to it.

```
labor_per_clear = 8h ÷ avg_daily_clear_count
```

**Confidence check:** count the distinct workdays returned. Fewer than ~10 → flag the estimate as
low-confidence in the read (not enough history yet to trust the ratio) rather than presenting it with the
same authority as a well-sampled one.

If this query errors with an access error, CFHT is unavailable: fall back to the initial-response median
(above) as a stand-in for `labor_per_clear` and label the read "based on average time for initial
response" — same degraded-mode language as before.

### Time with company vs customer (CFHT; the controllable-vs-not split)
Semantics in `references/field-reference.md` ("Time with company vs customer"). Note: this BH-elapsed split is
still
the right tool for *this* question (how much of a case's life is on us vs. the customer) — it's a
different question from labor_per_clear (how much rep effort a clear costs), so both stay in the skill for
their respective jobs.
```sql
SELECT FLAGS__Flag_Set__c, COUNT(Id) intervals, SUM(FLAGS__Business_Hours_Elapsed__c) total_bh
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c = '{UID}' AND FLAGS__Start__c = LAST_N_DAYS:90
GROUP BY FLAGS__Flag_Set__c
```
For team aggregates, group by `FLAGS__Owner__c` / `FLAGS__Owner_Name__c` instead.

### Load set classification
The flagged owned cases (Ring 1) plus the follow-ups-due-today cases are the load set — a single count,
no initial/ongoing split needed since `labor_per_clear` already reflects the rep's actual average across
every case type they handle:

`estimatedLoadHours = totalLoadSetCount * labor_per_clear`

If a future baseline shows initial-pending cases measurably take longer per clear than ongoing ones,
this can be split into `labor_per_initial` and `labor_per_ongoing` (same daily-clear-count method, just
segmented by whether `FLAGS__Initial_Response__c` was null going into that clear) — but start unified
until there's data to justify the extra complexity.

### Intraday forecast inputs (job C enhancement — expected arrivals after the morning snapshot)

The snapshot above only sees demand that already exists at report time. These two queries estimate
demand that will *arrive* later the same day. Both arrival *counts* are computed exactly as before — only
the weight applied to them has changed, since `labor_per_clear` is now a single coefficient rather than
two separate medians.

**Net-new arrivals (Case object only — works even without CFHT):**
```sql
SELECT CreatedDate
FROM Case
WHERE OwnerId = '{UID}'
  AND CreatedDate = LAST_N_DAYS:90
  {CF_SCOPE}
```
In code: keep only rows where `CreatedDate`'s local time-of-day is after the report cutoff (SKILL.md
constants, 8:30 AM). Bucket the rest by day-of-week, divide each weekday's count by how many times that
weekday occurred in the 90-day window → **expected net-new arrivals for today's weekday**.

**Re-flag arrivals (CFHT — this session's lazy probe if job C's labor_per_clear query hasn't already run):**
```sql
SELECT FLAGS__Case__c, FLAGS__End__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c = '{UID}'
  AND FLAGS__Event__c = 'Flag Set'
  AND FLAGS__Flag_Set__c = false
  AND FLAGS__Start__c = LAST_N_DAYS:90
ORDER BY FLAGS__End__c ASC
```
Same treatment: keep rows where `FLAGS__End__c` local time-of-day is after the cutoff, bucket by weekday
of `FLAGS__End__c`, divide by weekday-occurrence count → **expected re-flag arrivals for today's weekday**.

```
expectedIntradayLoadHours = (expectedNetNewCount + expectedReflagCount) * labor_per_clear
totalForecastHours = estimatedLoadHours + expectedIntradayLoadHours
```
No smoothing across weekdays (SKILL.md constants) — report the raw weekday average even when the sample
is thin, and let a low-volume weekday read as a noisier number rather than silently correcting it.

On a CFHT access error, drop the re-flag term (label the forecast as "new-case arrivals only — connect
history tracking to also forecast re-flags") and keep the net-new term, since it needs no CFHT access.
`labor_per_clear` itself falls back to the initial median in this case too (see above), so the net-new
term still produces a number, just a degraded one.

**With-Customer population (soft warning, not a load adjustment — see references/job-c-overload.md):**

Live-tested against production: a literal `Status = 'With Customer'` value is common (seen in the
reference org) but is NOT guaranteed portable across every customer install — status picklists are
org-specific. Detect it rather than assuming it:

```sql
SELECT Id, CaseNumber, Status
FROM Case
WHERE OwnerId = '{UID}'
  AND FLAGS__ViewedFlag__c = null
  AND IsClosed = false
  AND FLAGS__Initial_Response__c != null
  {CF_SCOPE}
```
If the returned `Status` values include something that reads as "with customer" / "awaiting customer"
(check what's actually present rather than guessing the literal string), narrow the count to that status —
it's a tighter, more accurate population. Otherwise use the full portable result as-is. In the reference
org this mattered: the portable query returned 30 cases, but only 24 were literally `Status = 'With
Customer'` — the other 6 (`On Hold`, `Working / In Development`, `Pending Closure`, `New`) had already
gotten a first response but weren't in an "awaiting customer" state, so including them overstates the
With-Customer count. Pair whichever count you land on with the **same-day re-flag rate**:
from the re-flag query's raw rows (pull `FLAGS__Start__c` alongside `FLAGS__End__c` for this use), rate =
(count where `Start__c` date = `End__c` date) ÷ (count of all rows, i.e. all down-intervals that eventually
re-flagged). Apply that rate to the current With-Customer count to get an expected same-day bounce-back
count. **Do not add this to `totalForecastHours`** — the re-flag term above already captures this
population's aggregate historical behavior; adding both double-counts the same phenomenon.
