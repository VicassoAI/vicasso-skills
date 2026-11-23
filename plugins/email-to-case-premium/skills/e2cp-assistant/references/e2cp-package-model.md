# E2CP Package Model

The objects, fields, and behaviors the skill relies on. For the full list of packaged fields, see the [Email to Case Premium Field Reference](https://kb.vicasso.com/?kb=000004770).

## Terminology

Always say **Canned Response** in anything a person reads. "Canned Comment" is the pre-9.0 name; it survives only in the API name `E2CP__Canned_Comment__c`, which the skill uses in queries and never shows to users.

## Objects

| Object (API) | Role in the skill |
|---|---|
| `CaseComment` (`IsPublished`, `CommentBody`, `CommentBodyRichText`) | The conversation. `CommentBody` is truncated to the org's maximum comment size (default 4,000 bytes); read `CommentBodyRichText` when present |
| `EmailMessage` (+ `E2CP__Private__c`, `E2CP__Message_Id__c`) | The full inbound body, including signatures (E2CP strips signatures from comments). Don't read outbound bodies for the conversation: they repeat the thread via History Text |
| `E2CP__Case_Comment_Draft__c` | Draft Comments. `Comment_Body` stores HTML. Fields include Case, User, Comment_Body, To/CC/BCC, Public, Template, Private_Template, Comment_Only, Schedule_Comment_For, Selected_Files, Fields_Updated_1/2, Widespread_Issue, Target_Audience, From |
| `E2CP__Canned_Comment__c` (label: Canned Response) | Title (required, 100 chars), Comment_HTML (authoritative when rich text is on), Comment (plain text; read only when rich text is off), Active, Usage_Count, Last_Used_By, Last_Used_Date. Public read/write in the package; orgs may restrict it. Default files are Files linked to the response (`ContentDocumentLink`); there is no attachment field. Images embedded in the body are linked too, so they're attached as well as shown inline |
| `E2CP__Canned_Response_Category__c` (`Criteria`, `Logic_Formula`) | A category, whose criteria decide which cases can see its responses. Public read/write in the package; E2CP Managers can create them |
| `E2CP__Canned_Response_Category_Relation__c` | Links responses to categories. A response with no category relation never shows on the Lightning New Comment Page |
| `E2CP__Canned_Response_Bookmark__c` | An agent's favorite responses. No OwnerId; the agent is `CreatedById` |
| `E2CP__Widespread_Issue__c` | Title, Description, Status, Closed_Date, Affected_Case_Count, Previous_Widespread_Issue |
| `E2CP__Widespread_Issue_Report__c` | Case-to-Widespread Issue junction. Creating one attaches a case ([KBA](https://kb.vicasso.com/?kb=000005171)) |
| `E2CP__Widespread_Issue_Communication__c` | A record of each broadcast |
| `CaseArticle` | A Knowledge article attached to a case. Needed for `{$KnowledgeLinks}` |

Some orgs add local fields and objects of their own; they aren't part of the package. Detect any Intelligent Response by Flow merge fields in the body rather than relying on a flag field.

## Case Fields

- **History Text** (`E2CP__HistoryText_Inc_Private__c`, `E2CP__History_Text_Inc_Private_HTML__c`, and the public versions): the last 25 comments. Updated only by the New Comment Page and the email service, so read CaseComment for the full history. E2CP recalculates the whole history, so making a public comment private removes it. Manual edits are overwritten.
- **Most Recent Public / Private Comment**: maintained by E2CP; email templates merge them into outgoing messages.
- `E2CP__ExtraEmails__c`: every address seen on inbound emails.
- `E2CP__AdditionalTo__c`, `E2CP__AdditionalCC__c`, `E2CP__AdditionalBCC__c` (+ private versions): extra recipients agents added by hand. The skill updates these to add a recipient before sending.

## Comment Shapes

- **Inbound** — created by the E2CP email service's automation user. A leading `From:` line, plus To/CC lines when the org shows recipients on inbound comments. A private inbound email creates a private comment, except the first comment on a new case, which is always public.
- **Outbound** — created by the agent. A recipients header appears only when the org shows recipients in comments: `To:` / `CC:` lines (Lightning and Send Response) or `[Recipients: …]` (Visualforce page). BCC is never listed. With the setting off there is no header.
- **Internal note** — `IsPublished = false`, created by an agent, no email. Tell these apart from outbound by CreatedBy and IsPublished, not by the header.

Strip the header block and the trailing quoted-reply line (`On <date> <address> wrote…`) before summarizing or comparing text.

## E2CP Send Response

The invocable action `E2CP.InvocableSend.send`, called through the Salesforce MCP as the signed-in user.

| Parameter | Notes |
|---|---|
| `caseId` | Required |
| `isPublic` | Required. Missing throws an error |
| `body` | HTML. Mutually exclusive with `cannedResponseId` |
| `cannedResponseId` | Sends a Canned Response as-is, attaches every File linked to it, and logs a use. Runs an Intelligent Response's Flow |
| `templateId` | Leave empty: E2CP picks the org's default public or private template by the same rules as the New Comment Page |
| `fileAttachments` | ContentDocument Ids to attach. The files don't need to be on the case first |
| `commentOnly` | Adds the comment without sending email |
| `createDraft` | Saves a Draft Comment instead of sending. Does not return the draft's Id |
| `scheduledSendAt` | Scheduled send |

- It throws (failing the call) for: missing `isPublic`, both or neither of `body` and `cannedResponseId`, a wrong Id prefix, a case not found, or two requests for the same case in one call.
- It handles rich text well. Pass HTML as-is.
- With `cannedResponseId` it updates the response's Usage Count, Last Used By, and Last Used Date — for sends and drafts alike, including automated sends.
- It has **no recipient parameter** and **no field-update parameter**.
- It does **not** check Comment Only Mode, whether Draft Comments are enabled, or whether Scheduled Send is enabled.
- With `USE_SIGNATURE` on, Salesforce appends the sending user's signature to the email.
- Saving a draft does not update the Case, so Case automation doesn't fire on a draft.

### Recipients

- **Public:** the New Comment Page's pre-selected defaults — the Case Contact (or Lead) and the Additional To / CC / BCC addresses when `EMAIL_NOTIFICATION` is on, plus Case Team Members when team members are enabled. With `EMAIL_NOTIFICATION` off it emails nobody and only adds the comment.
- **Private:** only the private Additional To / CC / BCC addresses whose domain is in Internal Domains (`PRIVATE_COMMENT_DOMAINS`). Others are dropped silently. With Internal Domains empty, a private reply emails nobody.
- Exclude List, routing, org-wide, and Inbound Email Addresses (`E2C_EMAIL_CASE_ORIGIN_ROUTING`) entries are always removed, so E2CP never emails itself.

### Order with Case automation

The New Comment Page inserts the comment, updates the Case, then sends ([order of execution](https://kb.vicasso.com/?kb=000004820)). The org's own Case automation runs after each step. The skill updates the Case fields first, then calls Send Response.

## Drafts

- A case can hold several drafts from different users. Agents can open a colleague's draft on the New Comment Page or Timeline, and editing it updates the original in place.
- The User field holds the user who created the draft; a draft with no User shows its creator as the author.
- **Recipients:** To / CC / BCC hold semicolon-separated entries, each one `case_contact`, `case_lead`, a CaseTeamMember Id (`0B6…`), or a plain email address.
- **Files:** a draft created through Send Response keeps its files (a Canned Response's default files, or `fileAttachments`) and preselects them when opened, except files already attached to the case, which load unselected. Inserting a response on the New Comment Page behaves the same way.
- Create drafts through Send Response (`createDraft = true`), never by inserting `E2CP__Case_Comment_Draft__c` directly. Query for the new draft right after the call (this case, this user as User, created since the call).
- `E2CP__Fields_Updated_1__c` holds the Case field changes saved with a draft, as JSON. They load on the New Comment Page with the draft:

  ```json
  {"case":{"Subject":{"oldValue":"Printer jam","newValue":"Printer jam - resolved"},"Status":{"oldValue":"New","newValue":"Working"}}}
  ```

  `E2CP__Fields_Updated_2__c` is used only for overflow past 131,072 characters. A change loads only when the field is in the New Comment Page field set, the user can edit it, the key matches the field's API name exactly (including case), and `oldValue` equals the Case's current value. `OwnerId` needs an object with `value`, `label` and `icon` rather than an Id.

## Files

- Inbound email files are Files (ContentDocument) linked to both the EmailMessage and the Case.
- For **inline images only**, E2CP's automation user creates a Content Delivery and writes its download URL (`/sfc/dist/version/download/…`) into the comment HTML. The image downloads from that URL with no login.
- These links exist only when inline images are on (`DISABLE_INLINE_IMAGE_SUPPORT = false`; the setting is inverted and defaults to off). Otherwise the image reference is replaced by the file name.
- Links expire after `CONTENT_DELIVERY_EXPIRATION` days (default 30; 0 or less means never) and are never renewed. Expired links are common on older cases.
- Attachments (PDFs, logs, `.eml`) never get a delivery link.
- The Salesforce MCP can't return file bytes: `VersionData` comes back as a REST path. Ask the agent to attach anything without a live delivery link.

## Other Package Behavior

- **Auto-created contacts** have the Description "Automatically created by Email to Case Premium" and usually sit in the Default Account (`EXTERNAL_CONTACT_ACCOUNT`). Internal To/CC addresses get contacts too unless they're on the Exclude List. A sender address with capital letters can produce a contact that isn't linked to the case.
- **Email Loop Protection** prefixes the Subject of a flagged new case with `[Email Loop Protection]`.
- **Reference to Original Case** (`REFERENCE_TO_ORIGINAL_CASE`) can set Parent Case on a new case created from a reply to an old closed case. Those are follow-ups, not child cases.
