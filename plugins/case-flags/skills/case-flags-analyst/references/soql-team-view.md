# SOQL — Manager / team view (Job B)

Every roster input run once across all direct reports and grouped per owner in code — never looped per person.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 7. Manager / team view (role-aware) — team-wide, not per person

Direct reports:
```sql
SELECT Id, Name FROM User WHERE ManagerId = '{UID}' AND IsActive = true
```

Then run each input ONCE across all reports and group per owner in code (do not loop per report):

### 7.1 Flagged roster inputs (Ring-1 shape, all reports)
```sql
SELECT Id, CaseNumber, Subject, Status, OwnerId, Owner.Name, Account.Name,
       FLAGS__Aging_Speed__c, FLAGS__Initial_Response__c,
       FLAGS__CaseFlagsEscalationTime4__c
FROM Case
WHERE FLAGS__ViewedFlag__c != null
  AND OwnerId IN ({REPORT_IDS})
  {CF_SCOPE}
ORDER BY OwnerId, FLAGS__CaseFlagsEscalationTime4__c ASC
```

### 7.2 Follow-ups due today (all reports)
```sql
SELECT Id, OwnerId FROM Case
WHERE OwnerId IN ({REPORT_IDS})
  AND FLAGS__ViewedFlag__c = null
  AND {FOLLOW_UP_ON} >= TODAY AND {FOLLOW_UP_ON} < TOMORROW
  {CF_SCOPE}
```

### 7.3 Initial medians (all reports)
```sql
SELECT OwnerId, FLAGS__Initial_Response_Business_Hours__c
FROM Case
WHERE OwnerId IN ({REPORT_IDS})
  AND FLAGS__Initial_Response__c != null
  AND FLAGS__Initial_Response__c = LAST_N_DAYS:90
```
Compute each owner's median in code.

### 7.4 labor_per_clear (all reports; CFHT — the lazy probe for this job)
Same daily-clear-count method as §5 (`references/soql-overload.md`), grouped by owner and day:
```sql
SELECT FLAGS__Owner__c, DAY_ONLY(FLAGS__Start__c) clear_day, COUNT(Id) clears
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c IN ({REPORT_IDS})
  AND FLAGS__Event__c = 'Flag Cleared' AND FLAGS__Action__c != 'Case Closed'
  AND FLAGS__Start__c = LAST_N_DAYS:90
GROUP BY FLAGS__Owner__c, DAY_ONLY(FLAGS__Start__c)
```
Per owner: `avg_daily_clear_count` = median of that owner's per-day clear counts (days with zero clears
won't appear, which is the intended exclusion); `labor_per_clear = 8h ÷ avg_daily_clear_count`. Flag any
owner with fewer than ~10 distinct workdays in the result as low-confidence. On an access error, fall back
to §7.3 medians in place of `labor_per_clear` and label the roster's load estimates accordingly.

Roll up: per person → flag count, # overdue (ET4 in the past), # follow-ups due today, estimated load
hours, and band (constants in SKILL.md). Highlight who is overloaded and who is light.

### 7.5 Intraday forecast inputs (all reports — team-wide equivalent of §5 in `references/soql-overload.md`)

Same two signals as the individual forecast (§5 "Intraday forecast inputs", `references/soql-overload.md`),
bulked across the team in
one call each rather than looping per report:

**Net-new arrivals (Case object only):**
```sql
SELECT OwnerId, CreatedDate
FROM Case
WHERE OwnerId IN ({REPORT_IDS})
  AND CreatedDate = LAST_N_DAYS:90
  {CF_SCOPE}
```

**Re-flag arrivals (CFHT):**
```sql
SELECT FLAGS__Owner__c, FLAGS__Case__c, FLAGS__Start__c, FLAGS__End__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c IN ({REPORT_IDS})
  AND FLAGS__Event__c = 'Flag Set'
  AND FLAGS__Flag_Set__c = false
  AND FLAGS__Start__c = LAST_N_DAYS:90
ORDER BY FLAGS__Owner__c, FLAGS__End__c ASC
```
Pulling `FLAGS__Start__c` alongside `FLAGS__End__c` here means this same result also answers the
same-day re-flag rate per owner (§7.6) — no separate query needed.

In code: group both by `OwnerId`/`FLAGS__Owner__c`, then apply the same per-weekday, post-cutoff logic as
§5 (`references/soql-overload.md`), per owner, weighting the combined arrival count by that owner's own
`labor_per_clear` from §7.4.
`totalForecastHours[owner] = snapshotLoadHours[owner] + expectedIntradayLoadHours[owner]`.

### 7.6 With-Customer soft warning (all reports)

```sql
SELECT OwnerId, Id, Status
FROM Case
WHERE OwnerId IN ({REPORT_IDS})
  AND FLAGS__ViewedFlag__c = null
  AND IsClosed = false
  AND FLAGS__Initial_Response__c != null
  {CF_SCOPE}
```
Same detection-over-assumption rule as §5 (`references/soql-overload.md`): narrow to a literal "with
customer"-reading status if one is
present in the returned values, otherwise use the full result. Combine with each owner's same-day re-flag
rate (from the §7.5 re-flag pull) to get an expected same-day bounce-back count per owner. This is
informational per person, not added to `totalForecastHours` — same anti-double-count rule as the
individual view.
