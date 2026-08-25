# Job A — My Day (individual)

Triggers: "what's my day look like", "my flagged cases", "what should I work on", "what's due today".
Cap each section at the top 5 with a "+N more" line.

Lead with the **overload banner** (compute per `references/job-c-overload.md` — snapshot/forecast line, plus the
With-Customer soft-warning line when applicable) and a **Start here** block, then the sections.

**Start here** — the single most urgent case the person *owns* (top of Ring 1). Show full detail and the
flag timing: account, contact, owner, status, priority, current level, exactly how overdue (or how long
until breach), the escalation timeline, the aging speed, and the Next Steps text if set.

Then five sections (all scoped to the current user, selective-scope applied, in this order):

1. **Cases I Own** — flagged cases I own, *including closed-but-flagged* (a customer replied to a closed
   case; don't ignore it). Sorted by ET4. (`references/soql-my-day.md` §2 Ring 1.)
2. **Cases I'm a Team Member On** — flagged cases where I'm on the case team but don't own it. (§2 Ring 2.)
3. **In My Queues** — flagged, unassigned cases sitting in queues I belong to; work to pick up. (§2 Ring 3.)
4. **Follow-ups due today** — unflagged cases I own whose Follow-Up On date is today; show Next Steps and
   Status. These are the "what do I pick up when my flags are clear" list. (§3.)
5. **Open Cases** — unflagged cases I own with no follow-up date, ordered by longest-since-activity, top 5.
   A scheduled follow-up means a case is *not* falling through the cracks, so those are excluded here;
   this bucket surfaces the genuinely quiet ones. Show Status. (§4.)

## Table format

For the flagged sections, merge flag level and timing into one **Flag Timing** column:

| Case | Subject | Account | Status | Flag Timing |
|---|---|---|---|---|
| [00184321](link) | Integration sync failing… | Northwind | Working | L4 · Overdue 6h 40m |
| [00184560](link) | Bulk import errors | Umbrella | Working | L3 · 48m left |
| [00184604](link) | Field history gap | Wayne Ent. | Working | L1 · Tomorrow 2:45 PM |

Flag Timing wording, measured against ET4:
- past ET4 → `L{n} · Overdue {Xh Ym}` (longest-overdue at top)
- breaching later today → `L{n} · {Xh Ym} left`
- breaching another day → `L{n} · {Tomorrow / Weekday / Mon DD} {time}`

Follow-ups and Open Cases use a Next step / Status column instead of Flag Timing.
