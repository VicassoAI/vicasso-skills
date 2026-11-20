# SOQL — Follow-up time investment (Jobs C, E)

The raw ordered CFHT pull that opening-trigger classification is reconstructed from, individual and team.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 8. Follow-up time investment (opening-trigger classification pull)

Used by `references/followup-time-investment.md` (Job C add-on, Job E team rollup). Unlike the GROUP BY
approach in §5 (`references/soql-overload.md`) and §7.4
(`references/soql-team-view.md`), this needs the **raw ordered records** so opening-trigger classification can
be reconstructed
in code (a GROUP BY can't express "the action of the record before this run started").

**Pull whole cases, then filter to the owner in code.** Filtering the pull on `FLAGS__Owner__c` drops
the queue's (or another rep's) records from the same case. The record just before the rep's first run is
then missing: the run looks like it started at the case's first record, gets excluded as "flagged at
creation", and `other_clears` is undercounted on every case that arrived from a queue. So select the
cases the owner had a record on, then pull all of those cases' records. This takes two queries: SOQL
rejects a semi-join from CFHT back into CFHT ("inner and outer selects should not be on the same
object type", verified live).

**Step 1: the owner's cases** (Job C: `= '{UID}'`; Job E team rollup: `IN ({REPORT_IDS})`):
```sql
SELECT FLAGS__Case__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Owner__c = '{UID}' AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE_CFHT}
GROUP BY FLAGS__Case__c
```

**Step 2: every record on those cases** (batch `{CASE_IDS}` at ~200 Ids per query):
```sql
SELECT FLAGS__Owner__c, FLAGS__Case__c, FLAGS__Case_Flag_History_Number__c, FLAGS__Start__c,
       FLAGS__End__c, FLAGS__Flag_Set__c, FLAGS__Event__c, FLAGS__Action__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__c IN ({CASE_IDS}) AND FLAGS__Start__c = LAST_N_DAYS:90
ORDER BY FLAGS__Case__c, FLAGS__Start__c ASC
```

In code, reconstruct runs per case on the full record set, then keep only runs whose records belong to
the owner(s) in question. `FLAGS__Case_Flag_History_Number__c` orders records that share a `Start` and
separates "flagged at creation" (history number 001) from runs the 90-day window cut off; see
`scripts/run_stitch.py`.

An active rep can return 1,000+ raw rows over 90 days (verified live: ~1,977 for one rep) — well within
the 50,000-row transaction cap, but don't repeat this pull if the §5 / §7.4 daily-clear-count query
(`references/soql-overload.md`, `references/soql-team-view.md`) already ran this session for the same
person/window; reuse is not possible directly (different shape), but avoid
running both this and a separate ongoing-response-time raw-run pull (`references/field-reference.md` method
(b)) in
the same session — they read the same underlying records for different purposes, so pull once and reuse
the reconstructed runs for both if both are needed.
