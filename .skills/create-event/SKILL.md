---
name: create-event
description: >
  Create events on Meetup and Luma using the pulumi-events MCP server tools.
  Use this skill whenever the user asks to create, schedule, or publish an event
  on Meetup or Luma — including single-group events, Pro network events that fan
  out to multiple chapters, online events, or cross-posting from Meetup to Luma.
  Also use when the user asks to edit an existing event's time, title, or details.
  Triggers on phrases like "create a meetup", "schedule an event", "publish to all
  groups", "network event", "cross-post to Luma", "edit the event time", or
  "set up a workshop on Meetup".
---

# Create Event Skill

Guide for creating and managing events on Meetup.com and Luma via the
pulumi-events MCP server. Covers single-group events, Pro network fan-out,
online events, and Meetup-to-Luma cross-posting.

## The timezone rules — read this first

Meetup's create and edit APIs accept **opposite** datetime formats. Getting this
wrong silently breaks network events or produces opaque server errors. The MCP
tools enforce these rules at call time with clear errors, but you should get
them right to avoid round-trips.

| Operation | `start_date_time` format | Why |
|-----------|--------------------------|-----|
| **Create** | Offset-aware ISO 8601: `2026-04-15T11:00:00-05:00` or `2026-04-15T16:00:00Z` | Normalized to UTC so every Pro network sub-group anchors to the same instant. Naive strings cause each sub-group to re-interpret the wall-clock in its own timezone. |
| **Edit** | Naive local wall-clock: `2026-05-13T18:00` | Meetup's `EditEventInput` rejects offset-aware strings with `"Invalid event edit params"`. The naive time is interpreted in the event's group timezone. |

For Pro network events, `pro_network_timezone` is **mandatory** alongside
`pro_network_urlname`. Without it, Meetup has no timezone anchor for the
fan-out and sub-groups drift.

## Gathering information

Before calling any create tool, make sure you have:

1. **Group URL name** — if unknown, call `meetup_list_my_groups` to discover it.
2. **Start time with timezone** — ask the user for both the time and their
   timezone if not provided. Convert to offset-aware ISO 8601 for create.
   Common offsets: US/Eastern = `-04:00` (EDT) / `-05:00` (EST),
   US/Central = `-05:00` (CDT) / `-06:00` (CST),
   US/Pacific = `-07:00` (PDT) / `-08:00` (PST),
   Europe/Berlin = `+02:00` (CEST) / `+01:00` (CET).
3. **Physical or online** — physical events need a venue ID (create one with
   `meetup_create_venue` if it doesn't exist). Online events just need
   `event_type="ONLINE"`.
4. **Draft or published** — default to `DRAFT` unless the user explicitly says
   to publish. For Pro network events the user usually wants `PUBLISHED` to
   push to all chapters at once.
5. **Pro network details** (if applicable) — `pro_network_urlname` (e.g.
   `"pugs"`), `pro_network_timezone`, and optionally which groups to
   include/exclude.

## Workflow: single-group event

```
1. (if needed) meetup_list_my_groups()           → find group_urlname
2. (if physical) meetup_create_venue(...)         → get venue_id
3. meetup_create_event(
       group_urlname="...",
       title="...",
       description="...",
       start_date_time="2026-05-15T18:00:00+02:00",   # offset-aware!
       duration="PT2H",
       event_type="PHYSICAL",        # or "ONLINE"
       venue_id="<from step 2>",     # omit for online
       publish_status="DRAFT",
       rsvp_limit=50,                # optional
       question="...",               # optional
       featured_image_path="...",    # optional local path
   )
4. (when ready) meetup_event_action(event_id="...", action="publish")
```

## Workflow: Pro network event

Pro network events fan out to all (or selected) chapters in one API call.
Both the timezone anchor and an offset-aware start time are required to
prevent sub-groups from drifting.

```
meetup_create_event(
    group_urlname="<primary-group>",
    title="Getting Started with Kubernetes on Google Cloud",
    description="<HTML description>",
    start_date_time="2026-05-13T11:00:00-05:00",  # 11 AM Central
    duration="PT2H",
    publish_status="PUBLISHED",                     # goes live everywhere
    pro_network_urlname="pugs",                     # triggers fan-out
    pro_network_timezone="US/Central",              # REQUIRED — anchor
    # pro_network_group_ids=["id1", "id2"],         # include only these
    # pro_network_excluded_group_ids=["id3"],       # or exclude these
    featured_image_path="/tmp/banner.png",          # uploaded before create
)
```

What happens internally:
- Featured image is uploaded first so it propagates to all copies.
- A network event filter is auto-created for the Pro network.
- The `start_date_time` is normalized to UTC (`2026-05-13T16:00:00Z`).
- The timezone anchor ensures every sub-group renders the same absolute moment.

## Workflow: editing an event

Only supply fields you want to change. The critical rule: `start_date_time`
must be **naive local wall-clock** in the event's group timezone.

```
meetup_edit_event(
    event_id="<event-id>",
    title="Updated Title",                  # optional
    start_date_time="2026-05-20T19:00",     # naive local — NOT offset-aware
    description="<new HTML>",               # optional
    featured_image_path="/tmp/new.png",     # requires group_urlname too
    group_urlname="<group>",                # required only with image
)
```

If the user gives you an offset-aware time for an edit, convert it to the
naive local wall-clock in the event's group timezone before calling the tool.
For example, `2026-05-13T16:00:00Z` for a Berlin group becomes
`2026-05-13T18:00` (UTC+2 in summer).

## Workflow: cross-post Meetup to Luma

1. Fetch the Meetup event: `meetup_get_event(event_id="...")`
2. Convert the start/end times to UTC ISO 8601 with `Z` suffix.
3. For physical events, look up the Google Maps place ID for the venue.
4. Create on Luma:

```
luma_create_event(
    name="<title>",
    start_at="2026-05-15T16:00:00Z",
    end_at="2026-05-15T19:00:00Z",
    description="<markdown description>",
    timezone="Europe/Berlin",
    geo_address_json={"type": "google", "place_id": "ChIJ..."},
    visibility="public",
    cover_image_path="/tmp/banner.png",
)
```

For Luma physical events, always use `geo_address_json` with a Google Maps
`place_id`. Raw address dicts are unreliable with Luma's API.

## Event lifecycle actions

After creation, manage events with `meetup_event_action`:

| Action | What it does |
|--------|-------------|
| `publish` | Make a draft event visible to the public |
| `announce` | Send announcement email to group members |
| `close_rsvps` | Stop accepting new RSVPs |
| `open_rsvps` | Resume accepting RSVPs |
| `delete` | Permanently delete the event |

## Common mistakes to avoid

- **Naive datetime on create** — causes network sub-groups to drift. Always
  include a timezone offset or `Z`.
- **Offset-aware datetime on edit** — Meetup rejects it silently. Strip the
  offset and use naive local time.
- **Missing `pro_network_timezone`** — the fan-out has no anchor. Every
  sub-group may show a different time.
- **Forgetting `PUBLISHED` on network events** — with `DRAFT`, the event
  only appears in the primary group. Use `PUBLISHED` to push everywhere.
- **Raw addresses for Luma** — always use Google Maps `place_id` in
  `geo_address_json`.

## Quick reference: parameter cheat sheet

### meetup_create_event (required params)

| Parameter | Example |
|-----------|---------|
| `group_urlname` | `"berlin-pulumi-user-group"` |
| `title` | `"Getting Started with AWS"` |
| `description` | `"<p>Join us for...</p>"` |
| `start_date_time` | `"2026-04-15T11:00:00-05:00"` (offset-aware) |

### meetup_create_event (Pro network extras)

| Parameter | Example |
|-----------|---------|
| `pro_network_urlname` | `"pugs"` |
| `pro_network_timezone` | `"US/Central"` |
| `publish_status` | `"PUBLISHED"` |

### meetup_edit_event

| Parameter | Example |
|-----------|---------|
| `event_id` | `"305678901"` |
| `start_date_time` | `"2026-05-13T18:00"` (naive local) |
