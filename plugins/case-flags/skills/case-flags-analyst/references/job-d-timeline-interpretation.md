# Job D — Timeline Interpretation ("walk me through this case")

Triggers: "walk me through case X", "what's the history on this case", "was this case handled well",
"give me the background before I call this customer". **Single case only** — a "zoomed out" view across
many cases (e.g. an account's whole case history) is a separate future job; if asked for that, say so and
offer to run this per-case instead.

CFHT-dependent. The §6 pull is the lazy probe: if it errors with an access error, CFHT is unavailable —
deliver the partial fallback described at the end of `references/job-e-manager-diagnostics.md` (vitals from Case
fields alone: initial response, current status, current flag).

**Step 1 — pull and compress.** Pull the case's CFHT records in `Start` order (`references/soql-timeline.md`
§6). Salesforce
automation can fire several CFHT records off one human action within the same second or two (e.g. sending
an email produces a flag-clear record and a status-change record simultaneously) — collapse any records
whose `CreatedDate` falls within ~2 seconds of each other into a single **compressed action** attributed to
whichever record's `Action` looks human-initiated (Email Sent/Received, a button click, a comment) rather
than `Local Automation` alone.

**Step 2 — tag each compressed action** against this taxonomy:
- **(A) Handoff** — `Event = Case Owner Changed` (queue→person, person→person, person→queue)
- **(B) Status change** — `Event = Case Status Changed` (only meaningful if `Track_Case_Status__c` is on)
- **(C) Long gap** — an interval that ran unusually long. For a flag-up interval, compare its
  `Business_Hours_Elapsed__c` against the *gap between the case's own aging-threshold offsets* for that
  band (`FLAGS__CaseTimeOffset_n__c` to `_n+1__c`) — i.e., it sat past where the org's own SLA said it
  should move to the next level. For a flag-down interval, compare against the flag-down long-gap bar in
  the SKILL.md **Tunable constants** block.
- **(D) Breach** — the interval in which the case crossed into L4 (`Flag_Level_BH = 'L4'` first appearing, or
  wall-clock passed `CaseFlagsEscalationTime4` while still flagged)
- **(E) Follow-up reflag** — `Action = 'Follow-Up Process'`
- **(F) Org-custom tracked field** — see "Detecting custom tracking" below
- **(G) Recurrence** — closed, reopened, and closed again at least once. Detection and trigger
  classification are canonical in `references/field-reference.md` ("Recurrence"); single-case mechanics in
  `references/soql-timeline.md` §6.
  Report which trigger path each reopening took (customer activity vs. Follow-Up Process pulling it back);
  do not editorialize about what it implies.
- **(H) Contact on a closed case** — a `Flag Set` with a customer Action (Email Received, External Comment
  Added, Customer Attachment Added, Chatter Post Received) while the case is closed. The product raises
  the flag by design. Report when it came, the time to the next genuine clear, and the level reached
  (the script's `customer_contacts.while_closed`). It is not a reopen unless the status reopened.
- **(I) Resolved status reverted on reply** — a resolved status changed to a non-resolved one within a
  minute of a genuine clear, with no customer contact since it was set. Case Flags never changes Status,
  so this is the org's own automation; attribute it that way. Only tag it when the person has named the
  resolved statuses.

Place each customer contact relative to the case's state (open, in a resolved status, or closed) and
say it neutrally: "the customer wrote while the case sat in Pending Closure" is an observation, not a
finding.

**Timestamps** are in the user's timezone, with daylight saving applied per date (a timeline crossing a
DST change shifts by an hour). **Level crossings** come from the case's own thresholds: a flag-up
stretch crosses L*n* at its start plus `FLAGS__CaseTimeOffset<n>__c` business hours, so say when it
reached L3, not only that it did. **Working days** use the case's own business-hours calendar; if the
aging speed changed mid-case, say so, since the hours before and after the change use different
calendars.

**Step 3 — build the vitals block** (same shape every time, regardless of lens). It always includes the
case's **True Case Age**: run `scripts/age_decompose.py --mode case` on the §6 pull plus the Case row
(see `references/job-i-true-case-age.md`), so a reviewer sees why the case is as old as it is, not just
how old. The block has:
- **Identity and age:** case number/subject, current status, opened date, closed date if applicable, and
  Salesforce's Age.
- **True Case Age:** the BH within Age split into waiting on us, waiting on the customer, resolved
  waiting to close, and (when non-zero) closed-gap, after-close and queue time. Give working days where
  the calendar is known.
- **Waits:** how many times the customer waited on us, labelled by how each ended (reply, manual clear,
  other) with the average, the longest and the highest level reached; and how many times we waited on
  the customer, labelled by how each ended (customer, Follow-Up Process, org automation) with the average
  and the longest. A manual clear is the Clear Flag button, a product feature for a response made
  another way; describe it neutrally. An org-automation-ended wait is a process outside Case Flags
  raising the flag (e.g. on assignment), not the customer.
- **Responsiveness:** initial response time (`Initial_Response_Business_Hours__c`). If the script says
  **rep-logged** (cleared within a minute of creation), say "logged by us" instead of quoting a response
  time.
- **People:** name any owner whose user is now inactive (`FLAGS__Owner_Is_Active__c = false`).
- **Now (open cases only):** current status and flag side by side, the follow-up date if set, and whether
  the case was modified after the last CFHT change (`LastModifiedDate` later than the last record's
  `End`: something changed that Case Flags doesn't track). Don't judge a status/flag mismatch unless the
  person has said which statuses mean waiting on the customer.
- **Shape:** handoff count; status-change count (if tracked);
breach count (how many separate times it reached L4: count contiguous L4 stretches, not L4 records, since one breach can span several records); follow-up-reflag count; **recurrence count** (number of
close events — `Action = 'Case Closed'`, either Event shape — beyond the first) and, if any, how each
reopening was triggered; aging speed(s) that
applied.

**The "silent auto-close" pattern (Tier 2 — ambiguous, always neutral).** A case that gets a short final
response, then times out into an automated-close status (readable directly from `FLAGS__Case_Status__c` on
the closing record — e.g. a status like `"Closed (Automated)"` — since status is already a tracked CFHT
field) with no further customer engagement before that close, has a recognizable shape: one short
`Follow-Up Process`-driven cycle at the end, then closure with nothing after it. **This shape alone cannot
tell you whether the customer was satisfied or gave up — both look identical in CFHT.** Surface it as
something worth a second look, never as a finding. Do not speculate about which explanation is more likely.

**Step 4 — infer the lens** from who's asking, not from how they phrase it (explicit phrasing overrides):
- Asker **owns** the case → **Personalize**: skip the vitals block and the structured narrative entirely.
  Output a single present-tense paragraph, **never more than 50 words**, written the way the owner would
  describe their own case out loud: felt time ("opened yesterday," "this morning") rather than exact
  timestamps, one arc instead of a blow-by-blow, ending on what they're currently waiting for. See the
  neutrality guardrail below — this format is the most tempting one to over-narrate, and the most
  important one to keep honest, since it reads as the owner's own voice.
- Asker **manages** the owner (or is reviewing someone else's case with them) → **Coach**: full detail —
  every compressed action, teaching-conversation depth.
- Case is **closed** and the ask is evaluative ("was this normal", "anything to note") → **Audit**: vitals
  plus every tagged event (A–F) in the case, neutral tone. State the facts; do not judge "good" or "bad" —
  neither the person nor the skill yet has a baseline for what's typical, so let the human decide.
- Ask is framed toward an upcoming **customer/account conversation** → **Prep**: sparse. Vitals plus only
  genuine abnormalities: a real service-side gap (an org-court interval that blew past the case's own SLA
  thresholds — tag C on a flag-up interval, or a breach) or a pattern of customer-side delay (repeated or
  large flag-down gaps). No interaction-by-interaction detail.

For Coach, Audit, and Prep: always render the vitals block first, then a structured narrative scaled to
the lens, then a **Takeaway** sentence if the case trips any trigger in SKILL.md's constants (rules in
`references/job-i-true-case-age.md`, "Takeaways"). No trigger, no takeaway line. Personalize is the one
exception — no vitals block, just the 50-word paragraph. When a trigger fires there, the paragraph may
carry the gist in the owner's own voice ("they've only replied when the follow-up nudged them").

**Neutrality guardrail for the Personalize paragraph (and every lens, but easiest to violate here):**
Because this format compresses several cycles into a short arc, it's tempting to smooth the numbers into
a cleaner story than they actually show — don't. Two specific traps:
- **Don't assert a trend the numbers don't clearly support.** If response times went 4.7h → 2.5h → 0.4h →
  1.0h, that's not monotonically "getting faster" — say something true and vaguer ("stayed brisk") rather
  than a specific directional claim the data doesn't back.
- **Don't assert an outcome CFHT can't see.** A cleared flag means the ball is in the customer's court, not
  that the issue is resolved — CFHT has no way to distinguish "waiting for a fix confirmation" from
  "waiting for anything else." Say "waiting on their next reply," never "waiting for them to confirm it's
  fixed" or similar, even if that's the likely read.

Example (48 words): *"This case opened yesterday morning; you responded within the hour and it's stayed
at L1 the whole time — never close to escalating. They've replied a few times since, each round moving
briskly on both sides. You're currently waiting on their next reply."*

**Pronoun usage.** Cases and accounts have no gender, and the customer's or agent's gender is rarely known
from CFHT data alone (a name doesn't reliably indicate it either). Use **they/them** for the customer and
for any individual referenced by name when gender isn't explicitly known — this applies to the Personalize
paragraph and every other lens's narrative. Don't infer gender from a name.

**Optional compact vitals line for Personalize.** The 50-word paragraph is the default and typically all
that's needed. If the person is reviewing several of their own cases side by side (rather than asking
about one case before replying to it), a single compact line of key numbers above the paragraph can help —
e.g. `Age 18d · 14.1 BH on us (12 waits, avg 1.2) · 97.2 BH on customer (11 waits, avg 8.8) · max L3`. This is one line, not
the full vitals block, and stays optional rather than default: only add it when the person is scanning
multiple cases or asks for the numbers alongside the narrative.

**Detecting custom tracking (F).** CFHT's `Event` values are fixed by the managed package, but a customer
can configure Case Flags Setup to track additional Case fields on CFHT records. Don't hardcode a field
list — look at what fields actually carry data on this org's CFHT records beyond the ones in
`references/field-reference.md`. If you find populated fields you don't recognize: (1) do NOT proactively
ask if nothing extra is present — most orgs won't have this; (2) if something is there, surface it plainly
("this org also tracks `{field}` on Case Flags History — here's what changed and when"), ask the person
what it means, and suggest they note it in their own copy of this skill for next time.
