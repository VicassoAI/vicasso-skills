# Timeline Updates

On request, gather what changed from a source the agent names, reduce it to what the case owner needs to act on next, and add one Timeline update to the case.

## Sources

The agent names the source; the skill defines the format, privacy, and when to add one.

- **This case** — reuse Case Companion's catch-up.
- **Child cases.**
- **Related Salesforce records** — calls, tasks, and similar.
- **Any system the agent's Claude is connected to** — an issue tracker, shipping, logs.

A recurring routine is a Claude scheduled task (a Claude feature, not a Salesforce Task) that calls this skill.

## What a Timeline Update Is

A **comment-only Case Comment** (Send Response with `commentOnly = true`), never a Salesforce Note. It has no recipients.

## Format

- **First line, always:** a fixed line identifying it as added by Claude, with the date and sources, e.g.

  `Update from Claude · Oct 1, 2026 · Sources: child cases`

  The skill finds its own previous Timeline update by this line, and people can tell at a glance that Claude added it.
- **Summary updates stay under 500 words.** The limit doesn't apply when the agent asks for specific hand-crafted content.
- **Last line, always:** what the owner needs to do next, or what the case is waiting on.

## Privacy

- **Private by default.** Private updates may keep internal links; they help internal readers.
- A **public** update goes into the public History Text and Most Recent Public Comment, which email templates merge into the next message to the customer. If the agent switches an update to public, run the audience gate (SKILL.md) before adding it.

## When to Add One

- At most one Timeline update per case per run.
- Only when something has changed since the last one. Find the last one by its first line.

## Child Cases

- For each child that changed since the last Timeline update: status, owner or team, what changed, and what it's waiting on.
- Children with no change get one line.
- E2CP's Reference to Original Case setting can set Parent Case on a new case created from a reply to an old closed case. Tell those follow-up cases apart from true child cases, and don't list them as work in progress.

## Side Effects

Every Timeline update is a Case Comment. It updates E2CP's comment fields on the Case, and the org's own Case automation runs after each step ([order of execution](https://kb.vicasso.com/?kb=000004820)). When the agent sets up a recurring routine, tell them that Timeline updates can set off their org's automation.

If Case Flags is installed, a Timeline update may clear the case's flag (see SKILL.md, "Interactions with Other Products").
