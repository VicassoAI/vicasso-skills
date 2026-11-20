# SOQL — True Case Age (Job I)

Backlog snapshot, closed-cohort population, the cohort CFHT pull, and the `CaseHistory` fallback for
time-in-status.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`. `{OWNER_SCOPE}` below means whichever owner filter the ask needs
> (`OwnerId = '{UID}'`, `OwnerId IN ({REPORT_IDS})`, or nothing for org-wide).

## 11.1 Open backlog (lens b — Case fields only, no CFHT)

```sql
SELECT Id, CaseNumber, Subject, Status, Priority, Origin, Owner.Name, CreatedDate,
       FLAGS__ViewedFlag__c, FLAGS__Case_Flag_Business__c, FLAGS__Aging_Speed__c,
       FLAGS__CaseFlagsEscalationTime4__c, {FOLLOW_UP_ON},
       FLAGS__Business_Hours_Age_1__c, FLAGS__Business_Hours_Age_2__c,
       FLAGS__Business_Hours_Age_3__c, FLAGS__Business_Hours_Age_4__c
FROM Case
WHERE IsClosed = false AND {OWNER_SCOPE} {CF_SCOPE}
ORDER BY CreatedDate ASC
LIMIT 2000
```

Feed to `scripts/age_decompose.py --mode backlog --followup-field {FOLLOW_UP_ON}`. If the org has
more than 2,000 open cases in scope, run the counts as aggregates instead. SOQL can bucket ages by
`CreatedDate` range literals, one query per bucket edge:

```sql
SELECT COUNT(Id) total, COUNT(FLAGS__ViewedFlag__c) flagged, COUNT({FOLLOW_UP_ON}) follow_up_set
FROM Case
WHERE IsClosed = false AND {OWNER_SCOPE} {CF_SCOPE}
  AND CreatedDate < LAST_N_DAYS:7 AND CreatedDate = LAST_N_DAYS:30   -- the 7–30d bucket
```

`COUNT(field)` counts non-null values, so "forgotten" in that bucket is not
`total − flagged − follow_up_set` (a case can have both). Get it directly by adding
`AND FLAGS__ViewedFlag__c = null AND {FOLLOW_UP_ON} = null` to a `COUNT(Id)`.

## 11.2 Closed cohort — population (lens c)

```sql
SELECT Id, CaseNumber, Subject, CreatedDate, ClosedDate, IsClosed, FLAGS__ViewedFlag__c, Status, Priority, Origin, Type,
       Reason, Account.Name, Owner.Name, FLAGS__Aging_Speed__c,
       FLAGS__Initial_Response_Business_Hours__c,
       FLAGS__Business_Hours_Age_1__c, FLAGS__Business_Hours_Age_2__c,
       FLAGS__Business_Hours_Age_3__c, FLAGS__Business_Hours_Age_4__c,
       FLAGS__Hours_Age_1__c, FLAGS__Hours_Age_2__c, FLAGS__Hours_Age_3__c, FLAGS__Hours_Age_4__c
FROM Case
WHERE IsClosed = true AND ClosedDate = LAST_N_DAYS:{N} AND {OWNER_SCOPE} {CF_SCOPE}
ORDER BY ClosedDate DESC
```

`{N}` must stay inside the history window (`FLAGS__HistoryTrackingMonths__c` from Preflight), or the
older cases will show partial history. The band rollups are what makes the **no-CFHT degraded read**
possible (see the job file): the sum of `Business_Hours_Age_1..4` equals the case's total flag-up
(our-court) BH, and `Business_Hours_Age_4` is the time past SLA. Verified live (2026-11-20): 37 of 37
checked closed cases matched the CFHT flag-up sum to within 0.001 BH. Don't select the calendar
`FLAGS__Hours_Age_*` fields for SLA; they use calendar-hour thresholds.

**Aggregate first, as a rough headline.** For a quick "how much of our cohort's age is ours", one GROUP
BY gets close without raw rows:

```sql
SELECT FLAGS__Flag_Set__c, SUM(FLAGS__Business_Hours_Elapsed__c) bh, SUM(FLAGS__Hours_Elapsed__c) h,
       COUNT_DISTINCT(FLAGS__Case__c) cases
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.IsClosed = true AND FLAGS__Case__r.ClosedDate = LAST_N_DAYS:{N} {CF_SCOPE_CFHT}
GROUP BY FLAGS__Flag_Set__c
```

It groups only by `Flag_Set`, so it is **not** the script's bucket split:
- the flag-down total also contains post-resolution, closed-gap and after-close time;
- the flag-up total also contains flag-up time after the final close.

The customer share it implies is therefore an upper bound. Label it "approximate, before separating
resolved and closed time". Use the 11.3 pull and the script for any figure you present as the customer
share, or whenever reopened or after-close cases are likely.

Add `FLAGS__Case__r.Priority` (or another Case field) to the SELECT and GROUP BY to segment it. This
query is also the lazy CFHT probe when it is the session's first CFHT touch.

## 11.3 Closed cohort — CFHT pull

```sql
SELECT Id, FLAGS__Case__c, FLAGS__Case__r.CaseNumber, FLAGS__Case_Flag_History_Number__c,
       FLAGS__Start__c, FLAGS__End__c,
       FLAGS__Flag_Set__c, FLAGS__Event__c, FLAGS__Action__c, FLAGS__Owner_Name__c,
       FLAGS__Queue_Id__c, FLAGS__Case_Status__c, FLAGS__Flag_Level_BH__c,
       FLAGS__Business_Hours_Elapsed__c, FLAGS__Hours_Elapsed__c,
       FLAGS__Business_Hours_in_Age_4__c, FLAGS__Aging_Speed__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__c IN ({CASE_IDS})
ORDER BY FLAGS__Case__c, FLAGS__Start__c ASC
```

**Do not drop `FLAGS__Business_Hours_Elapsed__c`, `FLAGS__Hours_Elapsed__c` or `FLAGS__End__c`.**
Leaving them out does not error in SOQL; every bucket silently sums to zero (see the silent-zero note
in `references/field-reference.md`). The script refuses to run without them.

Batch `{CASE_IDS}` (about 200 Ids per query keeps the statement short) and expect 2,000-row pages. Get
the row count first with `SELECT COUNT(Id)` on the same WHERE, merge pages with `scripts/cfht_merge.py
--expect-count`, then pass the cached file to `age_decompose.py --cfht … --cases …`.

For a **single case** (lens a, and Job D's vitals), reuse §6's pull in `references/soql-timeline.md`. It
selects everything the script needs, including `FLAGS__Case__c` and `FLAGS__Business_Hours_in_Age_4__c`.

## 11.4 Time-in-status fallback — standard `CaseHistory`

Use this only when CFHT status tracking is off (`FLAGS__Track_Case_Status__c = false`) or CFHT is
unavailable. It needs **Salesforce field history tracking on Case.Status**. If it isn't on, the query
returns no Status rows. Treat that as "not available" and say so; don't ask the user to turn it on.

```sql
SELECT CaseId, Case.CaseNumber, Field, OldValue, NewValue, CreatedDate
FROM CaseHistory
WHERE Field = 'Status' AND CaseId IN ({CASE_IDS})
ORDER BY CaseId, CreatedDate ASC
```

Each row ends the previous status at `CreatedDate`. The first status runs from `Case.CreatedDate`, and
the last runs to `ClosedDate` (or now). This gives **calendar hours only**: standard history has no
business-hours elapsed and no court. Label it that way, and never place it beside the CFHT business-hour
figures as if the two were comparable.
