# Job H — Account responsiveness (two-sided: how the account experienced us, and how responsive it has been)

Roll the flag timeline up to a **customer account** and read it in both directions. The same flag that drives
every other job carries the answer: a **flag-up interval** (`FLAGS__Flag_Set__c = true`) is time the account
waited on us — *how they experienced the service team* — and a **flag-down interval**
(`FLAGS__Flag_Set__c = false`) is time we waited on them — *how responsive the account has been back to us*.
Everything else here is aggregation and honest labeling on top of that one distinction (semantics:
`references/field-reference.md`, "Time with company vs customer" and the CFHT table).

This is the account-level cousin of Job G's support-vs-customer split (which groups by owner) and reuses Job
D's run-based response method (which reads one case). Job H groups by **Account** and is written for a
customer-facing read — renewal/QBR prep, at-risk detection, and the "is the latency us or them?" question.

## When to use, and the two modes

Trigger on: "how has [account] experienced us", "how responsive is [account]", "account responsiveness",
"responsiveness for [account] before the renewal", "which accounts are we slowest to", "which customers are
least responsive to us". Decide the mode from whether a specific account is named:

- **Profile mode** (an account is named) — a deep, two-sided read of one account. This is the accurate read:
  small enough volume to compute medians, stitch runs, and run the full outlier/concentration pass
  ("Spot the outlier case" below).
- **Roster mode** (no account named) — a ranked list across accounts. This is the scalable read: per-interval
  means (Job-G style), clearly labeled as less precise than the profile. Rank by whichever side the ask
  implies ("slowest to" → our-court; "least responsive" → their-court). Full outlier classification doesn't
  scale to the grouped roster query, so carry only a lightweight **concentration flag** here — mark any
  account whose single worst case drives ≥ the concentration bar of its total (a cheap top-case-vs-total
  check) so the row visibly says "one-case-driven — open the profile." The volume-vs-stall diagnosis belongs
  to profile mode.

## What the profile shows

Lead the **"how they experienced us"** side with the three reads you asked for, in this order:

1. **Typical response time (median).** Two numbers, both business-hours by default (offer Standard on request):
   - *Initial response* — median of `FLAGS__Initial_Response_Business_Hours__c` across the account's cases
     (Case field, **no CFHT** — always available). This is first-touch.
   - *Ongoing response* — median per-case cycle time from the **run-based** method
     (`references/field-reference.md`,
     "Ongoing-response time — compute per RUN"; default to the aggregate approximation (a)). This is
     every subsequent reply, and it is the accurate figure — not the per-interval mean.
   Keeping these two separate is the "initial vs ongoing split" — a slow first touch and a slow ongoing cadence
   are different failures and read differently to a customer.
2. **Worst waits + severity.** The single longest our-court wait (a worst **run**, not a worst interval —
   compute from raw flag-up runs in profile mode; a per-interval MAX understates any cycle split across
   records), shown with its `CaseNumber` link, plus **worst severity reached** = distinct cases that hit
   **L3** (red) and **L4** (breach) — `FLAGS__Flag_Level_BH__c`, §10.5. Report both levels, not L4 alone:
   on fast-response accounts L4 is often zero while L3 still names the cases that ran hot, so an L4-only
   count reads as a misleading flat zero. One long wait often *is* the relationship story, so surface it
   even when the median looks fine — and see "Spot the outlier case" below for reading it correctly.

Then the **"how responsive the account has been"** side (their court, `Flag_Set = false`):

- *Typical turnaround* — median of flag-down interval business-hours, **excluding the trailing
  post-resolution interval** (a down-interval whose `FLAGS__Action__c = 'Case Closed'`); otherwise a long
  pending-closure dwell inflates their apparent slowness (`references/field-reference.md`, "Time with company vs
  customer"). Their worst gap is the max of the same set.
- *Currently in their court* — a snapshot count of the account's **open** cases with no flag up right now
  (we're waiting on them). This is the one live, actionable number on the customer side.

Queries for all of the above: `references/soql-account.md` §10.

### Spot the outlier case (why this beats a plain report)

A customer's felt experience is often **one case**, not the average — and a summary quietly hides exactly
that. This is the read a native Salesforce report can't give, so it's core to Job H, not a nicety. Do it on
**both** sides (our court and theirs), using §10.9 (one grouped pull: per-case total, interval count, and
largest single interval) plus the Tunable-constants thresholds:

1. **Concentration.** What share of the side's total time is the top case, and the top 3? When the top case
   clears the concentration bar (default ≥ 30%), say so plainly — "this account's number is essentially one
   case" — and name it with a link. An account at 34%-from-one-case and one at 12% can post the *same*
   average and mean opposite things; the concentration line is what tells them apart.
2. **Median vs mean.** Report both. When the mean materially exceeds the median (default ≥ 1.5×), the
   distribution has a tail — an outlier is present even when the median looks clean. Don't "fix" this by
   showing only the median: a spotless median sitting on top of one catastrophic case is the most misleading
   read of all. The gap is the signal; surface it.
3. **Classify the outlier — volume vs stall (the part that changes the diagnosis).** A big case is big for
   one of two opposite reasons, and they call for opposite conversations:
   - **Volume / iteration** — high total time spread across **many** intervals, but no single continuous
     wait is long (largest interval below the stall bar). This is a complex, many-round case where each
     reply was fast. It is *not* a dropped ball — and saying so protects you when a raw hour count looks
     damning. (Live example: a 48.8-BH worst case that was 53 rounds with a 6.3-BH longest wait — heavy, but
     never neglected.)
   - **Stall** — a single continuous interval that reaches the **stall bar** (the org's ET3/red offset from
     Preflight, `FLAGS__TimeOffset3__c`). One long unbroken wait = a genuine dropped ball, and it reads that
     way to the customer regardless of the account's tidy average.
   The highest-total case (concentration leader) and the longest-single-wait case (stall leader) are often
   different cases — surface both when they are. The same split applies to the customer side: one long single
   gap = they went dark on a specific case (champion left? case abandoned?), which is a different story from
   broadly slow replies across many cases.

Lead the profile's two sides with the typical numbers, but always run the outlier pass underneath and raise
a flag the moment concentration or a stall crosses its bar — that flag, with the named case and its
classification, is usually the single most useful line in the whole read.

### Optional cuts (off the default headline)

- **Per-CSE breakdown** — which of the team carried this account's cases and their share, for handoffs or
  renewal coverage. Uses interval owner; remember `FLAGS__Owner_Name__c` is the **queue** name during a
  queue-held interval (`references/field-reference.md`), so a queue can appear alongside people — say so
  rather than
  reading it as a person.
- **Sentiment cross-reference** — if the person is prepping a renewal, offer to line the responsiveness read
  up against the account's survey/NPS (that lives outside this package — hand off to the survey skill rather
  than querying it here). Keep this an offer, not a default, so Job H stays portable.

## Scope, window, and edge cases

- **Window:** trailing 90 days by default (consistent with the rest of the skill), on CFHT `FLAGS__Start__c`
  and on `FLAGS__Initial_Response__c` for the initial figure. Overridable; honor the **post-install cutoff**
  (Job G) — cases created before Case Flags was installed carry unreliable history, so offer to bound to
  post-install and flag when a number may include pre-install cases.
- **Account hierarchy:** resolve the account by name; if it is a **parent with child accounts**, ask at
  run-time whether to roll the children up rather than assuming either way (§10.1). Don't bake a specific
  org's account structure into the skill.
- **Selective orgs:** scope through the Case relationship —
  `AND FLAGS__Case__r.FLAGS__Enable_Case_Flags__c = true` — so you don't count cases Case Flags ignores.
- **Silent-zero caution:** always SELECT `FLAGS__Business_Hours_Elapsed__c` explicitly; omitting it makes
  every BH sum default to 0, which reads as a real (wrong) finding rather than a missing column
  (`references/field-reference.md`).
- **Housekeeping clears:** exclude the `Event = 'Flag Cleared'` + `Action = 'Case Closed'` rows from
  response-time analysis — those are close housekeeping, not a human reply.

## Compare to normal (opt-in, our-court only)

By default Job H shows the account's own numbers. When someone asks how the account stacks up — "is this
normal?", "how do they compare to our average?" — add a benchmark, but **only on the "how they experienced
us" side.** There is no meaningful "normal" for how fast one customer replies to us, and benchmarking their
court would read as grading the customer against other customers — not the point, and not something to put in
front of a renewal. So the customer-responsiveness side never gets a baseline.

"Normal" = the org's own performance over the **same window, computed the same way** (§10.10): pooled
per-cycle ongoing and average initial response across all flag-enabled cases, ideally excluding the target
account (so it reads as "vs everyone else") and any internal/house account whose volume would distort the
average. Compare like-for-like — account mean vs org mean — and say it in plain terms ("initial response
about a fifth slower than normal; ongoing replies roughly a third faster"). Watch the median/mean interaction
from the outlier read: an account can sit *faster* than normal on its typical (median) case yet *slower* on
the mean when a few outlier cases drag it up — call out which one you're showing so the comparison doesn't
mislead. Keep it a default-off overlay so the base read stays portable and uncluttered.

## Faithful vs. accurate — be honest about which you're showing

Same discipline as Job G. **Profile mode** is the accurate read: medians, run-stitched cycles, worst **runs**.
**Roster mode** uses per-interval means so it scales to every account in one grouped query — label it as the
approximation it is, and if a specific account in the roster looks alarming, offer to drop into profile mode
for the precise picture before anyone acts on it. Never present a per-interval roster mean as if it were the
run-based median.

## Present it like the rest of the skill

**Open with a plain-language narrative.** Before any table, give a 2–4 sentence summary in words a non-analyst
can act on: translate business hours into human terms ("within an hour of business time," "about two business
days"), name the single most important finding (usually the outlier/concentration flag, by case number), and
give the two-sided takeaway — how fast we were, and where the ball mostly sat. If a "vs normal" overlay was
run, fold its one-line verdict in here too. This narrative is what a CSM reads aloud in renewal prep; the
tables below are the evidence for it. Keep it honest and specific — anchor to the real worst case — not
generic praise.

Then the data, plain and scannable — sectioned tables, no widget (SKILL.md output style). Profile mode: a
short header (account, window, case count) then two sections, "How {account} experienced us" and "How
responsive {account} has been," with the optional CSE cut and the "vs normal" columns only if they were
asked for. Roster mode: one table, accounts as rows, columns for our-court and their-court typical time plus
worst-severity, sorted by whichever side the ask implies, with the concentration flag marking one-case-driven
rows. Render any listed case as a `CaseNumber` link per the SKILL.md preflight rule.

## When CFHT is unavailable

The full two-sided read needs CFHT (all elapsed times, the customer side, worst waits, breaches, ongoing
response). Degrade gracefully like Job C/G: run the **initial-response median** (Case field, §10.4) and a
**current flag-state snapshot** for the account's open cases (how many are flagged now and at what level), and
say plainly that the ongoing-response, customer-court, worst-wait, and breach figures need the Case Flags
History Tracking object — ask the admin to enable history tracking and grant access.
