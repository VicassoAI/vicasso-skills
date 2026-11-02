# Canned Response Library (Managers)

Three ways in: "what are we retyping?", "set up our library", and "review our library". All three share the rules below.

## What Belongs in a Canned Response

A Canned Response is routine text that would read the same whatever the customer's technical problem: follow-ups, access requests, closing notices. Problem-specific text is troubleshooting content for Knowledge; mention it in a line and move on.

## "What Are We Retyping?"

Mine closed cases for replies agents keep writing by hand.

- **Window:** closed cases from the last 90 days by default. If that's too few to show a pattern, extend up to 12 months and say so. The manager can name a different window.
- Sample across the whole window, and state how many comments and cases were read and over what period.
- **A pattern is worth authoring** when it recurs across different cases, more than one agent writes it, and it would be reused roughly as-is.
- Rank candidates by frequency × length. Propose a handful at most, each with its case and agent counts and one real example.
- **Look at files too.** When agents keep attaching the same file alongside the same reply (the same ContentDocument, or copies with the same `ContentVersion.Checksum`), propose the response with that file as a default file.

### Check the library first

Compare by purpose, not wording: what each existing response (active and inactive) is for.

- If one already covers the pattern, name it and stop.
- If agents have stopped using it and retype their own version, propose updating that response with the team's wording (it keeps its Id and usage history) instead of creating a new one.

Usage Count and Last Used Date count every send, including the skill's and automated ones (such as Flows calling Send Response), so they measure volume, not agent preference.

## "Set Up Our Library"

Sources, converted directly by the skill:

- **Quick Text** — convert merge syntax, categories, and category relations. Converting isn't only a syntax mapping: check whether each snippet was written for chat (greetings, "today", "I've opened a case") and won't read as an email, and run the review checks below (old names, dead domains, placeholders) on import.
- **Email templates with built-in text** — often an org's main source of reply content, since many teams send templates as the message itself. Sort them by purpose first:
  - reply content → convert
  - E2CP container templates that merge the comment → skip
  - automation notifications, billing, sales sequences, Salesforce samples → list by type and skip
  - Visualforce templates → skip

  A template's attachments that are Files (ContentDocument) carry over as default files. Attachments stored as legacy Attachment records can't be linked; list them and ask the manager to add each file to the new response.
- **Pasted text** from documents or text-expander tools.
- **Sales content** (Quick Text or templates that merge on Lead): service teams are sometimes asked to send it, so list it as possible content and include it only if the manager confirms. Merge fields that don't resolve on a Case (e.g. Lead fields) must be remapped or removed before converting.
- **Mined closed cases** fill whatever the other sources don't cover. When an org has little usable Quick Text or template content, mining becomes the main source and this works like "what are we retyping?".

When a converted item and a mined pattern cover the same need, keep the wording agents use today.

## Creating a Response

- Title ≤ 100 characters.
- Body in `E2CP__Comment_HTML__c` (`E2CP__Comment__c` when the org has rich text off).
- `E2CP__Active__c = true`.
- At least one category: an existing one, or a new one the manager approves. A response with no category never shows on the Lightning New Comment Page. E2CP Managers can create categories.
- Validate every merge field against the schema.
- Where an Intelligent Response would help, say so; building the Flow is admin work.

### Default files

A response can carry default files that go out every time it's used: Files linked to the response record. There is no attachment field.

- **Existing files:** after creating the response, link each file to it with a `ContentDocumentLink` (the response's Id as `LinkedEntityId`). The manager confirms each file first. Linking needs edit access to the response and access to the file.
- **New files:** the skill doesn't upload them. Ask the manager to add the file in the response's Files related list.
- **Embedded images are attached too.** Every image embedded in the body is also linked to the response, so the customer gets it inline and as an attachment. When a new response embeds images, tell the manager.
- Only link files meant for every customer who gets this response. A file for one customer belongs on that case, not on the response.

## "Review Our Library"

### Order

1. **Most-used responses first** — a handful typically carries most of the volume. Fix errors there first: merge fields that don't resolve, broken links, wrong names or facts, and default files that don't match the text (the body says "attached" but no file is linked, or a linked file the body never mentions). Offer wording or tone improvements to heavily used responses only as suggestions, and say that agents know them as they are.
2. **Then the rest of the library:**
   - **Invisible to agents** — responses with no category (they never show on the Lightning New Comment Page), and responses only in categories whose criteria no case can match. For an uncategorized response, propose a category for it.
   - **Dormant** — no use in months, by Last Used Date.
   - **True near-duplicates** — bodies that say the same thing. Intentional variants, such as one per product or audience, aren't duplicates; don't call them out.
3. **Rare, low priority:** content or default files tied to a version, date, or retired name (e.g. "error in version 9.43").

### Judgment calls

- A link the skill can't open is "couldn't verify", not broken.
- Before calling out a placeholder (e.g. "[edit link]"), check recent sent replies. If agents replace it, it isn't an error.
- A response's creator having left the team isn't a reason to retire it.

### Fixing and retiring

- After a response is fixed, deactivate the ones that shouldn't be used anymore, with the manager's confirmation. **Deactivate, never delete** — it preserves usage stats.
- Use the approval checklist (SKILL.md, "Inline Interfaces") for batches.

## Edit Access

Canned Responses and Categories are public read/write in the package, but orgs can restrict that. Before editing a response the user didn't create, check their actual edit access to that record. Where they can't edit it, explain the problem and name who created the response.
