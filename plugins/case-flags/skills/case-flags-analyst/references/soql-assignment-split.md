# SOQL — Assignment/response split (Job F)

Case population, the paginated CFHT pull, transition-actor lookup, and the CaseHistory actor cross-check.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 9. Assignment/response split (Job F)

**9.1 Case population** (per rep, per window):
```sql
SELECT Id, FLAGS__Initial_Response_Business_Hours__c
FROM Case
WHERE OwnerId = '{REP_ID}'
  AND FLAGS__Initial_Response__c != null
  AND FLAGS__Initial_Response__c >= {WINDOW_START}
  AND FLAGS__Initial_Response__c <= {WINDOW_END}
  {CF_SCOPE}
```

**9.2 CFHT full pull** — CRITICAL: `FLAGS__Business_Hours_Elapsed__c` is required, not optional (see
references/job-f-assignment-response-split.md "Known pitfalls" for what happens if it's dropped):
```sql
SELECT Id, FLAGS__Case__c, FLAGS__Start__c, FLAGS__End__c, FLAGS__Owner__c,
       FLAGS__Owner_Name__c, FLAGS__Event__c, FLAGS__Business_Hours_Elapsed__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__c IN (
  SELECT Id FROM Case
  WHERE OwnerId = '{REP_ID}'
    AND FLAGS__Initial_Response__c != null
    AND FLAGS__Initial_Response__c >= {WINDOW_START}
    AND FLAGS__Initial_Response__c <= {WINDOW_END}
    {CF_SCOPE}
)
ORDER BY FLAGS__Case__c ASC, FLAGS__Start__c ASC
LIMIT 2000
```
Expect ~200-270 cases per rep to produce ~3,800-4,300 CFHT records — i.e. 2-3 pages. Paginate with
`LIMIT 2000 OFFSET 2000` for the second page; if a third page is needed, run
`ORDER BY FLAGS__Case__c DESC, FLAGS__Start__c DESC LIMIT {remainder}` for the tail and dedupe all
pages by `Id`. Confirm the deduped count against a `COUNT(Id)` on the same WHERE clause before
processing.

**9.3 Transition-actor lookup** — run only after the CFHT walk (job-f step 4) has identified the
specific transition record IDs; don't bulk-fetch `CreatedBy` for the whole CFHT pull:
```sql
SELECT Id, CreatedById, CreatedBy.Name
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE Id IN ({TRANSITION_RECORD_IDS})
```

**9.4 CaseHistory actor cross-check** (optional, for validating actor attribution against the
standard Salesforce audit trail rather than trusting the package's own bookkeeping):
```sql
SELECT CaseId, Field, OldValue, NewValue, CreatedById, CreatedBy.Name, CreatedDate
FROM CaseHistory
WHERE Field = 'Owner'
  AND CreatedDate >= {WINDOW_START}
  AND CreatedDate <= {WINDOW_END}
```
Note: `OldValue`/`NewValue` cannot appear in the WHERE clause (`INVALID_FIELD` error) — filter on
those in code after pulling by `Field` and `CreatedDate` only.
