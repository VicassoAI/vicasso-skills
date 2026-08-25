# Scripts

Deterministic computation for the parts of this skill that are arithmetic rather than
judgment. The reference files remain canonical for *semantics* — what a field means, which
query to run, how to read a result. These scripts own the *reductions*: stateful walks over
ordered CFHT records, medians over hundreds of values, and reconciliation checks.

## Cost model — read this before reaching for a script

Scripts do **not** save input tokens. SOQL results arrive through the MCP connector into
context, so feeding them to a script means writing them out as JSON first. What scripts buy:

- **Correctness on stateful walks.** Run stitching and the Job F owner walk are off-by-one
  hazards; a script gets them right identically every time.
- **Cheap output.** A script prints a 20-line summary instead of narrating 4,000 rows.
- **Pitfalls as failures.** The silent-zero trap and Job F's impossible values are assertions
  here, not warnings someone has to remember.
- **Real reuse.** Cached pulls in the session cache make `references/soql-followup-investment.md` §8's "pull
  once
  and reuse" actual rather than aspirational. `cfht_merge.py` prints the path it wrote.

**Order of preference: SOQL aggregate → script → inline reasoning.** If a `GROUP BY` returns
the number, never pull raw rows to compute it. If it needs a sort or a stateful walk, script
it. Reason inline only when the answer is a judgment.

## Calling convention

Write connector results to JSON, then pass the path. Every script accepts a bare JSON list,
`{"records": [...]}`, or the full Salesforce envelope, and every script takes `--json` for
machine-readable output instead of the human summary.

```bash
cd scripts   # or add it to PYTHONPATH; cfa_common must be importable
# <cache> is the path cfht_merge.py prints, e.g. .../cfa-session-<user>/cfht-90d.json
python3 run_stitch.py --input <cache>/cfht-90d.json --mode ongoing
```

Exit codes: `0` success · `1` empty input · `2` data error (missing column, unusable input)
· `3` a validity check failed (e.g. Job F produced a negative response time) — a `3` means
stop and debug, not report with a caveat.

## The scripts

### `cfa_common.py`
Shared helpers, not run directly. `require_columns()` is the silent-zero guard;
`check_variance()` catches the uniform-population signal; `median`/`percentile`/`describe`
back every statistic; `weekday_occurrences()` handles the forecast denominator;
`parse_dt()` copes with Salesforce's `+0000` offsets.

### `cfht_merge.py` — paginated pulls
Merges pages, dedupes by `Id`, reconciles against a `COUNT(Id)`, validates required columns,
reports the `FLAGS__Start__c` span actually covered, and caches to a per-user `0700`
directory under the OS temp dir (files `0600` — the cache holds real case data).
Warns when any page returns exactly 2000 rows (the hard cap — more pages almost certainly
exist, and `OFFSET` is itself capped at 2000).

```bash
python3 cfht_merge.py --pages p1.json p2.json --expect-count 4193 --label rep-90d
```

### `run_stitch.py` — contiguous flag-up runs
The walk that `references/field-reference.md`, `references/followup-time-investment.md`, Job D and Job H §10.6
each
describe separately. Modes:

| Mode | Serves | Returns |
|---|---|---|
| `runs` | inspection | every run with its opening trigger and closing shape |
| `ongoing` | field-ref (a)+(b), H §10.3 | both documented methods side by side |
| `followup-split` | followup-time-investment, C/E | follow-up vs other genuine clears + batching gap |
| `worst-run` | H §10.6/§10.9 | longest continuous wait, concentration, stall vs volume |
| `down-intervals` | H customer turnaround | flag-down stats, post-resolution dwell excluded |

Runs beginning at a case's first record are flagged `flagged_at_creation` and excluded from
the follow-up split rather than guessed at. Genuine clears exclude the
`Flag Cleared` + `Case Closed` housekeeping shape. `--stall-bar` takes the org's ET3 offset
from Preflight — it is never hardcoded.

### `assignment_split.py` — Job F
Two-pass by design. Pass 1 identifies the landing transitions and prints a ready-to-run
§9.3 `IN` clause; resolve those actors, then pass 2 buckets self / peer / no-handoff.

Enforced: `Business_Hours_Elapsed__c` present *and* not uniformly zero (pitfall 1); the
transition record is `i-1`, with a report on any whose `Event` is not `Case Owner Changed`
(pitfall 2); `--rep-name` required alongside `--actors`, since self-detection matches on
display name and without it every self-assigned case lands in the peer bucket.

`response = total_ir - assignment` by subtraction, so a walk bug shows up in
`assignment_bh`. Note that this makes `assignment + response == total_ir` an identity — it
is **not** a reconciliation, and an earlier version reported it as one. What is checked
instead: a negative `response_bh` is impossible and fails the run (exit `3`), and the
CFHT-measured initial-response span is compared against
`FLAGS__Initial_Response_Business_Hours__c` as an independent cross-check that warns on
disagreement (it also shifts when the retention window opens after case creation, so it
does not gate the exit code).

The self-vs-peer response gap is computed explicitly because it is a repeated finding that
should not be buried in a table.

```bash
python3 assignment_split.py --cfht cfht.json --cases cases.json \
    --rep-id 005... --rep-name "Name" --actors actors.json \
    --peer-actors "Peer One,Peer Two"
```

### `stats.py` — distributions and the load weight
`describe` mode summarises any numeric field, optionally grouped, with a low-confidence note
below `--min-n`. `labor-per-clear` mode turns §5/§7.4 daily-clear-count rows into
`8h ÷ median(daily clears)` per owner, flagging anyone under ~10 distinct workdays.

Mean sits beside median everywhere on purpose: the ratio is the tail signal Job H thresholds
at 1.5×, and a clean median resting on one catastrophic case is the most misleading read
available.

## Not scripted, deliberately

Preflight interpretation, business-hours mode inference, Job D's lens selection and every
narrative, the neutrality guardrails, and Job G/H's faithful-vs-accurate framing. These are
judgment. Scripting them would make the skill worse.

## Still to build

`load_forecast.py` (Job C/B weekday bucketing, 8:30 cutoff, banding),
`outlier_classify.py` (Job H §10.9 concentration), `flag_timing.py` (ET level + overdue
formatting for Jobs A/B), `recurrence.py` (Job D tag G, Job E §6), and
`labor_assumptions.py` (parse the markdown table, per-person-over-default precedence).
`cfa_common.weekday_occurrences()` already exists for the forecast.
