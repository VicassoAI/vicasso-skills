# Case Flags Field Reference (portable / managed-package only)

Everything here is namespaced and identical across every Case Flags install, EXCEPT the
follow-up fields, which are org-specific and must be read from settings (see Preflight).

Two namespaces:
- `FLAGS__` — core Case Flags (always present if Case Flags is installed)
- `FLAGS_METRICS__` — Metrics Extension, a SEPARATE package that may NOT be installed

Never assume any un-namespaced custom field exists; those are customer-specific.

---

## Settings — `FLAGS__FlagPref__c` (hierarchy custom setting; read the org-default row)

The master configuration. Read this FIRST (see SKILL.md Preflight). Org-default row:
`WHERE SetupOwnerId IN (SELECT Id FROM Organization)`.

| Field | Meaning / use |
|---|---|
| `FLAGS__Organization_Wide__c` | true = all cases processed; false = SELECTIVE → scope every case query to `FLAGS__Enable_Case_Flags__c = true` |
| `FLAGS__Enable_History__c` | Is Case Flags History Tracking (CFHT) on at all |
| `FLAGS__Track_Flag_Set__c` / `FLAGS__Track_Flag_Clear__c` | Whether flag set / clear events are recorded in CFHT |
| `FLAGS__Track_Case_Ownership__c` | Whether ownership-change events are recorded in CFHT |
| `FLAGS__Track_Case_Status__c` | Whether status-change events are recorded in CFHT |
| `FLAGS__HistoryTrackingMonths__c` | CFHT auto-purge window (months). Bounds how far back CFHT analysis can go |
| `FLAGS__Enable_Follow_Up_Process__c` | Is the Follow-Up Process enabled |
| `FLAGS__Follow_Up_On_Field__c` | **API name** of the Case "Follow-Up On" Date/Time field (ORG-SPECIFIC — do not guess) |
| `FLAGS__Next_Steps_Field__c` | **API name** of the Case "Next Steps" text field (ORG-SPECIFIC — do not guess) |
| `FLAGS__BusinessHoursId__c` | Global Business Hours set; null → standard hours (or per aging speed) |
| `FLAGS__TimeOffset1__c` … `FLAGS__TimeOffset4__c` | DEFAULT aging-speed band thresholds in hours (Offset1 usually 0) |

## Custom Aging Speeds — `FLAGS__Aging__c` (list custom setting)

One row per named aging speed. The DEFAULT speed lives in FlagPref (above); named speeds live here.
Fields: `Name`, `FLAGS__Active__c`, `FLAGS__Order__c` (evaluation precedence),
`FLAGS__Logic__c` (matching criteria), `FLAGS__Age1Hours__c`…`FLAGS__Age4Hours__c` (this speed's
thresholds), `FLAGS__BusinessHoursId__c` (this speed's business hours), `FLAGS__Follow_Up_Process_Id__c`.

The speed that governed a given case is stamped on `Case.FLAGS__Aging_Speed__c`. Because each speed has
its own thresholds and business hours, NEVER compare raw flag age / business-hours across cases on
different aging speeds as if equivalent.

---

## Case fields (core `FLAGS__`)

| Field | Meaning |
|---|---|
| `FLAGS__ViewedFlag__c` | Case Flag Date/Time. **Not null = currently flagged; null = cleared.** The canonical, color-independent "is it flagged" test. Set to NOW when raised, null when cleared |
| `FLAGS__Case_Flag_Business__c` | The flag icon to display. **Always use this one field** — if the org uses business hours it is correct; if not, it duplicates `FLAGS__CaseFlag__c`. (So you never branch on BH config for the flag.) |
| `FLAGS__CaseFlag__c` | Flag icon (non-business-hours). Do not use directly; prefer `Case_Flag_Business__c` |
| `FLAGS__CaseFlagsEscalationTime1__c` … `4__c` | The countdown. On flag set, all four populate: ET1 = the moment flagged; ET2/3/4 from the aging speed. **ET4 = SLA breach ("red buzzer").** All four are null when the flag is cleared. ET4 is always populated on a flagged case (built-in four levels), even if a speed collapses early levels to 0h |
| `FLAGS__CaseTimeOffset1__c` … `4__c` | The aging-speed hours applied to THIS case (Offset1 usually 0) |
| `FLAGS__Aging_Speed__c` | Name of the aging speed in effect (stamped at history-record creation) |
| `FLAGS__Initial_Response__c` | Timestamp set the FIRST time the flag clears = initial response. Null = no initial response yet |
| `FLAGS__Initial_Response_Hours__c` | Hours from opened → initial response |
| `FLAGS__Initial_Response_Business_Hours__c` | Business hours from opened → initial response. **Source for the initial-response median** |
| `FLAGS__Case_Flag_Age__c` / `FLAGS__Case_Flag_Business_Age__c` | Hours / business-hours the current flag has been active |
| `FLAGS__Hours_Age_1__c`…`4__c`, `FLAGS__Business_Hours_Age_1__c`…`4__c` | Rollups of time spent in each band (from CFHT) |
| `FLAGS__Enable_Case_Flags__c` | In a selective-processing org, true = this case is managed by Case Flags |
| `FLAGS__CaseFlagsBusinessHours__c` | Lookup → `FLAGS__CaseFlagsBusinessHours__c` wrapper |

Standard Case fields used: `CaseNumber`, `Subject`, `Status`, `Priority`, `OwnerId`
(referenceTo Group OR User — an Id beginning `00G` is a queue), `Account.Name`, `Contact.Name`,
`IsClosed`, `ClosedDate`, `CreatedDate`, `LastModifiedDate`.

Follow-up fields are referenced by the API names found in FlagPref
(`FLAGS__Follow_Up_On_Field__c`, `FLAGS__Next_Steps_Field__c`) — never hardcoded.

## Business Hours wrapper — `FLAGS__CaseFlagsBusinessHours__c`

Thin wrapper around the standard `BusinessHours` object:
`FLAGS__BusinessHours__c` (lookup → standard BusinessHours), `FLAGS__TodayStartTime__c`,
`FLAGS__TodayEndTime__c`. A case's applicable hours:
`Case.FLAGS__CaseFlagsBusinessHours__r.FLAGS__BusinessHours__r.Name`.

---

## Case Flags History Tracking (CFHT) — `FLAGS__Case_Flags_History_Tracking__c`

**Access note:** This object requires explicit object permissions (it is master-detail with a standard
object), so a given connection/user may not be able to query it even when cases are visible. Always
detect availability first (see SKILL.md "CFHT availability") and degrade gracefully.

An interval log: each record describes the case's flag state over a `FLAGS__Start__c` → `FLAGS__End__c`
window. Read in `Start` order, the records reconstruct the responsiveness timeline.

| Field | Meaning |
|---|---|
| `FLAGS__Start__c` / `FLAGS__End__c` | Interval bounds |
| `FLAGS__Flag_Set__c` | Was the flag UP during this interval. **true = the org's court (customer waiting on us); false = the customer's court (we're waiting on them).** |
| `FLAGS__Flag_Level__c` / `FLAGS__Flag_Level_BH__c` | Flag level as text **L0–L4** ("useful for analytics"). Prefer the `_BH` variant (it equals the non-BH one when the org isn't using business hours). Lets you read the level directly instead of computing it from escalation times |
| `FLAGS__Event__c` | Flag Set, Flag Cleared, Case Owner Changed, Case Status Changed. Describes the transition that ENDED this interval |
| `FLAGS__Action__c` | What initiated it. Validated picklist + observed values: Local Automation, Case Created, Case Closed, Set Flag Button, Clear Flag Button, External/Internal Comment Added, Email Received, Email Sent, Customer Attachment Added, Task Completed, **Follow-Up Process**, **User Action or Non-Flags Automation**. (There is no "Automatically Cleared" value.) |
| `FLAGS__Reason__c` | Free-text reason the flag was set or cleared (when populated) |
| `FLAGS__Owner__c` / `FLAGS__Owner_Name__c` | Case owner during the interval (a queue if queue-owned) |
| `FLAGS__Owner_Is_Active__c` | Whether that owner is still an active user (useful when summarizing past work) |
| `FLAGS__Owner_License_Type__c` | The interval owner's Salesforce license type (e.g. `Standard`). Packaged and portable. *Some* packaged reports (e.g. Average Time to Respond by Owner) filter to `= 'Standard'` to limit to full-license internal users; others (e.g. Average Time to Respond in Queue) do not — see Job G |
| `FLAGS__Queue_Id__c` | Queue Id if queue-owned during the interval |
| `FLAGS__Case_Status__c` | Case status during the interval |
| `FLAGS__Aging_Speed__c` | Aging speed in effect when the record was created |
| `FLAGS__Case__c` | Parent Case |
| `FLAGS__Business_Hours_Elapsed__c` | Business hours of THIS interval (Start→End) |
| `FLAGS__Hours_Elapsed__c` | Calendar-hours equivalent |
| `FLAGS__Business_Hours_in_Age_1__c`…`4__c`, `FLAGS__Hours_in_Age_1__c`…`4__c` | Time spent in each band during the interval |
| `FLAGS__Case_Flag_History_Number__c` | Per-case sequence string (e.g. "001"). Note: singular "Flag". The standard `Name` field holds the same value |

Ignore genuinely un-namespaced CFHT fields (e.g. `EventAction__c`, `Owners_Department__c`) — those are
customer-specific additions, not portable. Do NOT confuse these with the namespaced
`FLAGS__Owner_License_Type__c`, which looks similar but is a packaged, portable field the packaged
reports actually depend on (above).

**`FLAGS__Business_Hours_Elapsed__c` and `FLAGS__End__c` are easy to leave out of a SELECT list**
since Start/Owner/Event alone look sufficient for sequencing runs and reconstructing ownership
history — but any job computing durations (not just ordering), such as Job F's assignment/response
split, must include them explicitly. Omitting `Business_Hours_Elapsed__c` doesn't error; every
per-case sum silently defaults to 0, which reads as a real (and wrong) finding — e.g. "assignment
time is always zero" — rather than a missing column. This happened once during Job F's development;
treat a uniform, no-variance result across an entire population as a signal to check the field list
before trusting it.

**Close events come in two shapes (verified live).** The record that ends at a case close always has
`FLAGS__Action__c = 'Case Closed'`, but its `Event` depends on the flag state at close time:
`Event = 'Flag Cleared'` if the case closed while flagged (the housekeeping clear), or
`Event = 'Case Status Changed'` if the case closed while the flag was already down. In one real org over
90 days the split was roughly 64% / 36% — filtering on `Event = 'Flag Cleared'` alone misses a third of
closes. **The close-event test is `Action = 'Case Closed'`, regardless of Event.**

**Data hygiene for responsiveness:** the housekeeping clear is the `Event = 'Flag Cleared'` +
`Action = 'Case Closed'` shape (a flag cleared because the case closed, not a human reply) — exclude
those from response-time analysis. Also be aware that excluded/integration users may appear as the actor.

**Recurrence (reopening after close):** a case can carry more than one close event
(`Action = 'Case Closed'`, either Event shape above) if it was closed, reopened, and closed again. This
is a direct, unambiguous signal readable from CFHT alone — count close events per case; more than one
means it recurred. Classify each reopening's trigger from the `Flag Set` record that follows a close: `Email
Received` or comment activity means the customer engaged (an activity signal, not a resolution verdict);
`Follow-Up Process` means the customer did not act and our own scheduled check-in pulled it back open.
Never infer whether the underlying issue was actually resolved — CFHT cannot distinguish "customer
satisfied" from "customer gave up" when there's no further activity, so keep any read on this neutral.

**Opening-trigger classification, generalized to every flag-up cycle (not just reopens):** the same
"read the `Flag Set` record that starts the run" technique used above for recurrence applies to *any*
contiguous `Flag_Set = true` run, not only ones following a close. `references/followup-time-investment.md` uses
this to split all genuine clears into follow-up-triggered vs. other. One caveat that doesn't apply to the
recurrence case: a run with no preceding record at all (the case was flagged at creation) has no opening
trigger to read — exclude those runs from this classification rather than guessing. Also note: the run's
BH-elapsed does **not** reliably differ between follow-up-triggered and other-triggered genuine clears
(tested live — medians 23 vs 15 min, means ~41 vs ~41 min) — it measures queue/wait time, not rep labor,
so don't use it as a proxy for effort here; see `references/followup-time-investment.md` for how labor time is
handled instead (declared, not derived).

**Intraday re-flag arrival signal:** a CFHT record with `FLAGS__Event__c = 'Flag Set'` AND
`FLAGS__Flag_Set__c = false` is a down-interval (customer's court) that ended because the flag went back
up — i.e. the customer replied, or a follow-up pulled the case back. Its `FLAGS__End__c` is the arrival
timestamp. This is the basis for job C's intraday re-flag forecast (`references/soql-overload.md` §5, "Intraday
forecast inputs").

**This signal does NOT cover net-new cases.** A case flagged immediately at creation has no preceding
down-interval to end — its first CFHT record already starts `Flag_Set__c = true`, so there is no
`false → true` transition for this query to catch. Net-new arrival volume has to come from `Case.CreatedDate`
directly, not CFHT. Don't try to derive it from history-tracking data alone; the two are structurally
different signals and need two separate queries.

**Time with company vs customer (free split):** `SUM(FLAGS__Business_Hours_Elapsed__c)` grouped by
`FLAGS__Flag_Set__c` gives total org-court time (true = controllable, "waiting on us") vs customer-court
time (false = "waiting on them"). Consider excluding the trailing post-resolution interval (flag down,
ending in Case Closed) so a long pending-closure dwell doesn't inflate customer time.

**Ongoing-response time (CFHT) — compute per RUN, not per record.** *(Used for single-case timeline
narrative in D — e.g. "this cycle took 3.2 business hours" — and no longer as the Job C load weight; Job
C now uses `labor_per_clear`, a throughput ratio from daily clear counts rather than BH elapsed. See
`references/job-c-overload.md` for why: BH elapsed measures customer wait time, not rep labor time.)* Each
record's
`Business_Hours_Elapsed__c` covers only the interval since the previous record boundary. If nothing else
happened mid-cycle, the `Flag Cleared` record alone carries the whole response time; but any intervening
event (a status change, an owner change) splits the cycle across records, leaving the clear record with a
tiny tail. The real response time for a cycle is therefore the **contiguous run of `Flag_Set = true`
records** from the set that opened it through the clear that closed it. Two methods:
- **(a) Aggregate approximation (default — scales to any volume):** two small GROUP BY queries — per-case
  flag-up `SUM(Business_Hours_Elapsed)` and per-case genuine-clear `COUNT` (clears where Action is not
  `Case Closed`). Per-case mean cycle time = sum ÷ clears (skip cases with 0 genuine clears); the estimate
  is the **median of the per-case means**. Verified live to reconcile exactly with raw-run sums. SOQL has
  no CASE expression, so this two-query shape is required — a single `SUM(CASE WHEN …)` query is invalid.
- **(b) Raw runs (precise):** pull the raw `Flag_Set = true` records in Start order, sum each contiguous
  run ending in a genuine clear, take the median of the run totals. More precise but heavy — an active
  agent can have 1,000+ flag-up intervals in 90 days — so reserve it for small volumes or when the person
  asks for precision.
Genuine clears exclude the `Flag Cleared` + `Case Closed` housekeeping rows.

## Metrics Extension (`FLAGS_METRICS__`, optional package)

If installed, adds pre-computed business-hours metrics on Case:
`FLAGS_METRICS__Business_Hours_Elapsed_Current__c`, `_Previous__c`, `_Total__c`, plus company/customer
wait splits. Prefer these when present; otherwise derive from CFHT. (Not used for the overload load
estimate — see SKILL.md.)
