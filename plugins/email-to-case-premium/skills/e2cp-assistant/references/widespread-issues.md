# Widespread Issues

Only when Widespread Issues is enabled (`WSI_ENABLED`, off by default). When it isn't, the skill has no Widespread Issue behavior and doesn't mention the feature.

## Who Does What

- **Agents** report new Widespread Issues and attach cases to active ones.
- **Managers** manage Widespread Issues and broadcast updates. Broadcasting is not part of this skill.
- A new Widespread Issue is owned by the org's configured Widespread Issue Owner (a manager or a queue of managers).

## Matching a Case

While reviewing a case, compare it against:

- **Active** Widespread Issues.
- **Recently resolved** ones: closed (a status in the org's `wsi_closed_status` list) but not yet archived. A closed Widespread Issue is archived `WSI_ARCHIVE_AFTER` days (default 7) after its Closed Date.
- **Archived** ones only when "Enable Search for Archived Widespread Issues" (`WSI_ENABLE_ARCHIVE_SEARCH`) is on.

When a case matches, offer to attach it. When replying, draw on the Widespread Issue's Description and its latest public owner comment.

## Spotting an Unreported Issue

Cluster detection reuses Case Companion's similar-case search; it doesn't run a search of its own.

- A cluster must span several customers: distinct accounts, or distinct contacts in orgs that don't use accounts.
- **Default threshold:** 3+ open cases from 3+ distinct customers within 7 days.
- Scale it with the org's typical weekly case volume and customer count: a busy org needs a larger cluster, a quiet one a longer window.
- High or Urgent priority lowers the bar to 2 customers.
- A manager can set the org's own threshold. Offer to save it in Claude's memory and use it from then on.

## Reporting and Attaching

1. Show the similar cases found and get the agent's confirmation before reporting a Widespread Issue or attaching any case.
2. **Reporting a new one:** Title and Description drawn from the cases. Leave the owner to the configured Widespread Issue Owner.
3. **Attaching:** create one `E2CP__Widespread_Issue_Report__c` record per case ([KBA](https://kb.vicasso.com/?kb=000005171)). Attach this case and every similar case the agent confirms.

Use the approval checklist (SKILL.md, "Inline Interfaces") when attaching several cases.
