# Job C — Overload read

Triggers: "am I overloaded", "do I have a light day", and as the My Day banner (job A) / roster load
column (job B). The idea: a flag tells you a deadline but not how much work a case needs, so use the
person's own throughput as a proxy for "one unit of responsiveness work," and compare the cumulative
work in their queue — plus what's likely to still arrive today — to a day's capacity.

- **Capacity** = a flat 8 business hours (an estimate; ignore breaks/meals).
- **Load set** = the person's owned cases that are currently flagged OR have a follow-up date of today —
  counted as a single total, no initial/ongoing split (see `labor_per_clear` below).
- **Weight**: `labor_per_clear = 8h ÷ avg_daily_clear_count`, where `avg_daily_clear_count` is the median
  of the rep's per-day Flag Cleared counts (excluding Case Closed events) over the trailing 90 days (SOQL
  §5). This is a throughput ratio, not a time-elapsed measurement — it replaced an earlier BH-elapsed
  "ongoing median" that conflated customer wait time with rep labor time (see below).
- `estimatedLoadHours = totalLoadSetCount * labor_per_clear` (`references/soql-overload.md` §5).
- **Medians** over the trailing 90-day window (see SKILL.md constants — never longer, even if retention
  allows), using the **median** not the mean, for the same reason as always: a couple of unusual days
  (backlog clearing, a half-day before PTO) shouldn't skew what a typical workday looks like.
  - Initial median: from `FLAGS__Initial_Response_Business_Hours__c` — always available (§5), used only as
    the CFHT-unavailable fallback for `labor_per_clear` now (see below), not as its own load weight.
  - `labor_per_clear`: from CFHT via the daily-clear-count method (`references/soql-overload.md` §5). **This
    is the session's lazy
    CFHT probe**: attempt it directly; an access error means CFHT is unavailable — fall back to the
    initial median in its place and state plainly that the read is "based on average time for initial
    response." Flag the read as low-confidence if fewer than ~10 distinct workdays are in the sample.

**Why this replaced the BH-elapsed ongoing median:** the old metric measured how long a flag sat before
clearing, not how long the rep actually spent on it — a case that ages for 2.5 business hours before a
20-minute fix inflates the load estimate for the rep who happened to be busy elsewhere while it aged, and
does the same in reverse for a rep who clears fast but juggles high volume. `labor_per_clear` sidesteps
measuring effort directly: it just asks how many clears a rep typically produces in a day, and divides the
day by that. A rep doing fewer, deeper clears naturally shows a higher per-clear cost; a rep doing more,
lighter clears naturally shows a lower one — self-calibrated per rep without classifying case complexity.

## Intraday forecast term

`estimatedLoadHours` is a snapshot — it only sees demand that already exists at report time. It
consistently underestimates the day because it has no term for what arrives afterward: customer
re-replies re-triggering flags, and net-new cases coming in before the report was even run for. Add a
forecast term (queries and formula in `references/soql-overload.md` §5 "Intraday forecast inputs"):

```
expectedIntradayLoadHours = (expectedNetNewCount + expectedReflagCount) * labor_per_clear
totalForecastHours = estimatedLoadHours + expectedIntradayLoadHours
```

`expectedNetNewCount` and `expectedReflagCount` are the rep's historical average count of that arrival
type, for today's specific weekday, arriving after the report cutoff (8:30 AM local — SKILL.md constants).
Both are now weighted by the same `labor_per_clear` coefficient, since it already reflects the rep's
actual average across every case type they handle — no need for a separate weight per arrival type. Net-new
needs no CFHT (Case object only); re-flag does. On a CFHT access error, keep the net-new term (weighted by
the initial-median fallback) and drop the re-flag term, labeling the forecast accordingly (§5).

Band `totalForecastHours` against the 8h day using the four bands in the SKILL.md **Tunable constants**
block — the forecast number is what should decide Light/Balanced/Heavy/Overloaded, not the snapshot alone.

## With-Customer soft warning (informational — not part of the hours estimate)

Separately, surface how many of the rep's currently With-Customer cases (`references/soql-overload.md` §5)
tend to bounce back the
same day, using their historical same-day re-flag rate. This is a heads-up, not a load number — it is
**not** added to `totalForecastHours`, since the re-flag term above already reflects this same population's
aggregate behavior over the window; adding both would double-count it.

## Banner format

Show the snapshot and the forecast as two numbers side by side, not merged into one — the rep should be
able to see at a glance how much is already sitting in front of them versus what the day tends to add:

> ⚖️ **Heavy day** — 9h snapshot / +3h forecast = 12h against an 8h day (9 flagged cases + 2 follow-ups
> due now; Tue pattern: ~2 new cases + ~1 re-flag expected before end of day).
> *3 of your 5 With-Customer cases typically re-flag the same day.*

If CFHT is unavailable for `labor_per_clear` (existing degraded mode), the same degradation applies to
the forecast — drop the re-flag half and the With-Customer line entirely, and state the forecast is
"new-case arrivals only."

## Follow-up time investment (optional add-on line)

Separate from the load estimate above — a line answering "how much of this is follow-up busywork, and
what would automating it buy back." Full methodology in `references/followup-time-investment.md` (shared with
Job
E's team rollup); it uses declared assumptions from `references/labor-assumptions.md` rather than measuring
effort
directly, since CFHT can't observe labor time. Surface it under the banner when the person asks about
follow-up time/effort specifically, or once Setup (`references/job-z-setup.md`) has been completed for them —
don't
force it into every My Day / overload read by default, since it's a heavier CFHT pull (§8,
`references/soql-followup-investment.md`) than the
snapshot banner needs.

**Note on the earlier live-tested validation:** an earlier version of this doc included worked numbers
from a live run against the reference org (Brian, a Thursday) showing the forecast term catching
~6.2h of real work that a snapshot-only read missed entirely. Those specific figures were computed under
the old BH-elapsed ongoing median and are now stale under `labor_per_clear` — the qualitative finding
(a rep starting the day empty is not the same as a rep whose day will stay empty) should still hold, but
the numbers need to be rerun. This is exactly what next week's before/after analysis is for.

