# SOQL — Timeline interpretation and recurrence (Jobs D, E)

The single-case CFHT pull with compression and tagging, plus recurrence at single-case and portfolio level.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 6. Timeline Interpretation (job D) — single case

Pull the full CFHT history for one case, in order, with everything needed for compression and tagging.
This query is the lazy probe when D is the session's first CFHT touch:

```sql
SELECT Id, CreatedDate, FLAGS__Case_Flag_History_Number__c, FLAGS__Start__c, FLAGS__End__c,
       FLAGS__Flag_Set__c, FLAGS__Flag_Level_BH__c, FLAGS__Event__c, FLAGS__Action__c, FLAGS__Reason__c,
       FLAGS__Owner__c, FLAGS__Owner_Name__c, FLAGS__Queue_Id__c, FLAGS__Case_Status__c,
       FLAGS__Aging_Speed__c, FLAGS__Business_Hours_Elapsed__c, FLAGS__Hours_Elapsed__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__c = '{CASE_ID}'
ORDER BY FLAGS__Start__c ASC
```

Also pull the Case's own aging thresholds (for the "long gap" comparison in tag C):
```sql
SELECT FLAGS__CaseTimeOffset1__c, FLAGS__CaseTimeOffset2__c, FLAGS__CaseTimeOffset3__c,
       FLAGS__CaseTimeOffset4__c, FLAGS__Aging_Speed__c, FLAGS__Initial_Response_Business_Hours__c,
       CreatedDate, ClosedDate, Status
FROM Case WHERE Id = '{CASE_ID}'
```

**Detecting custom-tracked fields (F):** compare the non-null fields on the returned CFHT rows against the
known set in `references/field-reference.md`. Any additional populated field is a customer-specific tracked
field —
surface it, don't guess its meaning.

### Compression + tagging (apply in code, not SOQL)

1. Sort by `FLAGS__Start__c`. Walk the list; group consecutive records whose `CreatedDate` is within ~2
   seconds of each other into one compressed action. Prefer the most "human" `Action` in the group
   (Email Sent/Received, a button click, a comment) as the action's label over `Local Automation`.
2. Tag each compressed action per the taxonomy in `references/job-d-timeline-interpretation.md` (A–G).
3. Compute vitals (job D Step 3) from the full (uncompressed) interval set — compression is a
   display concern, not a calculation concern; sums should use every raw interval.
4. Render: vitals block, then the narrative — include only the compressed actions relevant to the inferred
   lens (Personalize = recent + open commitments; Coach = all; Audit = all tagged A–F; Prep = only C/D
   plus a customer-side-delay summary).

### Recurrence — single case (tag G)

Semantics canonical in `references/field-reference.md` ("Recurrence" / "Close events come in two shapes").
From the
same pulled record set (no extra query needed): count close events — `Action = 'Case Closed'`, whether
`Event` is `'Flag Cleared'` (closed while flagged) or `'Case Status Changed'` (closed while unflagged);
more than one = recurred. For each reopening beyond the first, read the `Flag Set` record immediately
following the close (by `Start__c`) and classify its `Action__c` per the field-reference trigger rules.

### Recurrence rate (job E — portfolio level)

```sql
SELECT FLAGS__Case__c, FLAGS__Owner__c, FLAGS__Owner_Name__c, FLAGS__Event__c, FLAGS__Action__c, FLAGS__Start__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Action__c = 'Case Closed'
  AND FLAGS__Start__c = LAST_N_DAYS:90
ORDER BY FLAGS__Case__c, FLAGS__Start__c ASC
```
(Do not filter on `Event` — closes appear under both `'Flag Cleared'` and `'Case Status Changed'`;
filtering to one shape silently drops a large share of closes.) Group by `FLAGS__Case__c`; any case with
2+ rows recurred at least once. Recurrence rate = (cases with 2+ rows) ÷ (distinct cases in the result).
For the trigger breakdown, pull the first `Flag Set` record following each non-final close (same approach
as the single-case pattern) and tally by `Action__c`. Slice by
`FLAGS__Owner_Name__c` for a per-rep view, or roll up org-wide for a baseline.
