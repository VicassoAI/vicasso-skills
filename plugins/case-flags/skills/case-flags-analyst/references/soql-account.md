# SOQL — Account responsiveness (Job H)

The two-sided account rollup through `FLAGS__Case__r.AccountId`: headline split, medians, worst severity,
concentration, and the compare-to-normal baseline.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 10. Account responsiveness (Job H) — two-sided, rolled up to Account

CFHT has no Account field; it is master-detail to Case, so the account rollup joins through the parent case
via `FLAGS__Case__r.AccountId`. `{AID}` = the account (or IN-list of parent + children, §10.1); `{CF_SCOPE}`
= `AND FLAGS__Case__r.FLAGS__Enable_Case_Flags__c = true` in selective orgs, empty otherwise. All BH figures
require `FLAGS__Business_Hours_Elapsed__c` in the SELECT (silent-zero — see `references/field-reference.md`).

**10.1 Resolve account (and optional hierarchy):**
```sql
SELECT Id, Name, ParentId FROM Account WHERE Name LIKE '%{TERM}%'
-- if rolling up a parent's children (ask first):
SELECT Id, Name FROM Account WHERE Id = '{AID}' OR ParentId = '{AID}'
```
Use `AccountId IN (...)` / `FLAGS__Case__r.AccountId IN (...)` below when the hierarchy is rolled up.

**10.2 Two-sided split (one account, the headline totals):**
```sql
SELECT FLAGS__Flag_Set__c, COUNT(Id) intervals,
       SUM(FLAGS__Business_Hours_Elapsed__c) total_bh,
       AVG(FLAGS__Business_Hours_Elapsed__c) avg_bh
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}'
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
GROUP BY FLAGS__Flag_Set__c
```
`true` row = our court (how they experienced us); `false` row = their court (how responsive they were).
Means only — medians need raw values (§10.3, §10.6).

**10.3 Ongoing-response median (our court, run-based, method (a) — accurate):** account-scoped versions of
the two `references/field-reference.md` "Ongoing-response" queries:
```sql
-- per-case flag-up BH sum
SELECT FLAGS__Case__c, SUM(FLAGS__Business_Hours_Elapsed__c) up_bh
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}' AND FLAGS__Flag_Set__c = true
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
GROUP BY FLAGS__Case__c
-- per-case genuine-clear count (exclude Case Closed housekeeping)
SELECT FLAGS__Case__c, COUNT(Id) clears
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}' AND FLAGS__Event__c = 'Flag Cleared'
  AND FLAGS__Action__c != 'Case Closed'
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
GROUP BY FLAGS__Case__c
```
per-case mean = up_bh ÷ clears (skip 0-clear cases); the read is the **median of the per-case means**.

**10.4 Initial-response median (Case field, no CFHT — always available):**
```sql
SELECT FLAGS__Initial_Response_Business_Hours__c
FROM Case
WHERE AccountId = '{AID}' AND FLAGS__Initial_Response__c != null
  AND FLAGS__Initial_Response__c = LAST_N_DAYS:90 {CF_SCOPE}
```
Median in code. This is also the CFHT-unavailable degraded read.

**10.5 Worst severity reached (distinct cases at L3/L4).** Verified live: neither `CaseNumber` nor
`FLAGS__Flag_Level_BH__c` can appear in a `GROUP BY` (both error). Filter the level and `COUNT_DISTINCT`
the case, grouped by account — one query per level:
```sql
SELECT FLAGS__Case__r.AccountId aid, COUNT_DISTINCT(FLAGS__Case__c) cases
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}' AND FLAGS__Flag_Level_BH__c = 'L4'
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
GROUP BY FLAGS__Case__r.AccountId
```
Swap `'L4'` for `'L3'` for the red count. Report **both**: L4 is the breach (SLA blown), but on fast-response
accounts L4 is often zero while L3 still flags the cases that ran hot — so "worst severity reached (L3/L4)"
is the honest headline, not an L4-only count that reads as a flat zero for healthy accounts. To list the
actual cases, take the `FLAGS__Case__c` ids from a non-grouped version and resolve `CaseNumber` in a second
`SELECT Id, CaseNumber FROM Case WHERE Id IN (...)` — never group by `CaseNumber`.

**10.6 Worst wait + customer-court turnaround (raw pull, profile mode):** small per-account volume, so pull
raw and compute in code:
```sql
SELECT FLAGS__Case__c, FLAGS__Case__r.CaseNumber, FLAGS__Flag_Set__c,
       FLAGS__Start__c, FLAGS__End__c, FLAGS__Event__c, FLAGS__Action__c,
       FLAGS__Business_Hours_Elapsed__c
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}'
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
ORDER BY FLAGS__Case__c ASC, FLAGS__Start__c ASC
```
`CaseNumber` is fine in this **detail** (non-aggregate) query — the grouping restriction only bites in
aggregate queries. Worst wait = longest contiguous `Flag_Set = true` **run** (stitch runs; a per-interval
MAX understates a split cycle). Customer turnaround = median of `Flag_Set = false` interval BH **excluding**
rows with `FLAGS__Action__c = 'Case Closed'` (the post-resolution dwell); their worst gap = max of that set.

**10.7 Currently in their court (snapshot, no window):** open cases for the account with no flag up now:
```sql
SELECT Id, CaseNumber, Subject, Status
FROM Case
WHERE AccountId = '{AID}' AND IsClosed = false
  AND FLAGS__ViewedFlag__c = null {CF_SCOPE}
```

**10.8 Roster (across accounts — per-interval means, scalable, less precise):**
```sql
SELECT FLAGS__Case__r.AccountId, FLAGS__Flag_Set__c,
       COUNT(Id) intervals, AVG(FLAGS__Business_Hours_Elapsed__c) avg_bh
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Start__c = LAST_N_DAYS:90
  AND FLAGS__Case__r.AccountId != null {CF_SCOPE}
GROUP BY FLAGS__Case__r.AccountId, FLAGS__Flag_Set__c
```
Resolve `AccountId → Name` in a second `SELECT Id, Name FROM Account WHERE Id IN (...)`. Grouping one
relationship hop deep on `FLAGS__Case__r.AccountId` is **verified to work**; the fall back (group by
`FLAGS__Case__c`, roll per-case sums up to Account in code) is only needed if an org rejects it. Rank by the
`true`-row avg for "slowest to," the `false`-row avg for "least responsive." Label these as per-interval
means (Job-G style), not the run-based median profile mode gives.

**10.9 Outlier / concentration (Job H fuller read — per side).** One grouped pull gives per-case total,
interval count, and largest single interval; everything the concentration line and the volume-vs-stall
classification need. Run once with `FLAGS__Flag_Set__c = true` (our court) and once with `= false`
(customer court, add `AND FLAGS__Action__c != 'Case Closed'`):
```sql
SELECT FLAGS__Case__c, SUM(FLAGS__Business_Hours_Elapsed__c) total,
       COUNT(Id) ints, MAX(FLAGS__Business_Hours_Elapsed__c) max_int
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Case__r.AccountId = '{AID}' AND FLAGS__Flag_Set__c = true
  AND FLAGS__Start__c = LAST_N_DAYS:90 {CF_SCOPE}
GROUP BY FLAGS__Case__c
ORDER BY SUM(FLAGS__Business_Hours_Elapsed__c) DESC
```
From the returned rows (one per case), in code:
- **Concentration** = top `total` ÷ account side total, and top-3 ÷ total. Flag per the Tunable constants
  concentration bar. (Account side total is the `Flag_Set` row from §10.2, or the sum of these `total`s.)
- **Classify the worst case(s)** using its `max_int` against the Preflight **ET3 offset**
  (`FLAGS__TimeOffset3__c`): `max_int >=` ET3 → **stall** (one continuous wait aged into red); otherwise,
  high `total` over many `ints` with sub-ET3 `max_int` → **volume/iteration** (complex, many rounds, fast
  per reply). The highest-`total` case and the highest-`max_int` case can differ — surface both when they do
  (concentration leader vs. stall leader). `MAX(FLAGS__Business_Hours_Elapsed__c)` is a per-interval max, a
  lower bound on a true run; for the headline stall call it's sufficient, but stitch runs (§10.6 raw pull)
  if you need the exact longest continuous wait. Resolve `CaseNumber`s via §10.6 or a follow-up `IN (...)`.

**10.10 Compare to normal (opt-in, our-court ONLY).** "Normal" = the org's own baseline over the SAME window,
computed the SAME way, so it's apples-to-apples. Never benchmark the customer-court side. Two org figures:
```sql
-- ongoing_normal numerator + denominator (pooled per-cycle):
SELECT SUM(FLAGS__Business_Hours_Elapsed__c) up_sum, COUNT(Id) up_ints
FROM FLAGS__Case_Flags_History_Tracking__c
WHERE FLAGS__Flag_Set__c = true AND FLAGS__Start__c = LAST_N_DAYS:90
  AND FLAGS__Case__r.AccountId != null {CF_SCOPE}      -- add AND FLAGS__Case__r.AccountId != '{AID}' to exclude the target
-- ...and org genuine clears (same WHERE as §10.3 clears, minus the AccountId filter)
-- initial_normal:
SELECT AVG(FLAGS__Initial_Response_Business_Hours__c) avg_ir, COUNT(Id) n
FROM Case
WHERE FLAGS__Initial_Response__c != null AND CreatedDate = LAST_N_DAYS:90
  AND AccountId != null {CF_SCOPE}
```
`ongoing_normal = up_sum ÷ org_clears`; `initial_normal = avg_ir`. Compare **account mean vs org mean** on
each — the account's ongoing is its own `sum ÷ clears` (§10.3), its initial is `AVG` over its cases — and
express as a delta/ratio ("~29% faster than normal"). Refinements: exclude the target account from its own
baseline (as noted above) so it reads "vs everyone else," and consider excluding any internal/house account
whose runaway volume would distort "normal." Use MEANS here (org-wide medians need full row extraction; means
are cheap and keep both sides consistent) — and remember an account can beat normal on its median case yet
trail on the mean when it has a tail (§10.9), so state which you're showing.
