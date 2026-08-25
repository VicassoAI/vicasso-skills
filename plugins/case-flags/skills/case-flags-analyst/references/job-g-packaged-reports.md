# Job G — Packaged reports (reproduce the shipped Case Flags reports as data)

Case Flags ships a **"Case Flags" report folder** and two **customizable dashboards** (one Standard-Hours,
one Business-Hours, both sourced from the folder's reports). This job surfaces that packaged set on demand:
it (a) says what each packaged report shows, (b) **reproduces the same metric as a plain table via portable
SOQL** so the numbers are available right here — schedulable, summarizable, no navigating to the Reports tab —
and (c) points to the native report/dashboard records for the clickable version.

Use it when someone asks to "run the Case Flags reports," "give me the packaged metrics," "show me average
time to respond by owner," "current red/black flags by owner," "recreate the Case Flags dashboard," or asks
for any of the six named reports below. For analytics that go *beyond* the packaged set (distributions,
bottlenecks, recurrence, handoff churn), that is **Job E** — Job G is the packaged baseline Job E builds on.

## The documented packaged set (portable)

From Vicasso's published "Reports and Dashboards" documentation — this is the set that ships in the managed
package, so it is the same across every install and safe to describe in this shared skill. Each row maps to
a metric the skill already models; reproduce via the referenced pattern rather than inventing a new query.

| Packaged report | Shows | Reproduce with | CFHT? |
|---|---|---|---|
| **Initial Response Averages** | Average initial response, last 90 (Standard + Business Hours), grouped by **month of case creation** — owner is a detail column, not the grouping | **Verified from metadata:** AVERAGE of `FLAGS__Initial_Response_Hours__c` (Std) / `FLAGS__Initial_Response_Business_Hours__c` (BH) on the Case, filtered `FLAGS__Initial_Response__c != null`, grouped by case created-date bucketed monthly — see "Initial Response Averages" below | No |
| **Average Time to Respond by Owner, Last 90** | Per-owner average time to respond, last 90 (Std + BH) | **Verified from metadata:** flat AVERAGE of `FLAGS__Hours_Elapsed__c` (Std) / `FLAGS__Business_Hours_Elapsed__c` (BH) across individual flag-up CFHT interval records, grouped by `FLAGS__Owner__c`. NOT the run-based method — see "What the report actually computes" below | Yes |
| **Average Time to Respond in Queue, Last 90** | Average time flagged cases sat in a queue, last 90 (Std + BH), grouped by queue | **Verified from metadata:** flat AVERAGE of `FLAGS__Hours_Elapsed__c` / `FLAGS__Business_Hours_Elapsed__c` across flag-up CFHT intervals where `FLAGS__Queue_Id__c` is populated, grouped by `FLAGS__Owner_Name__c` (which is the *queue* name during a queue-held interval). Note: NO Standard/active-owner filters — see "Queue report" below | Yes |
| **Response Time - Support vs Customer** | Per-owner support-court response time vs. customer-court response time | **Verified from metadata:** per-interval AVERAGE of `FLAGS__Hours_Elapsed__c` / `FLAGS__Business_Hours_Elapsed__c`, grouped by `FLAGS__Owner_Name__c` **then** `FLAGS__Flag_Set__c` — **no report filters, no date window, units in DAYS** — see "Support vs Customer" below | Yes |
| **Current L3-L4 Flags by Owner** | Count of currently red (L3) / black (L4) flagged cases per owner — **Standard Hours** | **Verified:** `CaseList` report, count of cases grouped by Case Owner, filtered `Owner != '' AND FLAGS__CaseFlag__c` contains "L3,L4" (i.e. the Std flag markup shows L3 or L4), no date filter — see "Current L3–L4" below | No |
| **Current L3-L4 Flags by Owner (BH)** | Same, **Business Hours** | Same, but matches the BH flag field `FLAGS__Case_Flag_Business__c` contains "L3,L4" — see "Current L3–L4" below | No |

**Availability split:** the three *current-flag* and *initial-response* reports run off Case fields alone
(no history data), so they work in any org with Case Flags installed. The three *elapsed-time* reports
(ongoing response, queue dwell, support-vs-customer) read the Case Flags History Tracking object (CFHT) —
probe lazily per SKILL.md and degrade with the job's usual CFHT-unavailable message if it errors.

## What the report actually computes (verified from report metadata)

The `Average Time to Respond by Owner Last 90` definition was read directly from its Reports API
`describe`. Ground truth, not inference:

- **Report type:** "Cases with Case Flags History Tracking" (`CaseCustomEntity$FLAGS__Case_Flags_History_Tracking__c`) — Case primary, CFHT detail.
- **Metric:** a flat **AVERAGE** of `FLAGS__Hours_Elapsed__c` (Standard) and `FLAGS__Business_Hours_Elapsed__c` (BH), computed **per CFHT interval record** — not per run and not per case.
- **Grouping:** `FLAGS__Owner__c` (the interval owner), ascending.
- **Window:** last 90 days on the **CFHT record's Created Date** (`CUST_CREATED_DATE`) — not `Case.CreatedDate` and not `FLAGS__Start__c`.
- **Scope:** `organization` (all cases), then narrowed by the owner filters below.

**Packaged filters (apply these to reproduce faithfully):**
```
FLAGS__Flag_Set__c = true            -- our-court (flag up) intervals only
FLAGS__Owner__c != ''                -- person-owned only (excludes queue-held intervals)
FLAGS__Owner_License_Type__c = 'Standard'   -- LICENSED users only (full-license internal users)
FLAGS__Owner_Is_Active__c = true     -- currently-active owners only
```
The `Standard` license filter is the answer to "does it limit to licensed users" — for *this* report, yes.
But **the filter set is not uniform across the packaged reports** — verified, not assumed: the Time to
Respond in Queue report (below) carries only `Flag_Set = true` + `Queue_Id != ''`, with NO Standard-license
or active-owner filter. So do not generalize one report's filters to another; read each report's `describe`
and reproduce its own filter set. Response Time - Support vs Customer and Initial Response Averages have
now also been read from metadata (sections below), and both diverged from the earlier assumption — Initial
Response groups by month of creation rather than by owner, and Support vs Customer carries no filters, no
date window, and reports in days — which is exactly why each report's own `describe` is the authority.

## Faithful reproduction vs. the skill's more accurate method — be honest about the gap

Two distinct numbers, and the difference is real:

- **The packaged report** is a per-interval mean (above). It does not stitch a case's flag-up intervals into
  one response cycle, so a cycle split across several CFHT records (by a status or owner change mid-cycle)
  contributes several small interval averages, not one cycle time. `references/field-reference.md`
  ("Ongoing-response
  time — compute per RUN, not per record") explains why this understates true per-response time. The package
  accepts that simplification.
- **The skill's run-based ongoing-response** (field-reference method a/b) stitches contiguous flag-up runs
  and is the more accurate response-time figure — but it is **not** what the native report shows.

So: when the ask is "run the packaged report," reproduce the **per-interval average with the four filters
above** so it reconciles with the native report/dashboard. Offer the run-based figure (and a median instead
of a mean) as the more robust companion, clearly labeled as such — never silently swap either in and call it
"the packaged report." The packaged report is fully introspectable via its `describe`, so aim to reconcile
closely; where a reproduced number still drifts, name the reason (window edge on Created-vs-Start, rounding)
rather than hand-waving.

## Queue report (Average Time to Respond in Queue) — verified from metadata

Despite the "before a person picked it up" framing in the doc, the report does **not** model a per-case
pickup time or attribute anything to the eventual human owner. Verified definition:

- Same report type and per-interval AVERAGE of `FLAGS__Hours_Elapsed__c` / `FLAGS__Business_Hours_Elapsed__c`
  as the by-owner report.
- **Filters:** only `FLAGS__Flag_Set__c = true` and `FLAGS__Queue_Id__c != ''` (a queue held the case during
  the interval). No Standard-license filter, no active-owner filter, no owner-not-blank filter.
- **Grouping:** `FLAGS__Owner_Name__c` — and during a queue-held interval that value is the **queue's** name
  (see `references/field-reference.md`: Owner/Owner_Name is the queue when queue-owned). So the report is really
  "average flagged-interval time per queue," not per person.
- Window on CFHT Created Date, `LAST_N_DAYS:90`; scope `organization`; units hours.

To reproduce: average elapsed hours over CFHT rows where `FLAGS__Flag_Set__c = true AND FLAGS__Queue_Id__c !=
null`, from `CFHT.CreatedDate = LAST_N_DAYS:90`, grouped by `FLAGS__Owner_Name__c`. This is *not* the same as
Job F's assignment time (which attributes creation→pickup time to the responding person); don't conflate
them or reuse Job F's per-person walk here. Silent-zero caution from `references/field-reference.md` still
applies —
omitting `Business_Hours_Elapsed__c` from the pull yields a spurious all-zero BH column.

## Current L3–L4 by Owner (Standard and Business Hours) — verified from metadata

A count of currently red/black flagged cases per owner. Both variants are `CaseList` (plain Case) reports —
no CFHT, no date filter (current state):

- **Metric:** record count of Cases, grouped by Case Owner (`Owner.Name`).
- **Filters:** `Owner != ''` (person-owned) AND the flag field **contains** "L3,L4". The report uses a
  text-contains match on the rendered flag HTML — the Standard variant on `FLAGS__CaseFlag__c`, the BH
  variant on `FLAGS__Case_Flag_Business__c`. Salesforce "contains L3,L4" is an OR, so it catches cases whose
  flag markup shows either L3 or L4. Scope `organization`; no date bound.
- **SOQL reproduction:** `SELECT Owner.Name, COUNT(Id) FROM Case WHERE OwnerId != null AND (FLAGS__CaseFlag__c LIKE '%L3%' OR FLAGS__CaseFlag__c LIKE '%L4%') GROUP BY Owner.Name` (Std); swap in `FLAGS__Case_Flag_Business__c` for BH. This is the one place the skill's "always use the BH flag" rule is deliberately set aside — the two report variants read two different fields, so say which one you're showing.
- **Note vs the skill's level model:** SKILL.md computes level from how many of ET1..ET4 are at/before now.
  That should broadly agree with the flag-markup match, but it is *not* what the packaged report does — to
  reconcile with the native report, use the contains-match above; offer the ET-based reading only as a
  cross-check, labeled as such.

## Initial Response Averages — verified from metadata

A `CaseList` report (Case primary, **no CFHT**), so it runs in any org with Case Flags installed:

- **Metric:** AVERAGE of `FLAGS__Initial_Response_Hours__c` (Standard) and `FLAGS__Initial_Response_Business_Hours__c`
  (BH) — both fields live on the Case. `RowCount` is also carried.
- **Grouping:** `CREATED_DATE` with **monthly** granularity. This is the key correction from an earlier
  assumption: the shipped report is an **org-wide monthly trend of initial-response time**, *not* a per-owner
  leaderboard. Case Owner is present only as a **detail column** (alongside `FLAGS__Initial_Response__c` and the
  two hours fields), so per-owner numbers are visible when you drill into detail rows but are not the summary.
- **Filter:** `FLAGS__Initial_Response__c != null` (only cases that actually received an initial response — this
  keeps unanswered cases from dragging the average toward zero).
- **Window:** `CREATED_DATEONLY = LAST_N_DAYS:90` (the **Case's** created date, not CFHT). Scope `organization`; units hours.

**Reproduce faithfully** (monthly trend) by averaging the two Case fields over cases where
`FLAGS__Initial_Response__c != null AND CreatedDate = LAST_N_DAYS:90`, grouped by `CALENDAR_MONTH(CreatedDate)`.
If the person actually wants the **per-owner** cut (a common and reasonable ask), that's a legitimate variation
— group by `Owner.Name` instead — but say clearly that you've switched the grouping dimension, because it no
longer matches the native report's monthly view. The choice of grouping dimension is a report-builder setting
that orgs frequently change, so when matching a specific org's folder, read the live `describe` rather than
assuming month vs. owner.

## Support vs Customer (Response Time) — verified from metadata

A `Cases with Case Flags History Tracking` report (CFHT — probe lazily and degrade if unavailable):

- **Metric:** per-interval AVERAGE of `FLAGS__Hours_Elapsed__c` and `FLAGS__Business_Hours_Elapsed__c`, plus `RowCount`.
- **Grouping — two levels:** `FLAGS__Owner_Name__c` (ascending) **then** `FLAGS__Flag_Set__c` (descending).
  Within each owner, `Flag_Set = true` (flag up = the ball is in *our* court, i.e. support-court time) sorts before
  `Flag_Set = false` (customer-court time). So the report reads as, per owner: average time on our side vs. average
  time on the customer's side. As with the queue and by-owner reports, `Owner_Name` is the **queue's** name during a
  queue-held interval (see `references/field-reference.md`), so queue rows can appear alongside people.
- **Filters:** **none.** No `Flag_Set` filter (both courts are wanted — it's a grouping, not a filter), no
  owner/license/active filters.
- **Window:** **none** — the shipped report has no date bound (all-time). If you want to bound it (e.g. to reconcile
  with a 90-day dashboard tile or to respect the post-install cutoff below), say so explicitly rather than
  presenting an all-time number as if it were windowed.
- **Units: DAYS**, not hours — this is the only report in the set measured in days. When you reproduce it, either
  convert the elapsed-hours fields to days or label the unit, and heed the silent-zero caution from
  `references/field-reference.md`: always pull `FLAGS__Business_Hours_Elapsed__c` explicitly so the BH column
  isn't a spurious zero.

**Reproduce faithfully** by averaging both elapsed fields over all flag-up *and* flag-down CFHT intervals (no date
filter), grouped by `FLAGS__Owner_Name__c, FLAGS__Flag_Set__c`, presenting hours-elapsed as days. This is a
company-vs-customer split per owner; it is not the same as the run-based ongoing-response method (that stitches
contiguous flag-up runs into response cycles) — offer the run-based figure only as a clearly-labeled companion.

## Present it like the packaged output

- Plain, scannable, sectioned tables — one section per requested report, owners as rows. No widget (per
  SKILL.md output style).
- Only run the reports the person asked for; if they say "all the Case Flags reports" or "the dashboard,"
  run the full set and group the tables the way the two dashboards do (Standard set / Business-Hours set).
- **Post-installation cutoff (Vicasso best practice, from the packaged doc):** metrics from cases created
  *before* Case Flags was installed are unreliable even if Case Flags later touched them. Offer to bound the
  reproduced queries to cases created post-install (ask for or detect the install date) and note when a
  number may include pre-install cases. This is a general Vicasso recommendation, not org-specific.
- Close by pointing to the native artifacts: the **"Case Flags" report folder** and the two dashboards on the
  Reports tab, which can be scheduled to email periodically for an ongoing snapshot.

## Reconcile against the org's live folder — don't hardcode it

The **documented** set above is the portable backbone. Any given org's actual "Case Flags" folder often
diverges — reports get cloned, renamed, added, or removed over the years. When it's useful (e.g. the person
asks "what Case Flags reports do we have" or wants the reproduced set to match their real folder), look the
folder up live rather than assuming:

```sql
SELECT Id, Name, DeveloperName, FolderName FROM Report WHERE FolderName = 'Case Flags' ORDER BY Name
```

Reconcile what's present against the documented set, call out additions/renames/absences, and reproduce
whatever the person actually wants. **Do not bake a specific org's report names or Ids into this skill** —
they are org-specific. If an org wants its particular inventory (custom reports, folder Id, install date)
remembered, that belongs in memory, not here.

## When CFHT is unavailable

Same as Job E: say so briefly and constructively, run the two Case-field-only reports (Initial Response
Averages, Current L3–L4 by Owner) which don't need history, and note that the three elapsed-time reports
need the Case Flags History Tracking object — ask the Salesforce admin to enable history tracking and grant
access.
