# Job Z — Setup: declare labor assumptions

A one-time (or revisitable) onboarding step. Unlike the Preflight (which resolves *org configuration*
silently and never asks the user anything), this step resolves a *person-specific belief* that CFHT
cannot observe on its own — so it has to ask.

## When to trigger

- **Automatically, once per person, the first time** a job needs `references/labor-assumptions.md` for that
  person
  (Job C banner add-on, Job E team rollup, or an explicit follow-up-time-investment ask) and that
  person's row is missing or shows `source: default (not yet declared)`. Don't block the rest of the
  output on this — run Setup inline as a short add-on to whatever answer is otherwise ready, not as a
  gate in front of it.
- **Explicitly**, on phrasing like "set up my time assumptions," "how long do follow-ups take me," or a
  manager asking to set team defaults.

## Flow

1. Read the current defaults from `references/labor-assumptions.md`.
2. Ask the person (in plain language, not jargon): *"I can estimate how much time your follow-up clears
   are costing you, but I don't have a way to measure that directly — only you know how long a typical
   follow-up takes versus a typical troubleshooting clear. Want to go with a default of ~6 minutes per
   follow-up and ~30 minutes for everything else, or set your own?"*
3. If they accept the defaults: write a row for them with those values, `source: declared`, and today's
   date — this converts them from "using the fallback default" to "explicitly confirmed the default,"
   which matters for trust in the resulting numbers even though the values are unchanged.
4. If they give different numbers: write their row with those values, `source: declared`, today's date.
5. If they say "I don't know" or want to skip: leave their row as `default (not yet declared)` and
   proceed with the org-wide default for this session — don't nag every session, just don't mark it
   declared either. Re-offer only if they explicitly ask again.
6. A manager can do this once for the team by editing the **Defaults** section directly instead of
   walking through per-person rows — mention this option if a manager is the one asking.

## Writing back

Use `str_replace` against `references/labor-assumptions.md` to add or update the person's row in the
"Declared values by person" table. This is a real edit to the skill's own file, not a session-only value —
say so plainly ("I've saved that to your labor assumptions file") so the person knows it will persist
across sessions, and remind them that if this skill gets repackaged/reinstalled from a version prior to
their edit, the edit won't carry over — worth a quick check after any reinstall.
