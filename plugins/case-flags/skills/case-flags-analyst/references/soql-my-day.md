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

Queue membership can be direct, or through a **public group** or a **role** (verified live: one org had 6
queue memberships held by groups and roles, not users). Resolve the user's groups first, then the queues.
All of these queries were verified live.

**Ring 3, step 1: the user's role chain.** Start from the role Id (from the identity step, or
`SELECT UserRoleId FROM User WHERE Id = '{UID}'`) and follow `ParentRoleId` until it's null:
```sql
SELECT Id, ParentRoleId FROM UserRole WHERE Id = '{ROLE_ID}'
```

**Ring 3, step 2: groups the user is in.**
```sql
SELECT GroupId FROM GroupMember WHERE UserOrGroupId = '{UID}' AND Group.Type = 'Regular'
```
```sql
SELECT Id FROM Group
WHERE (RelatedId = '{ROLE_ID}' AND Type IN ('Role','RoleAndSubordinates','RoleAndSubordinatesInternal'))
   OR (RelatedId IN ({ANCESTOR_ROLE_IDS}) AND Type IN ('RoleAndSubordinates','RoleAndSubordinatesInternal'))
```
Public groups can be nested, so add one more hop (groups that contain the groups found so far):
```sql
SELECT GroupId FROM GroupMember WHERE Group.Type = 'Regular' AND UserOrGroupId IN ({GROUP_IDS})
```

**Ring 3, step 3: queues** for the user plus every group found (`{MEMBER_IDS}` = `{UID}` + all group Ids):
```sql
SELECT GroupId FROM GroupMember WHERE Group.Type = 'Queue' AND UserOrGroupId IN ({MEMBER_IDS})
```

**Ring 3, step 4: the cases.** Cases already in Ring 2 (I'm on the case team) are excluded, so a case shows once:
```sql
SELECT Id, CaseNumber, Subject, Status, Account.Name, OwnerId, Owner.Name,
       FLAGS__Case_Flag_Business__c, FLAGS__Aging_Speed__c, FLAGS__CaseFlagsEscalationTime4__c
FROM Case
WHERE FLAGS__ViewedFlag__c != null
  AND OwnerId IN ({QUEUE_IDS})
  AND Id NOT IN (SELECT ParentId FROM CaseTeamMember WHERE MemberId = '{UID}')
  {CF_SCOPE}
ORDER BY FLAGS__CaseFlagsEscalationTime4__c ASC
```
`Owner.Name` on a queue-owned case is the queue's name, for display. If the role steps can't run (no
role, or no access to `UserRole`), use direct and public-group membership, and say that role-based
queues may be missing.
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
## 3b. My Day — Overdue follow-ups (owned, unflagged, follow-up date already past)

```sql
SELECT Id, CaseNumber, Subject, Status, Account.Name, {FOLLOW_UP_ON}, {NEXT_STEPS}
FROM Case
WHERE OwnerId = '{UID}'
  AND IsClosed = false
  AND FLAGS__ViewedFlag__c = null
  AND {FOLLOW_UP_ON} < TODAY
  {CF_SCOPE}
ORDER BY {FOLLOW_UP_ON} ASC
```
These fall between §3 (due today) and §4 (no date at all), so without this query they appear nowhere.

## 4. My Day — Open Cases (owned, unflagged, no follow-up, longest since activity)

**Count first.** The candidate query orders by `LastModifiedDate`, and automation that touches a case
updates that date without any human activity. A capped candidate set can therefore drop a genuinely
stale case. Count the candidates:
```sql
SELECT COUNT(Id) FROM Case
WHERE OwnerId = '{UID}' AND FLAGS__ViewedFlag__c = null AND {FOLLOW_UP_ON} = null
  AND IsClosed = false {CF_SCOPE}
```
- **500 or fewer:** run the query below **without** `LIMIT`, so every candidate gets its true
  last-activity.
- **More than 500:** keep `LIMIT 500` and say the list was drawn from the 500 least recently modified
  cases, so it may miss some.

Then fetch the candidates with recent-touch subqueries, compute true last-activity, and take the top 5:
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
```
last-activity = max(latest CaseComment.CreatedDate, latest EmailMessage.MessageDate); fall back to
LastModifiedDate only if neither child exists. Sort ascending by last-activity; show the 5 stalest.
