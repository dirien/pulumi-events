---
name: luma-send-invites
description: Invite people to a Luma event by email with luma_send_invites, optionally using the people list and guest list to choose or de-duplicate recipients. Use when asked to invite, re-invite or email Luma contacts.
---

# Send Luma invites

## Tool: `luma_send_invites(event_id, emails, message=None)`

- `event_id`: Luma API ID (`evt-...`).
- `emails`: at least one address. An empty list is rejected.
- `message`: optional note added to every invite, at most 200 characters. Longer values are rejected.
- People who are not on the guest list are added and invited.

The tool sends real emails and is not idempotent. Do not call it twice for the same list.

## Flow

1. Identify the event. Use `luma_list_events` or `luma_get_event` if you only have a name.
2. Build the recipient list.
   - From the user: use the addresses given.
   - From the calendar: `luma_list_people` returns contacts with name, email, attendance count and tags. Filter locally.
3. Remove people already invited: `luma_list_guests(event_id)` and drop matching emails.
4. Show the user the final list, the event name and time, and the message. Wait for a yes.
5. Call `luma_send_invites`.
6. Report how many invites were sent. Check the result before claiming success.

## Notes

- `luma_list_people` and `luma_list_guests` accept `limit`. Large calendars take a while, so pass one when sampling.
- Make sure the event is not cancelled or in the past before inviting.
