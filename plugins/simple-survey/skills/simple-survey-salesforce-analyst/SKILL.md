---
name: simple-survey-salesforce-analyst
compatibility: Requires a connected Salesforce MCP server with read access to the Simple Survey managed package (simplesurvey__).
description: Understand and analyze Simple Survey data stored in Salesforce. Use this skill whenever someone asks questions about survey responses, NPS scores, CSAT, CES, team or agent feedback, customer sentiment, account sentiment, product feedback trends, or coaching and review preparation — even if they do not explicitly mention Simple Survey. Triggers include requests to summarize feedback for a team, assess how an agent is doing, prepare for a quarterly review, find out what customers think about a product or service, or identify trends in survey data. Always use this skill when the Salesforce MCP is in play and the question involves survey responses or scores.
---

# Simple Survey Salesforce Analyst

Simple Survey is a managed package by Vicasso that sends customer feedback surveys — NPS, CSAT, CES, Likert, Thumbs Up/Down, Medical Pain, and Questionnaire — and stores each response as a record directly in Salesforce. This skill gives you the data model, field semantics, and analysis patterns to answer questions about survey data correctly.

---

## The Core Object

Every survey sent to a customer produces one record on the **Survey object**: `simplesurvey__Survey__c`.

Each record captures who was surveyed, what they were surveyed about, how they responded, and which agent or team member the survey is attributed to.

---

## Key Fields

### Status & Identification

| Field Label | API Name | Notes |
|---|---|---|
| Status | `simplesurvey__Status__c` | Lifecycle stage — see Status section below |
| Survey Type | `simplesurvey__Survey_Type__c` | Scale type (NPS, CSAT, CES, etc.) |
| Rating Scale | `simplesurvey__Rating_Scale__c` | Numeric range in use: `1-5` or `0-10` |
| Test Survey | `simplesurvey__Is_Test_Survey__c` | Boolean — always exclude these from analysis |
| Last Response At | `simplesurvey__Last_Response_At__c` | When the respondent last interacted with the survey |
| Survey Send Date | `simplesurvey__Survey_Send_Date__c` | When the survey email was sent |

### Scores & Responses

| Field Label | API Name | Notes |
|---|---|---|
| Survey Score | `simplesurvey__Survey_Score__c` | The initial rating selected (numeric) |
| Net Promoter System | `simplesurvey__Net_Promoter_System__c` | Auto-set for NPS: `Detractor`, `Passive`, or `Promoter` |
| NPS Factor | `simplesurvey__NPS_Factor__c` | Auto-set for NPS: `-1`, `0`, or `1` — used for score calculation |
| Human Confidence Score | `simplesurvey__Human_Confidence_Score__c` | reCAPTCHA-based bot detection score — see Bot Detection section below |
| Survey Comments | `simplesurvey__Survey_Comments__c` | Standard packaged free-text question field |
| Snapshot | `simplesurvey__Snapshot__c` | Rich text (HTML) of the full survey — all questions and answers |

### Relationships & Lookups

The fields below are the standard, always-present lookups shipped with the package.

| Field Label | API Name | Notes |
|---|---|---|
| Case | `simplesurvey__Case__c` | Related Case lookup — populated only if the survey program is configured with Case as its related object |
| Contact | `simplesurvey__Contact__c` | Related Contact lookup |
| Account | `simplesurvey__Account__c` | Related Account lookup |
| Record Owner | `simplesurvey__Record_Owner__c` | Lookup to the User who owned the related record (the agent) |
| Owner | `OwnerId` | Salesforce record owner — typically the agent's manager |

**Don't assume Case.** When someone builds a survey program in Simple Survey, they choose a **related object** for that program — Case is the most common choice, but it can just as easily be Opportunity, Lead, or most standard and custom objects. The related-object lookup field only gets populated for programs configured that way; a survey program built on Opportunity will have `simplesurvey__Case__c` null and will instead have an Opportunity lookup (standard or custom, depending on how the program was set up).

Survey programs can also be configured to **map additional fields from the related object** onto the survey record itself (e.g., pulling a Product field from the related Case, or a Stage field from a related Opportunity). These mapped fields are org-specific and won't appear in this reference.

**Before assuming Case is the related object:**
- Check the org's schema for the survey object (e.g., via `getObjectSchema`) to see which relationship/lookup fields actually exist and are populated
- Check the relevant Survey Configuration record's `simplesurvey__Survey_Object__c` field (see below) — it states the related object directly
- If unsure, ask the user which object their survey program is built on, or check `RecordType.DeveloperName` / `Name` for a hint at the program's configuration
- If Case-related fields come back null, look for other populated lookups before concluding no related-object data exists

---

## Survey Configuration Object

Each survey **program** (what a user means by "our Case NPS survey" or "the CES program") is defined by a **Survey Configuration** record: `simplesurvey__Survey_Configuration__c`. This object drives setup — which object it's built on, whether it's active, and whether survey records are pre-created automatically — and is the right place to look when someone asks why a program isn't behaving as expected.

### Key Fields

| Field Label | API Name | Notes |
|---|---|---|
| Inactive | `simplesurvey__Inactive__c` | Boolean. `true` means the program is currently inactive — check this first if new survey records aren't being created or populated at all for a program |
| Survey Object | `simplesurvey__Survey_Object__c` | **Plain text field**, not a lookup — stores the API name of the related object (e.g., `Case`, `Opportunity`, `Contact`, `Lead`, `Campaign`) that the program is built on |
| Auto Create Survey Records Enabled | `simplesurvey__Auto_Create_Surveys_Enabled__c` | Boolean — whether Simple Survey pre-creates survey records automatically ahead of sending |
| Auto Create Survey Records Criteria | `simplesurvey__Auto_Create_Surveys_Criteria__c` | Long text — the record-level criteria that determines which related records get a survey pre-created. Read this as configuration text (it's not meant to be parsed as SOQL); useful when someone asks "why didn't a survey get created for this record?" |
| Record Type | `simplesurvey__Record_Type__c` | Stores a Record Type reference as text — can help narrow down which Configuration record corresponds to a given program alongside `Survey_Object__c` |

### Matching a Configuration Record to a Survey Program

**There is no direct lookup between a Survey record (`simplesurvey__Survey__c`) and its Survey Configuration record.** You can't join them in a query. To figure out which Configuration record governs a given survey program:

1. Use `simplesurvey__Survey_Object__c` on the Configuration object as a first filter — narrow to Configuration records built on the same object as the surveys in question (e.g., if the surveys have `simplesurvey__Case__c` populated, look at Configurations where `Survey_Object__c = 'Case'`)
2. Cross-reference `simplesurvey__Record_Type__c` on the Configuration against the survey records' Record Type where possible, and use the Configuration `Name` as a secondary signal
3. **Confirm with the user** which Configuration record matches — Name and Record Type conventions vary by org, and this is a best-effort narrowing, not a guaranteed match

### Diagnosing "Why Wasn't a Survey Created / Sent?"

When someone asks why a survey record doesn't exist for a record they expected one for, check the relevant Configuration record in this order:
1. **`simplesurvey__Inactive__c = true`** — the whole program is off; nothing will be created or sent
2. **`simplesurvey__Auto_Create_Surveys_Enabled__c`** — if the org relies on pre-created survey records and this is `false`, that pre-creation path won't fire (surveys may still be created through other automation, like a Flow, so absence of this alone isn't conclusive)
3. **`simplesurvey__Auto_Create_Surveys_Criteria__c`** — if enabled, read this criteria text to see whether the specific record in question would have matched it

### Open Question — Related-Object Lookup for Non-Standard Objects

The standard lookups on the Survey object (`simplesurvey__Case__c`, `simplesurvey__Contact__c`, `simplesurvey__Account__c`) don't cover every object a program can be built on — for example, this org has Opportunity-based Configurations, but the Survey object has no dedicated Opportunity lookup field. There's a generic `simplesurvey__Embed_Related_Record_Id__c` text field on the Survey object that could be how non-standard related records are referenced, but **this is unconfirmed** — verify with the user or R&D before relying on it for analysis.

---

## Survey Status — What Each Value Means

The `simplesurvey__Status__c` field tracks the full lifecycle of a survey record.

| Status | Meaning | Has Response Data? |
|---|---|---|
| New | Created; external automation will send it | No |
| Pending | Created but not yet sent | No |
| Sent | Sent via Simple Survey's packaged Flow | No |
| Not Sent | No valid email or inactive user | No |
| Fatigued | Hit the survey fatigue threshold; not sent | No |
| Expired | Survey program expired before sending | No |
| Bounced | Email bounced; system retries at 24h and 48h | No |
| **Responded** | Respondent clicked the score link in the email | Score only |
| **Partial** | Respondent started the landing page but didn't submit | Score + partial answers; Snapshot notes skipped questions |
| **Completed** | Respondent submitted the full survey | Full response |

**For analysis:** Filter to `Status IN ('Responded', 'Partial', 'Completed')` for any records with data. Use `Completed` only if full responses are required.

**Always add:** `simplesurvey__Is_Test_Survey__c = false` to exclude test records from every analysis query. Also see Bot Detection below for a second exclusion filter to apply alongside this one.

---

## Bot Detection & Data Quality (Human Confidence Score)

Simple Survey has an optional reCAPTCHA-based bot prevention feature. When enabled, every survey response gets a `simplesurvey__Human_Confidence_Score__c` value.

### Interpreting the Score

| Range | Meaning |
|---|---|
| Closer to 1 | High confidence the respondent is human |
| Closer to 0 | Likely an email scanner or bot |
| Negative | reCAPTCHA verification did not complete — a connection error or invalid Site/Secret Key configuration, **not** a bot signal |

Common negative error codes:

| Value | Meaning |
|---|---|
| -3.0 | Failed to load the reCAPTCHA JavaScript API in time |
| -3.1 | Connection timeout retrieving the reCAPTCHA token |
| -3.2 | Connection timeout verifying the reCAPTCHA token |
| -4.0 | General verification error — usually Google not configured as a Remote Site in Salesforce; if not, this needs a Vicasso Support case |

### Why Some Bot Records Still Show Up

Simple Survey blocks survey record creation when the Human Confidence Score falls under the bot threshold at submission time, so most bot and duplicate/empty-survey noise never becomes a record at all. Records with a score of exactly `0` that still exist are the ones that slipped through (e.g., threshold set to allow them, or scored right at the boundary) — treat these as likely bot-created. They will typically sit in **Responded** status, since a bot will trigger the score link but won't complete a landing page.

### How to Handle This in Analysis

- **Score = 0 (likely bot):** Exclude from analysis the same way you exclude `simplesurvey__Is_Test_Survey__c = true` records — but call out the count/presence of excluded bot-suspect records when reporting results, so the user knows data was filtered.
- **Negative scores (connection/config errors):** Treat as a separate data-quality issue, not a bot signal. Exclude them from score analysis too (an unverifiable record shouldn't count either way), but report them separately from the bot-suspect count — e.g., "N records excluded as likely bots (score = 0), M records excluded due to reCAPTCHA verification errors (negative score)." If the negative-score count is notable, flag it as a possible configuration problem worth raising with an admin, rather than a data-quality issue with the survey responses themselves.
- **Score close to but not exactly 0, or between 0 and 1:** Treat as human unless the user indicates their org's bot threshold is set higher than 0 — ask if unsure.

---

## Rating Scales & Score Interpretation

The `simplesurvey__Survey_Type__c` field determines how to interpret `simplesurvey__Survey_Score__c`. Always read scores in the context of survey type — the same number can mean very different things across scales.

### Net Promoter Score (NPS) — Scale: 0–10

The most common survey type. The score represents how likely the respondent is to recommend.

| Score | Classification | NPS Factor |
|---|---|---|
| 0–6 | Detractor | -1 |
| 7–8 | Passive | 0 |
| 9–10 | Promoter | +1 |

The `simplesurvey__Net_Promoter_System__c` and `simplesurvey__NPS_Factor__c` fields are auto-populated by the package for NPS records.

**To calculate NPS:** `AVG(simplesurvey__NPS_Factor__c) × 100` — produces a value between -100 and +100. Above 0 means more Promoters than Detractors. Industry benchmarks vary; 50+ is generally considered excellent.

### Customer Satisfaction Score (CSAT) — Scale: 1–5

Higher is better. Scores of 4 or 5 are typically considered "satisfied." Average CSAT across a team or time period is the standard metric.

### Customer Effort Score (CES) — Scale: typically 1–5 or 1–7

**Higher is better — Simple Survey does not reverse the direction.** CES measures how easy it was for the customer to resolve their issue, and the scale is aligned so "Very Easy" is the top score (e.g., 5) and "Very Difficult" is the bottom score (e.g., 1). This keeps the desirable outcome as the high score and the undesirable outcome as the low score, consistent with CSAT — a high CES is a good experience, a low CES is a bad one.

### Thumbs Up / Down

Binary response stored as a number: `1` = Thumbs Up, `0` = Thumbs Down. No averaging is meaningful; report as a count or percentage of positive responses (score = 1).

### Likert Scale — 3, 4, 5, 6, or 7 points

Agreement or satisfaction scales. Higher values = more positive. The number of points is configured per survey program — check the program setup if the scale range is unclear.

### Medical Pain Scale — Scale: 0–10

**Higher means more pain — this is inverted relative to satisfaction scales.** A score of 8 is a bad outcome (significant pain), not a good one.

### Wong-Baker Scale — Scale: 0–10

A visual variant of the Medical Pain Scale that uses illustrated faces to represent pain levels. Interpretation is identical: higher = more pain. Treat the same as Medical Pain Scale for analysis purposes.

### Questionnaire — No Score

The initial question is open-ended, not a rating. `simplesurvey__Survey_Score__c` will be null. Analysis should rely entirely on `simplesurvey__Survey_Comments__c` and the Snapshot field.

---

## Ownership & Visibility

Simple Survey uses a deliberate two-level ownership model.

| Field | Who It Is | Query Pattern |
|---|---|---|
| `simplesurvey__Record_Owner__c` | The user who owned the related record (e.g., the support agent who closed the case, or the rep who owned the opportunity) | Use to find surveys attributed to a specific **agent** |
| `OwnerId` (Owner) | Typically the Record Owner's **manager** | Gives the manager access to their team's records in Salesforce |

**Key rules:**
- To find surveys for a specific agent: `simplesurvey__Record_Owner__r.Name = 'First Last'`
- The manager (Salesforce Owner) can see all their team's survey records because they hold record ownership
- Record Owner is set at survey creation time and typically reflects who owned the related record (Case, Opportunity, or whatever object the program is built on) at the time the survey was triggered

---

## Response Rate

Response rate measures the percentage of delivered surveys that received a response. It is a useful health metric for a survey program — low response rates may indicate email deliverability issues, survey fatigue, or a poorly timed send.

### The Formula

**Response Rate = (Responded + Partial + Completed) ÷ (Sent + Responded + Partial + Completed) × 100**

| Role in Calculation | Statuses to Include |
|---|---|
| **Numerator** (responded) | Responded, Partial, Completed |
| **Denominator** (delivered) | Sent, Responded, Partial, Completed |

Statuses excluded from both: New, Pending, Not Sent, Fatigued, Expired — these were never delivered to the customer.

**Bounced records** (email bounced) can be included or excluded from the denominator depending on preference. Excluding them gives the response rate among customers who actually received the email; including them gives the rate across all send attempts.

### Date Filtering for Response Rate

Use `simplesurvey__Survey_Send_Date__c` as the date boundary — not `simplesurvey__Last_Response_At__c`. The goal is to answer "of surveys *sent* in this period, what percentage got a response?" Some responses may arrive after the period closes, which is expected.

### Identifying a Specific Survey Program

Survey records do not include a direct lookup field to the survey program configuration. To scope a response rate query to a specific program, filter using one or more of:

- **`simplesurvey__Survey_Type__c`** — narrows to the scale type (e.g., all NPS surveys, all CSAT surveys). If an org runs only one program per type, this may be sufficient.
- **`RecordType.DeveloperName`** — admins sometimes create one record type per survey program. Ask the user how their org is configured.
- **`Name`** — survey record names typically include the program name. Use a `LIKE` filter (e.g., `Name LIKE '%Case NPS%'`) if the user knows their program naming convention.

When a user asks about "our Case NPS program" or similar, clarify which of these identifiers applies in their org before running the query.

`simplesurvey__Snapshot__c` is a **rich text (HTML) field** that stores the complete survey response exactly as the respondent experienced it — all questions and answers in one place.

**When to use it:**
- Reading the full response for coaching or sentiment analysis
- When a survey program has multiple custom questions beyond the initial score
- When `simplesurvey__Survey_Comments__c` alone doesn't tell the whole story

**Important:** Because this field contains HTML markup, strip the tags before doing text analysis or sending to an LLM for summarization. The underlying plain text contains all the narrative content.

**Partial responses and the Snapshot:** When a survey has Status = 'Partial', the Snapshot will include notes indicating which questions were skipped — and whether each skip was made by the respondent intentionally or triggered automatically by a Skip Logic rule. This distinction matters for coaching: a respondent-skipped question may signal discomfort or disengagement, while a Skip Logic skip is a configured behavior and not a signal about the customer's experience.

**About custom question fields:** Survey programs can be configured with custom questions stored in org-specific fields. These are not part of the standard package and vary by customer. The Snapshot field is the most reliable way to capture all question responses in one place regardless of program configuration.

---

## Common Analysis Patterns

### Response Rate for a Survey Program
*"What is my response rate for our Case NPS survey program in Q1?"*
- Filter by `simplesurvey__Survey_Send_Date__c` within the target period
- Identify the program using `simplesurvey__Survey_Type__c`, `RecordType.DeveloperName`, or `Name LIKE` — confirm with the user which applies to their org
- Exclude test records
- Count records where Status IN ('Sent', 'Responded', 'Partial', 'Completed') for the denominator
- Count records where Status IN ('Responded', 'Partial', 'Completed') for the numerator
- Response Rate = numerator ÷ denominator × 100
- Optionally break down by month or agent to identify where response rates are stronger or weaker

### Team Performance Summary
*"Summarize feedback for my team over the last 30 days"*
- Date filter on `simplesurvey__Last_Response_At__c` (or `simplesurvey__Survey_Send_Date__c`)
- Status IN ('Responded', 'Partial', 'Completed')
- Exclude test records
- Group by `simplesurvey__Record_Owner__r.Name` for per-agent breakdown
- For NPS: `AVG(simplesurvey__NPS_Factor__c) × 100` per agent
- Surface score distribution and notable comments from Snapshot or Survey Comments

### Individual Coaching / Quarterly Review
*"Help me prepare a quarterly review for [agent]"*
- Filter to `simplesurvey__Record_Owner__r.Name = '[Agent Name]'`
- Look at score trends over time, not just averages — directional change matters
- For NPS programs: identify Detractor responses and read Snapshots to understand each situation
- Highlight Promoter examples as positive coaching evidence
- Extract recurring themes from free-text comments to inform actionable feedback

### Account Sentiment — Current & Historical
*"What is the sentiment for [Account Name]?"*
- Filter by `simplesurvey__Account__c` (the Account's record ID)
- Current sentiment: most recent Completed responses
- Historical trend: scores over time using `simplesurvey__Last_Response_At__c`
- For NPS: `simplesurvey__Net_Promoter_System__c` distribution (Detractor/Passive/Promoter counts)
- Read Snapshot fields for qualitative themes alongside the numeric picture

### Product or Service Feedback
*"What feedback are we getting about [product or topic]?"*
- Check which related object the survey program uses before assuming Case — it may be Opportunity, Lead, or a custom object, and a Product-type field could be mapped from any of them onto the survey record, or live only on the related record itself
- If a mapped field exists directly on the Survey record, filter/group on it directly
- Otherwise, join through whichever related-object lookup is populated (`simplesurvey__Case__r`, or the relevant lookup for the program's configured object) to reach a Product field
- If no structured Product field is available anywhere, analyze `simplesurvey__Survey_Comments__c` and Snapshots for theme extraction instead
- Group responses by score range to understand whether feedback skews positive or negative
- Surface verbatim themes — what customers are actually saying, not just the score

---

## Common Gotchas

- **Score context is everything.** A score of 3 means something very different on a 0–10 NPS vs. a 1–5 CSAT vs. a CES scale. Always check `simplesurvey__Survey_Type__c` before interpreting.
- **CES is not inverted — Pain scales are.** In Simple Survey, high CES ("Very Easy") is good, low CES ("Very Difficult") is bad, same direction as CSAT. Only Medical Pain and Wong-Baker scales are inverted: higher pain = worse.
- **Questionnaire type has no score.** Don't average it. Go straight to comments and Snapshot.
- **Responded ≠ full response.** Records with Status = 'Responded' only have the initial score. Comments and landing page questions will be empty.
- **Record Owner ≠ Salesforce Owner.** These are different users. Use Record Owner to find an agent's surveys; Salesforce Owner reflects management hierarchy.
- **No direct link from Survey to Survey Configuration.** If diagnosing a program-level issue (inactive program, auto-create settings), you have to match the Configuration record by `Survey_Object__c`/Record Type/Name — confirm with the user rather than assuming a match.
- **Always filter out test records.** `simplesurvey__Is_Test_Survey__c = false`
- **Also filter out likely-bot records where bot prevention is enabled.** `simplesurvey__Human_Confidence_Score__c = 0` records are suspected bots and should be excluded like test records (but call out the count). Negative scores are verification errors, not bots — exclude from scoring but report separately.
- **Snapshot is HTML.** Strip tags before text analysis.
- **NPS is a -100 to +100 scale.** Don't compare it to CSAT percentages or Likert averages without context.

---

## Visualization Note

When presenting aggregated survey results, appropriate chart types improve readability. Visualization guidance for survey data is managed by a separate skill — flag this when the output would benefit from a chart recommendation.
