# Job F — Assignment time vs. response time decomposition

CFHT-dependent. Splits `FLAGS__Initial_Response_Business_Hours__c` into two parts per case:
- **Assignment time**: Case creation → landing with whoever ultimately produces the initial response
- **Response time**: That landing point → the flag actually clearing (initial response)

These two must sum to the case's total initial-response BH. Use this as a mandatory reconciliation
check — if they don't sum, the split logic has a bug, not the data. Validated across three
independent reps' populations (601 handoff cases total) with reconciliation error at floating-point
noise level (~1e-16) in every case — treat any larger discrepancy as a bug in a future run, not as
real data variance.

## Self vs. peer vs. no-handoff

Every case falls into exactly one bucket:
- **Self-assigned**: the person who ends up with the case pulled/claimed it themselves (actor of the
  landing transition == the new owner). Report separately — mixing these into "how fast do peers
  assign work" understates real peer-assignment behavior. Self-assigns are NOT trivially fast on
  assignment time (that was a measurement bug the first time this was built — see "Known pitfalls"
  below) but they ARE consistently faster on response time than peer-assigned cases in both reps
  checked so far (Jessie: 0.33 vs 0.90 BH; Kristin: 0.70 vs 1.72 BH). Flag this response-time gap
  explicitly when reporting — it's a genuine, repeated finding, not noise.
- **Peer-assigned**: someone else (a teammate) performed the transition that landed the case with
  its final owner.
- **No handoff recorded**: no `Case Owner Changed` event exists for this case within the CFHT
  retention window (`FLAGS__HistoryTrackingMonths__c`). Treat assignment time as unknown/0 and
  response time as the full total — do NOT guess who assigned it or when. In validation this bucket
  ran ~10-26% of each rep's population; it's common enough to always report as its own line, not a
  footnote.

Scope which actors count as "peer" explicitly per run (e.g. "only Brian/Jessie/Kristin, exclude
manager reassignments") — this is a parameter, not a hardcoded assumption, since different orgs will
want different actor sets in scope.

## Multi-hop rule

If a case bounces queue → Person A → Person B before the flag clears, do NOT split the assignment
leg by hop. Lump ALL time from case creation through the FINAL landing transition into one
"assignment time" number, and attribute it to whoever performed that FINAL handoff (the one that
produced the eventual responder) — not to whoever touched it earlier. The rationale: the metric is
"how long did it take before the responding person had it," and the final assigner is the one whose
action determines that duration. Earlier hops are invisible to this metric by design.

## Method

1. Run Preflight; confirm `FLAGS__Track_Case_Ownership__c` is true (needed for `Case Owner Changed`
   events) and note `FLAGS__HistoryTrackingMonths__c` as the window's outer bound.
2. Pull the case population: `Id, FLAGS__Initial_Response_Business_Hours__c` for cases owned by each
   in-scope rep, `FLAGS__Initial_Response__c` within the target window, plus `{CF_SCOPE}` per
   SKILL.md conventions.
3. Pull CFHT for those cases: `Id, FLAGS__Case__c, FLAGS__Start__c, FLAGS__End__c, FLAGS__Owner__c,
   FLAGS__Owner_Name__c, FLAGS__Event__c, FLAGS__Business_Hours_Elapsed__c` — ORDER BY
   `FLAGS__Case__c, FLAGS__Start__c ASC`.
   **CRITICAL: `FLAGS__Business_Hours_Elapsed__c` MUST be explicitly selected.** Omitting it doesn't
   error — every case will silently compute as "0 assignment time," which looks like a real (and
   wrong) finding rather than a missing column. This exact mistake happened once already in the
   development of this job; treat its absence from the SELECT list as a blocking bug in any future
   run.
4. Per case, walk records in Start order. Find the index `i` where `FLAGS__Owner__c` first equals
   the case's final owner AND the record at `i-1` has a different owner. Record `i-1` is the true
   landing transition — **not** record `i`. In one verified example, record `i` was a
   `Case Status Changed` / `Local Automation` blip that fired seconds after the real ownership
   change, under a different user's session — using it as "the" transition silently misattributes
   the actor. Always locate the actual `Event = 'Case Owner Changed'` record; don't assume "first
   record with the right owner" is it.
5. `pre_response (assignment time)` = `SUM(FLAGS__Business_Hours_Elapsed__c)` for every record from
   index 0 through `i-1` inclusive.
6. `response_phase` = `total_ir - pre_response` (don't re-derive it by summing forward from `i`
   independently — computing it as a subtraction guarantees the reconciliation check always passes
   by construction, and any bug in the walk-forward logic will show up as an inconsistent
   `pre_response` instead of a silently-wrong `response_phase`).
7. Actor of `i-1`'s `CreatedBy.Name` determines self/peer per the rule above. For the actor lookup,
   query `Id, CreatedById, CreatedBy.Name` on the specific set of transition-record IDs found in step
   4 — don't try to get CreatedBy in the same bulk pull as step 3, since that field isn't needed for
   the large majority of records and bulk-fetching it for everything wastes a very large query for
   no benefit; fetch it only for the (much smaller) set of actual transition records.
8. If no such `i-1` exists at all (case owned by final owner from the first record in the window):
   bucket as "no handoff recorded."

## Cross-check available: CaseHistory

Standard Salesforce `CaseHistory` (`Field = 'Owner'`) is the authoritative system-of-record for
*who* performed an ownership change — more authoritative than trusting CFHT's own `CreatedBy` in
isolation, since CFHT is package-generated bookkeeping. Use it to validate the actor determination
(not the timing/BH split, which only exists in CFHT). Note: `OldValue`/`NewValue` on `CaseHistory`
cannot be filtered in a WHERE clause (`INVALID_FIELD` error) — pull by `Field`/`CreatedDate` range
only and filter old/new values in code afterward.

## Known pitfalls (both hit during development — treat as permanent warnings)

1. **Missing `Business_Hours_Elapsed__c` in the SELECT list.** Produces a uniform, plausible-looking
   "0.00 assignment time for every case" result. This is NOT a real finding (queue dwell time is
   genuinely non-trivial — validated mean 0.5-0.6 BH, max 4-7 BH across three reps) — it's a silent
   data-availability bug. Any run showing literally zero variance across an entire population is a
   signal to check the field list before reporting the result.
2. **Using "first record with the right owner" instead of the actual transition record.** The first
   record where `Owner__c` matches the final owner may be a downstream automation event (e.g.
   `Case Status Changed` / `Local Automation`) that fired under a *different* user's session moments
   after the real ownership change. This misattributes the actor. Always walk back to find the
   record immediately preceding the owner change (index `i-1` in step 4), and prefer verifying with
   `FLAGS__Event__c = 'Case Owner Changed'` and/or the CaseHistory cross-check when actor attribution
   matters (e.g., manager wants to know who is/isn't self-assigning).

## Pagination trap (routine at this data volume)

CFHT pulls for an active team routinely exceed 2,000 records (the max page size regardless of
`LIMIT`). Salesforce also caps `OFFSET` at 2000. Pattern that works: query #1 `LIMIT 2000`, query #2
`LIMIT 2000 OFFSET 2000` (reaches record ~4000), query #3 `ORDER BY ... DESC LIMIT n` for the tail if
the total exceeds 4000, then dedupe all batches by record `Id` before processing. Confirm the
merged, deduped count matches a separate `COUNT(Id)` query before trusting the split numbers. Case
populations of ~200-270 cases per rep typically produce ~3,800-4,300 CFHT records — plan pagination
accordingly.

## Output

Report, per rep, per bucket (self / peer / no-handoff):
- n
- mean & median assignment time (BH)
- mean & median response time (BH)
- reconciliation check (max abs diff between `pre_response + response_phase` and `total_ir` — should
  be ~0, i.e. floating-point noise only; anything larger means stop and debug before reporting)

Cross-tab by assigner → final-owner pair for peer-assigned cases, same as Job B/E style breakdowns.

Always call out the self-vs-peer response-time gap explicitly if present — in both validated cases
so far, self-assigned cases were answered meaningfully faster (2-3x) than peer-assigned ones. This
is worth a manager's attention (e.g., it may mean handoffs sit in an inbox before being noticed) and
should not get buried in a table without comment.
