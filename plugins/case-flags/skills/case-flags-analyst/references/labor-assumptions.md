# Labor Assumptions (declared, not observed)

CFHT cannot measure actual rep effort — it only records when things started and ended
(`references/field-reference.md`). Everything in this file is a **stated belief**, not a measurement. The skill
reads it to translate flag-clear *volume* (which CFHT can count) into estimated *hours* (which it can't
directly measure), and to compare declared assumptions against observed batching patterns as a reality
check — never to silently override the declared number.

This file lives inside the skill (not Salesforce) on purpose: it's easy to edit, easy to see at a glance,
and doesn't require a schema change. If this proves valuable across customers, a future version could move
it into Case Flags configuration in Salesforce — not a today concern.

Edit the tables below directly. There is no UI for this; a text edit is the interface.

## Defaults (used for anyone without a row below)

- `minutes_per_followup_clear`: 6
- `minutes_per_other_clear`: 30

At these defaults, 10 follow-up clears + 14 other clears (24 flag clears total) works out to
`10*6 + 14*30 = 480 minutes = 8 hours` — a full day's effort as a sanity-check starting point.

## Declared values by person

| Person | User Id | minutes_per_followup_clear | minutes_per_other_clear | Declared on | Source |
|---|---|---|---|---|---|
| Sample Person | (fill in User Id when declared) | 6 | 30 | — | default (not yet declared) |

The row above is a format example, not a real person — replace it (or add alongside it) as people go
through Setup. An empty table (just the header row) is equally valid; Job Z adds a real row the first
time someone actually declares.

**Source** is `default` until the person has gone through Setup (`references/job-z-setup.md`) and explicitly
confirmed or overridden the numbers, at which point it flips to `declared` and gets a real date. A row
with `source: default` is functionally identical to having no row at all — it exists as a placeholder so
Job Z knows who still needs to be asked.

## Declaring at the team level instead of per-person

A manager can also declare on behalf of the whole team by editing the **Defaults** section instead of
adding individual rows — this is the team-wide option. Per-person rows always take precedence over
defaults when present, so the two approaches compose: use team defaults until/unless a specific person's
observed pattern (see `references/followup-time-investment.md`) suggests their number is meaningfully
different, then
give them their own row.
