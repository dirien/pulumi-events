---
name: create-edit-events
description: Create and edit events on Meetup and Luma with the pulumi-events tools, including the datetime, venue and image rules that differ per platform. Use when asked to create, update, publish or mirror an event.
---

# Create and edit events (Meetup + Luma)

## Meetup

### Create: `meetup_create_event`

Required: `group_urlname`, `title`, `description` (HTML), `start_date_time`.

- `start_date_time` must be ISO 8601 **with an offset** (`2026-05-13T11:00:00-05:00` or `...Z`). Naive values are rejected.
- `duration` is an ISO 8601 period, default `PT2H`.
- `publish_status` defaults to `DRAFT`. Use `PUBLISHED` only when the user wants the event live.
- `event_type="ONLINE"` attaches Meetup's online-event venue. For in-person events create a venue first with `meetup_create_venue` and pass its ID as `venue_id`.
- Images: `featured_image_url` (public URL, works when the server runs remotely) or `featured_image_path` (only if the server shares your filesystem). Pass one, not both.
- Optional: `rsvp_limit`, `question`, `hosts` (member IDs), `topics` (topic IDs).

For Pro network events (one call, many groups) see the `meetup-network-search` skill. They additionally require `pro_network_urlname` and `pro_network_timezone`.

### Edit: `meetup_edit_event`

Only the fields you pass change. `start_date_time` here is the **opposite** of create: a naive local wall-clock string in the event's group timezone (`2026-05-13T18:00`). Offsets are rejected. Pass `group_urlname` when setting a featured image.

## Luma

### Create: `luma_create_event`

Required: `name`, `start_at`, `end_at` (ISO 8601, UTC).

- `timezone` is an IANA name such as `Europe/Berlin`. It defaults to the account timezone.
- Physical events: look up the venue's Google Maps place ID and pass `geo_address_json={"type": "google", "place_id": "ChIJ..."}`. Do not forward Meetup venue objects. A plain address dict is a less reliable fallback and must not contain `type`.
- Online events: `meeting_url`.
- `visibility` is `public` (default) or `private`.
- Cover: `cover_image_url` or `cover_image_path`.
- `tint_color` is a hex theme colour. When omitted on create, the server default applies. Updates never apply the default.

### Update, cancel

`luma_update_event(event_id, ...)` changes only the fields you pass. `luma_cancel_event(event_id)` cancels. Event IDs look like `evt-...`.

## Mirroring Meetup to Luma

1. `meetup_get_event` to read title, description, time and venue.
2. Convert the time to UTC for `start_at` and `end_at`.
3. Resolve the venue to a Google place ID. Do not copy the Meetup venue.
4. Create the Luma event, then report both URLs.

## Checks before reporting success

- Confirm the returned event URL and status. Meetup returns `id`, `title`, `dateTime`, `eventUrl`, `status`.
- Creation tools are not idempotent. Do not retry a create after an ambiguous failure without listing events first (`meetup_list_group_events` or `luma_list_events`).
