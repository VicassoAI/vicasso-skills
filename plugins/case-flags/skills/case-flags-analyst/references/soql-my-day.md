# SOQL — My Day (Job A)

The three flagged rings, follow-ups due today, and the stalest open cases — the personal daily view.

> Placeholders (`{UID}`, `{REPORT_IDS}`, `{FOLLOW_UP_ON}`, `{NEXT_STEPS}`, `{CF_SCOPE}`) are defined in
> `references/soql-preflight.md`, which also holds the Preflight query every job runs first.

## 2. My Day — flagged rings (ordered by breach time)

### Ring 1 — Cases I Own (includes closed-but-flagged)

```sql
SELECT Id, CaseNumber, Subject, Status, Priority, IsClosed, Account.Name, Contact.Name,
       FLAGS__Case_Flag_Business__c, FLAGS__Aging_Speed__c, FLAGS__Initial_Response__c,
       FLAGS__CaseFlagsEscalationTime1__c, FLAGS__CaseFlagsEscalationTime2__c,
       FLAGS__CaseFlagsEscalationTime3__c, FLAGS__CaseFlagsEscalationTime4__c,
       {FOLLOW_UP_ON}, {NEXT_STEPS}
FROM Case
WHERE FLAGS__ViewedFlag__c != null
  AND OwnerId = '{UID}'
  {CF_SCOPE}
ORDER BY FLAGS__CaseFlagsEscalationTime4__c ASC
```

Note: no `IsClosed` filter — a closed case that is still flagged means a customer replied after close
and must surface.

### Ring 2 — Cases I'm a team member on (flagged, not owner)

On `CaseTeamMember` the Case lookup is `ParentId` (NOT `CaseId`), and the member is `MemberId`:

```sql
SELECT ParentId, Parent.CaseNumber, Parent.Subject, Parent.Status, Parent.Account.Name, Parent.OwnerId,
       Parent.FLAGS__Case_Flag_Business__c, Parent.FLAGS__Aging_Speed__c,
       Parent.FLAGS__CaseFlagsEscalationTime1__c, Parent.FLAGS__CaseFlagsEscalationTime2__c,
       Parent.FLAGS__CaseFlagsEscalationTime3__c, Parent.FLAGS__CaseFlagsEscalationTime4__c
FROM CaseTeamMember
WHERE MemberId = '{UID}'
  AND Parent.FLAGS__ViewedFlag__c != null
  AND Parent.OwnerId != '{UID}'
ORDER BY Parent.FLAGS__CaseFlagsEscalationTime4__c ASC
```
(Apply `{CF_SCOPE}` against `Parent.FLAGS__Enable_Case_Flags__c` when selective.)

### Ring 3 — Flagged cases in my queues (unassigned to a person)

One query via semi-join (verified live — matches the explicit-Id-list result exactly). `Owner.Name` on a
queue-owned case is the queue's name, for display:
```sql
SELECT Id, CaseNumber, Subject, Status, Account.Name, OwnerId, Owner.Name,
       FLAGS__Case_Flag_Business__c, FLAGS__Aging_Speed__c, FLAGS__CaseFlagsEscalationTime4__c
FROM Case
WHERE FLAGS__ViewedFlag__c != null
  AND OwnerId IN (SELECT GroupId FROM GroupMember
                  WHERE UserOrGroupId = '{UID}' AND Group.Type = 'Queue')
  {CF_SCOPE}
ORDER BY FLAGS__CaseFlagsEscalationTime4__c ASC
```
If a connector rejects the semi-join, fall back to two steps — queues first:
```sql
SELECT GroupId FROM GroupMember
WHERE UserOrGroupId = '{UID}' AND Group.Type = 'Queue'
```
then the same Case query with `OwnerId IN ({QUEUE_IDS})`.
## 3. My Day — Follow-ups due today (owned, unflagged)

```sql
SELECT Id, CaseNumber, Subject, Status, Account.Name, {FOLLOW_UP_ON}, {NEXT_STEPS}
FROM Case
WHERE OwnerId = '{UID}'
  AND FLAGS__ViewedFlag__c = null
  AND {FOLLOW_UP_ON} >= TODAY AND {FOLLOW_UP_ON} < TOMORROW
  {CF_SCOPE}
ORDER BY {FOLLOW_UP_ON} ASC
```
## 4. My Day — Open Cases (owned, unflagged, no follow-up, longest since activity)

Fetch a candidate set with recent-touch subqueries, then compute true last-activity and take the top 5:
```sql
SELECT Id, CaseNumber, Subject, Status, Account.Name, LastModifiedDate, {NEXT_STEPS},
       (SELECT CreatedDate FROM CaseComments ORDER BY CreatedDate DESC LIMIT 1),
       (SELECT MessageDate FROM EmailMessages ORDER BY MessageDate DESC LIMIT 1)
FROM Case
WHERE OwnerId = '{UID}'
  AND FLAGS__ViewedFlag__c = null
  AND {FOLLOW_UP_ON} = null
  AND IsClosed = false
  {CF_SCOPE}
ORDER BY LastModifiedDate ASC
LIMIT 50
```
last-activity = max(latest CaseComment.CreatedDate, latest EmailMessage.MessageDate); fall back to
LastModifiedDate only if neither child exists. Sort ascending by last-activity; show the 5 stalest.
