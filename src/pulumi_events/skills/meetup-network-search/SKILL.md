---
name: meetup-network-search
description: Search a Meetup Pro network (urlname pugs) for events, groups or members, and create one event across selected chapters using group IDs. Use for network-wide searches, finding organizers, or publishing a network event.
---

# Meetup Pro network (`pugs`)

The Pro network URL name is `pugs`. `meetup_network_search` falls back to the configured network when `network_urlname` is omitted. `meetup_create_event` has no such fallback: network mode turns on only when `pro_network_urlname` is passed, so always pass it for network events. Without it, `pro_network_group_ids` and the other network options are ignored.

## Search: `meetup_network_search`

`search_type` is `events`, `groups` or `members`.

- `query`: event title or member name.
- Members only: `roles` (`ORGANIZER`, `COORGANIZER`, `MEMBER`), `events_attended_min`, `sort` (`groupsCount`, `eventsAttended`), `desc`.
- Paging: `first` per page, `after` cursor from the previous result.

Member results carry `groupsCount`, `eventsAttended`, `role` and `isOrganizer`. Sorting by `groupsCount` is unreliable. To find key people, filter with `roles=["ORGANIZER"]` instead.

To get group IDs for the create call, run a `groups` search and collect the IDs.

## Create one event across chapters: `meetup_create_event`

Network creation is a single call on Meetup's `gql2` endpoint. The server first creates a network event filter, then creates the event with `proNetworkEvents`. Parameters on top of the normal ones:

| Parameter | Meaning |
|-----------|---------|
| `pro_network_urlname` | `"pugs"`. Enables network mode. |
| `pro_network_timezone` | Required IANA zone, for example `US/Central` or `Europe/Berlin`. |
| `pro_network_group_ids` | Only these groups get the event. When given, all-active-groups is not applied. |
| `pro_network_excluded_group_ids` | Skip these groups. Use when targeting everyone except a few chapters. |

Rules:

- `start_date_time` must carry an offset. The tool converts it to wall-clock time in `pro_network_timezone`. Missing offset or missing timezone raises an error.
- `group_urlname` is still required: it names the hosting group.
- `publish_status="PUBLISHED"` publishes in every selected group at once. With `DRAFT`, each copy stays a draft.
- Omit both ID lists to target all active groups in the network.

Example:

```
meetup_create_event(
    group_urlname="pulumi-seattle",
    title="Getting Started with Kubernetes on Google Cloud",
    description="<p>Join us...</p>",
    start_date_time="2026-05-13T11:00:00-05:00",
    pro_network_urlname="pugs",
    pro_network_timezone="US/Central",
    pro_network_group_ids=["<id1>", "<id2>"],
    publish_status="DRAFT",
)
```

## Confirm with the user first

A published network event is visible in many groups immediately and is tedious to retract. Show the group list, time and timezone and get confirmation before using `PUBLISHED`.

## Editing afterwards

`meetup_edit_event` edits a single event. Its `start_date_time` is naive local wall-clock, not an offset string.
