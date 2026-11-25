# Contact Enrichment

Suggest better values for auto-created contacts from what the person wrote, and call out people who can no longer be reached so the case can be fixed. Surfaces as a Case Companion observation, or on request across the agent's open cases.

Covers every person who has emailed into the case, not only the original sender.

## Finding Auto-Created Contacts

- An auto-created contact has the Description "Automatically created by Email to Case Premium" and often sits in the Default Account (`EXTERNAL_CONTACT_ACCOUNT`).
- E2CP also auto-creates contacts for colleagues on To/CC. **Flag those instead of enriching them.** A colleague is someone whose email domain matches the email domain of an active internal Salesforce user in the org (`UserType = 'Standard'`). Experience Cloud and portal users have customer domains, so they never count. Free email providers (gmail.com, outlook.com, yahoo.com and the like) never mark someone as a colleague, even when a user has an address there.
- When the case has no Contact but an auto-created contact matches the sender's address ignoring case (a sender address with capital letters can leave the contact unlinked), offer to set it as the Case Contact.

## Sources, Best First

1. The sender's display name on inbound EmailMessages — present even on short replies. Handle "Last, First" order.
2. Signatures in inbound EmailMessage bodies (E2CP strips them from comments).
3. The To/CC header lines in E2CP comments (`CC: Name <address>`), which name people who were only copied and never wrote in.

## What to Suggest

- Standard Contact fields only: First Name, Last Name, Title, Phone, Mobile.
- **Fill empty fields only; never overwrite an existing value.** A name field that holds the email address (E2CP's placeholder) counts as empty.
- When the signature disagrees with an existing value (e.g. Title), show both and leave the record alone.
- Nothing changes until the agent confirms. Use the approval checklist for batches.

### Suggesting an Account

When the contact is in the Default Account, the skill may suggest the matching Account; the agent confirms.

- Match by email domain first: accounts where other contacts with the same domain already sit, or the account's website. Skip this for free email providers; they say nothing about the company.
- Then by the company the signature names.
- Never by account name alone.
- With more than one candidate, show them and let the agent pick.

### Senders that aren't people

Skip voicemail alerts, no-reply addresses, and shared mailboxes; mention them instead of enriching. Out-of-office auto-replies are not departures.

The org's own support addresses (see `replying.md`, "Support addresses are never recipients") are never contacts: don't enrich them, suggest them as the Case Contact, or match accounts by them.

## Reachability

Call out a person who can't receive email, quoting the evidence. Signals:

- `Contact.EmailBouncedDate` / `EmailBouncedReason` (populated when bounce management is on).
- Bounce messages in inbound comments or emails: mailer-daemon, postmaster, "Undeliverable", "Delivery Status Notification".
- Departure statements: "no longer with the company", "Jane left; please work with Raj".

For an unreachable person, **fix the case only**, with the agent's confirmation:

- Remove them from Additional To / CC and the Case Team. Removing a Case Team Member deletes its CaseTeamMember record; if the connection can't delete records, tell the agent to remove them from the Case Team on the case page.
- If they were the Case Contact and someone else was named, suggest that person (an existing contact, or a new one the agent approves).
- If they were the only recipient, warn that a sent reply would be added as a comment with no email going out.

Never delete the contact, change or clear their email address, or otherwise edit their Contact record for a departure or bounce. That is the agent's decision.
