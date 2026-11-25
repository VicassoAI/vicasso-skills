# SOQL Gotchas (Salesforce MCP)

Query patterns that fail or time out on E2CP data, and what to do instead.

- **Long text fields can't be filtered in WHERE** (Criteria, Comment, comment bodies). Select them and filter in memory.
- **Always LIMIT queries that select `E2CP__Criteria__c`.** Unbounded, they time out.
- **Don't traverse `__r` on `E2CP__Canned_Response_Category_Relation__c`.** Select the raw Ids, then resolve names in a second query.
- **Don't OR several leading-wildcard LIKEs on `E2CP__Title__c`.** Pull the title list once and match in memory.
- **Keep `E2CP__Comment_Body__c` out of the draft-check query.** Fetch it separately, only for the draft you need.
- **Keep field lists narrow and page with LIMIT / OFFSET.** Comment bodies are rich text and can be long.
- **Unbounded aggregates over CaseComment time out.** Bounded ones (by case, date, or LIMIT) are fast.
- **Avoid reserved words as column aliases** (e.g. `first`).
- **Knowledge body fields vary by org.** Discover them via `FieldDefinition` on `Knowledge__kav` before selecting.
- **Missing packaged fields mean missing field access.** If a packaged field (e.g. `E2CP__Usage_Count__c`) is absent from the schema or rejected in a query, the user can't see it. It still exists in the package.
- **Settings may be unreadable.** A query on `E2CP__casepref__c`, `E2CP__Variation__c`, or `E2CP__Variation_Criterion__c` that returns `INVALID_TYPE` means the user lacks access, not that the org has no settings. See `settings.md`.
