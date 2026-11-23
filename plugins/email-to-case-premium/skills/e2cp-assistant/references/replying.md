# Replying ("Help Me Reply")

The full mechanics behind Case Companion's "help me reply". SKILL.md covers the flow; this file covers every rule that decides what an option contains and how it is sent or saved.

## Canned Responses

Skip this section when Canned Responses are turned off (`ENABLE_CANNED_COMMENTS`).

### Which responses the agent can see

Suggest only responses the agent can see on the New Comment Page:

- `E2CP__Active__c = true`, and
- it's in at least one **category whose criteria match the case**. A category with no criteria matches every case. A response with **no category never shows** on the Lightning New Comment Page, so never suggest one.

Category criteria (`E2CP__Criteria__c`) are a JSON array of `{field, operator, value}`:

- `=` is the only operator. If any other operator appears, exclude that category's responses and name the category.
- Newline-separated values mean match-any.
- `E2CP__Logic_Formula__c` combines conditions by 1-based position.

### Which response to suggest

- Rank by how well the response's content fits what this reply needs to say. Break ties with the agent's bookmarks, then Usage Count.
- Suggest a response only when it says what this reply needs to say. Small edits are fine (a name, a date, one case-specific sentence); one that would need rewriting doesn't qualify. Never suggest one just to fill an option.
- When none qualifies, write fresh and say so in one line: "No Canned Response fits this reply." When the fresh reply looks routine, add one line: if the agent finds themselves writing this often, ask their manager to create a Canned Response for it.
- **Intelligent Responses** (responses with Flow merge fields) can go out directly: Send Response runs their Flow when given the `cannedResponseId`.

### Merge fields

Resolve merge fields against the case when showing an option. Syntax:

| Merge field | Resolves to |
|---|---|
| `{Subject}` | A Case field |
| `{Contact.FirstName}` | A field on a related record |
| `{$CurrentUser.FirstName}` | The sending user |
| `{$KnowledgeLinks}` / `{$KnowledgeLinksExternal}` | Links to Knowledge articles attached to the case |

An unresolved merge field renders literally in the customer's email. Leave unresolved fields visible in the option and call them out.

### Counting a use

The New Comment Page counts a use when a response is **inserted** (Usage Count +1, Last Used By, Last Used Date; nothing else), not when it's sent. Loading a draft doesn't count again. Match that:

- **One trigger.** A use counts when the skill sends or saves a draft built on a Canned Response. Options Claude only shows don't count, and neither does text handed over in chat for the agent to paste.
- **Once per response per reply.** A reply combining two responses counts each once.
- **Unedited:** send or draft through Send Response with its `cannedResponseId`, which logs the use.
- **Edited or combined:** Send Response can't take both `body` and `cannedResponseId`, so send or save the text, then update the three usage fields on each response used. If the agent can't edit those fields, skip it and say so in one line.
- Sending a draft later never logs the use again.

### Default files

A Canned Response can carry default files: Files linked to the response record (`ContentDocumentLink`). Images embedded in the response body are linked the same way, so they count too.

- **Show them.** An option built on a response lists every file linked to it. When the body embeds images, say they will also go out as attachments, so the customer gets them twice (inline and attached).
- **Unedited:** sending or drafting with `cannedResponseId` attaches every linked file. Nothing else to do.
- **Edited or combined:** sending or drafting with `body` attaches nothing on its own. Pass the ContentDocument Ids of each used response's linked files in `fileAttachments`. They don't need to be on the case first. The agent can drop any file (an embedded image, for instance) at the final confirmation.
- **Dropping a file from an unedited response:** `cannedResponseId` always attaches every linked file. If the agent wants one left off, send the response's text as `body` with the remaining files in `fileAttachments`, and treat it as edited for usage counting.
- **Drafts:** a draft keeps its files and preselects them when the agent opens it, whether it was created with `cannedResponseId` or with `body` and `fileAttachments`. The exception is files already attached to the case, which load unselected (the New Comment Page does the same). Name those files so the agent can select them.

## Knowledge

- Search Knowledge articles and pull the content the reply needs. Body fields vary by org; discover them before selecting (see `soql-gotchas.md`). When it's unclear which article fields to use, ask the agent.
- Orgs without Knowledge are normal. Don't mention the absence.
- After a reply uses an article, attach it to the case (`CaseArticle`). Send Response doesn't, and `{$KnowledgeLinks}` lists only attached articles.
- Before using a Canned Response with `{$KnowledgeLinks}`, check the org has a knowledge base URL (`PKB_BASE_URL`, or the case's `Knowledge_Base_URL__c`). Without one the links start with the text "null": leave the response out and say why.
- `{$KnowledgeLinks}` lists only English, online articles attached to the case. Internal-only articles are skipped unless `PKB_ALL_LINKS` is on — and when it is, check the expanded links in the audience gate.

## Proposed Case Field Updates

Data quality is part of every reply, as on the New Comment Page. Each option comes with proposed Case field updates, drawn only from the org's New Comment Page field set (see `settings.md`), of two kinds:

- **Working the case** — fields that should change because of what the reply says or does (asking the customer for information → Status = Waiting on Customer; a promised follow-up → next step and follow-up date).
- **Categorization** — fields that describe the case (Reason, Type, product) that are empty or no longer match what the thread shows. Categories drift as a case evolves, so an existing value may be corrected; show old → new with the evidence.

Rules:

- Use only valid picklist values, read from the schema. Never invent one.
- When a reply closes the case, call out any categorization field in the field set that's still empty.
- Propose an update only when the thread supports it. The agent confirms before anything changes.

## Before Sending or Saving

Run these checks every time, in this order.

1. **Drafts on the case.** Only when Draft Comments are on (`DRAFT_COMMENTS`); when they're off, never offer or save a draft, since Send Response would create one the agent can't see. Query every draft on the case. If this agent already has one, don't create another or edit theirs; offer the text in chat for them to paste into their draft. A colleague's draft is worth mentioning.
2. **Comment Only Mode.** If `ENABLE_COMMENT_ONLY_MODE` applies to this case (including through a variation preset), post with `commentOnly = true` and send no email, as the New Comment Page would. Send Response doesn't check it.
3. **Recipients.**
   - Public: Send Response emails only the case's default recipients (Case Contact or Lead, Additional To / CC / BCC, and Case Team Members when team members are enabled), and nobody when `EMAIL_NOTIFICATION` is off. With no recipients it only adds the comment: tell the agent, and offer a draft instead when Draft Comments are on.
   - **Support addresses are never recipients.** Every inbound email lists the support address the customer wrote to (e.g. support@yourcompany.com). E2CP already threads the reply, and Send Response drops support addresses itself so E2CP never emails itself. Keep them out of the Additional fields anyway, so the recipients the agent confirms match who actually gets the email. An address is a support address when it matches an org-wide email address (`OrgWideEmailAddress.Address`), an active Email Services address (`EmailServicesAddress`, `LocalPart@EmailDomainName`), or an entry in E2CP's Inbound Email Addresses (`E2C_EMAIL_CASE_ORIGIN_ROUTING`) when settings are readable. Never propose adding one, and remove any found in the Additional To / CC / BCC fields before sending, with the agent's confirmation.
   - Adding someone: Send Response has no recipient parameter. With the agent's confirmation, update the Case's Additional To / CC / BCC fields (or add a Case Team Member) first, then send.
   - Private: only the private Additional To / CC / BCC addresses whose domain is in Internal Domains (`PRIVATE_COMMENT_DOMAINS`) are emailed; E2CP silently drops the rest. Check that Internal Domains is populated and that each intended recipient's domain is on it. When settings can't be read and the list isn't in memory yet, ask the user for it (see `settings.md`); don't assume it's empty. When the list is empty, nobody gets the email: tell the agent before posting. To add an internal person, use the private Additional fields.
4. **Audience gate** (SKILL.md, "Audience"). Scan the final HTML. Stop on any internal link or record Id.
5. **Final confirmation.** Show the final text, public or private, the recipients, the files that will be attached, and the field updates. Also list every other write that comes with it: changes to the Case's Additional To / CC / BCC fields or Case Team, the Knowledge article to attach to the case, and the usage update on each edited or combined Canned Response. Wait for the agent.

## Sending

1. Update the confirmed Case fields first (Send Response has no field-update parameter).
2. Call Send Response without a `templateId`; E2CP picks the org's default public or private template.
   - Pass `body` (HTML as-is) or `cannedResponseId` — never both.
   - To send files, pass their ContentDocument Ids in `fileAttachments`: files already on the case, or a Canned Response's default files when its text was edited (see "Default files"). The skill doesn't upload new files.
3. If a Knowledge article was used, attach it to the case.
4. If an edited or combined Canned Response was used, update its usage fields.

## Saving a Draft

1. Call Send Response with `createDraft = true` and `body` or `cannedResponseId`. With `body` built on a Canned Response, also pass its default files in `fileAttachments` (see "Default files"). Never insert the draft record directly, even when Send Response is unavailable: a draft inserted by hand can miss what E2CP sets when it saves one, and its recipients may not load as the agent expects. Offer the text in chat instead.
2. Send Response doesn't return the draft's Id. Query for it right after the call: this case, this agent as User, created since the call.
3. **Check the draft's recipients.** Its To / CC / BCC fields hold semicolon-separated entries, each one `case_contact`, `case_lead`, a CaseTeamMember Id (`0B6…`), or a plain email address. Compare them with the recipients the agent confirmed. If anyone is missing, name them so the agent can add them on the New Comment Page; don't edit the draft's recipient fields.
4. Write the confirmed field changes into the draft's `E2CP__Fields_Updated_1__c` (not the Case), so they load on the New Comment Page with the draft:

   ```json
   {"case":{"Status":{"oldValue":"New","newValue":"Working"}}}
   ```

   `E2CP__Fields_Updated_2__c` is only for overflow past 131,072 characters.

   The New Comment Page loads a change only when all of these hold; otherwise it silently drops it:
   - The field is in the page's field set and the agent can edit it. The key must match the field's API name exactly, including case.
   - `oldValue` equals the Case's current value. Read the Case right before writing, and use what it holds now.

   Field sets can't be read through the Salesforce MCP. When you aren't sure a field is on the page, or for a change to the Owner (it needs a format the skill doesn't build), leave it out and tell the agent to set it on the New Comment Page.
5. If the draft carries files already attached to the case, name them: they load unselected.
6. The agent edits and sends the draft from the New Comment Page.
