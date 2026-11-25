# E2CP Settings

The skill reads E2CP's settings and never writes them.

## Reading Settings

Settings live in the list custom setting `E2CP__casepref__c`.

- **General settings:** one record per setting. `Name` = the setting's API name, `E2CP__prefcat__c` = `general`, the value in `E2CP__prefval__c`, `E2CP__preflong__c` blank. A missing or blank value means the package default. Booleans are lowercase `true` / `false`.
- **List settings:** one record per entry. `E2CP__prefcat__c` = the setting's API name in lower case (e.g. `private_comment_domains`), with the entry in the Long Name and Value fields. Closed Widespread Issue statuses use the category `wsi_closed_status`.
- **Variation overrides:** `E2CP__prefcat__c` = `variation`, `Name` = `<Variation__c Id>:<n>`, `E2CP__Variant_Of__c` = the setting it overrides, the value in `E2CP__prefval__c`.

### When settings can't be read

When the org has **Restrict access to custom settings** enabled, a user can query `E2CP__casepref__c`, `E2CP__Variation__c`, and `E2CP__Variation_Criterion__c` only with Customize Application, View All Custom Settings, or access granted to those specific custom settings. The packaged E2CP permission sets don't grant it. Without access, Salesforce returns `INVALID_TYPE`. When that happens:

1. Infer each setting the job needs, using the signals below.
2. Show the user what was inferred and why, and confirm once.
3. Save the confirmed values in Claude's memory for this org, and use them from then on.
4. Tell the user once how to remove the guesswork: their Salesforce admin can grant read access to the E2CP custom settings above (Custom Setting Definitions access in a permission set). That is narrower than View All Custom Settings or Customize Application, which reach every setting in the org. This access only lets users read E2CP's settings, not change them, and E2CP keeps its sensitive configuration in a protected custom setting it doesn't reach. Never suggest turning off Restrict access to custom settings.

Field sets (including the New Comment Page field set) can't be read through the Salesforce MCP at all; infer them the same way.

## Settings the Skill Relies On

| Setting | What it changes | Inferred from data when unreadable |
|---|---|---|
| `ENABLE_CASE_FEED_EXTENSION` | `true` = Inbound Specific layout. Say the skill supports the Standard layout only, and stop | Case Comments created by E2CP's inbound automation user exist: Standard layout. None at all: ask the user |
| `ENABLE_HTML_SUPPORT` | Rich-text comments. Off: Canned Responses use `Comment__c`, not `Comment_HTML__c` | Rich-text comment fields are populated |
| `ENABLE_CANNED_COMMENTS` | Canned Responses on or off | Active Canned Responses exist |
| `DRAFT_COMMENTS` | Draft Comments on or off. Send Response doesn't check it, so check it before offering or saving a draft | Draft records exist |
| `EMAIL_NOTIFICATION` | Whether default recipients are pre-selected. Off: a public send emails nobody | Ask the user |
| `ENABLE_COMMENT_ONLY_MODE` | Comment Only Mode. Send Response doesn't check it; the skill must | Ask the user |
| `USE_SIGNATURE` | Salesforce appends the agent's signature. On: don't write a signature block | Ask the user |
| `PRIVATE_COMMENT_DOMAINS` (list) | Internal Domains: the only domains private replies are emailed to | No data signal. Before the first private reply that should email someone, ask the user for the list (an empty answer is valid) and save it. Don't assume it's empty |
| `IGNORE_INTERNAL_SUBDOMAINS` | Lets subdomains of Internal Domains match | Ask the user |
| `E2C_EMAIL_CASE_ORIGIN_ROUTING` (list) | Inbound Email Addresses: the support addresses customers write to. Never recipients or contacts. Each entry (category `e2c_email_case_origin_routing`) holds an address in Long Name, and a comma-separated Value that starts with an address (followed by routing details). The two addresses can differ; treat both as support addresses | Org-wide email addresses and active Email Services addresses cover most of them; no other data signal |
| `PKB_BASE_URL` | Base URL for `{$KnowledgeLinks}` (or the case's `E2CP__Knowledge_Base_URL__c`). Neither: links start with the text "null" | Ask the user |
| `PKB_ALL_LINKS` | Includes internal-only articles in `{$KnowledgeLinks}` | Ask the user |
| `NEW_COMMENT_FIELDS` | The field set shown on the New Comment Page | See below |
| `REFERENCE_TO_ORIGINAL_CASE` | Sets Parent Case on a follow-up created from a reply to a closed case | New cases whose Parent Case was already closed |
| `EXTERNAL_CONTACT_ACCOUNT` | The Default Account for auto-created contacts | The account most auto-created contacts sit in |
| `WSI_ENABLED` | Widespread Issues on or off (off by default) | Widespread Issue records exist |
| `WSI_ARCHIVE_AFTER` | Days after Closed Date before a closed Widespread Issue is archived (default 7) | Ask the user, or use the default |
| `WSI_ENABLE_ARCHIVE_SEARCH` | Lets agents find archived Widespread Issues (default on) | No data signal. Treat as on unless the user says otherwise |
| `wsi_closed_status` (list) | The Widespread Issue statuses that count as closed | Ask the user |
| `DISABLE_INLINE_IMAGE_SUPPORT` | Inverted: `false` = inline images get delivery links (default `true`) | Delivery links appear in inbound comment HTML |
| `CONTENT_DELIVERY_EXPIRATION` | Days before inline-image links expire (default 30; 0 or less = never) | Use the default |

### The New Comment Page field set

Start from the fields agents change within seconds of their own outbound comment (CaseHistory), excluding fields that automation users also change on that pattern. Only fields with history tracking show up, so confirm the list with the agent.

## Variation Presets

Variation presets can override a setting per case. Presets are `E2CP__Variation__c` records (Active, Order — lowest wins, Use_Criteria, Logic) with criteria in `E2CP__Variation_Criterion__c`. Outside the email service, only presets with Use_Criteria apply.

For a setting with overrides, evaluate the active presets' field criteria against the case; the lowest Order that matches wins. When a preset can't be evaluated, name the preset that might apply and confirm with the user.
