# SOQL — Preflight and conventions

The configuration read every job runs first, plus the placeholder conventions the other SOQL files use.

Conventions used below:
- `{UID}` — the current user's Id (from the identity step).
- `{REPORT_IDS}` — comma-quoted Ids of a manager's direct reports (§7, `references/soql-team-view.md`).
- `{FOLLOW_UP_ON}` / `{NEXT_STEPS}` — the Case field API names read from FlagPref
  (`FLAGS__Follow_Up_On_Field__c` / `FLAGS__Next_Steps_Field__c`). Substitute the literal API names.
- `{CF_SCOPE}` — if the org is selective (`FLAGS__Organization_Wide__c = false`), append
  ` AND FLAGS__Enable_Case_Flags__c = true`; if org-wide, append nothing.

Always run the Preflight first; every other query depends on its output. There is no standalone CFHT
probe — the first CFHT query a job needs doubles as the probe (see SKILL.md, "CFHT availability").

## 1. Preflight (read configuration)

```sql
SELECT FLAGS__Organization_Wide__c, FLAGS__Enable_History__c,
       FLAGS__Track_Flag_Set__c, FLAGS__Track_Flag_Clear__c,
       FLAGS__Track_Case_Ownership__c, FLAGS__Track_Case_Status__c,
       FLAGS__HistoryTrackingMonths__c,
       FLAGS__Enable_Follow_Up_Process__c, FLAGS__Follow_Up_On_Field__c, FLAGS__Next_Steps_Field__c,
       FLAGS__BusinessHoursId__c,
       FLAGS__TimeOffset1__c, FLAGS__TimeOffset2__c, FLAGS__TimeOffset3__c, FLAGS__TimeOffset4__c
FROM FLAGS__FlagPref__c
WHERE SetupOwnerId IN (SELECT Id FROM Organization)
LIMIT 1
```

Identity: use the connection's "current user" tool (e.g. getUserInfo) to get `{UID}` and display name.
Do not ask the user who they are.
