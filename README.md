<p align="center">
  <img src="docs/logo.png" alt="PulumiEvent" width="400">
</p>

# Pulumi Events MCP

MCP server for managing events on Meetup.com and Luma via AI assistants like Claude.

Built with [FastMCP 3.x](https://gofastmcp.com), it exposes Meetup's GraphQL API and Luma's REST API as MCP tools and resources so LLMs can search events, manage groups, create and publish events, and more.

## Features

- **22 tools** across two platforms (Meetup + Luma), tagged by platform and domain
- **6 resources** for read-only lookups (user profiles, group/event/network details)
- **Cover image upload** — pass a local file path when creating/updating events; the server handles CDN upload automatically (Luma presigned URL, Meetup two-step photo upload)
- Auto-pagination on all list tools — single tool call returns all results
- Meetup: JWT authentication for headless server-to-server access (no browser needed), with OAuth2 fallback
- Meetup Pro network search with member metadata (roles, events attended, group counts)
- Luma: API key authentication
- Stateless HTTP transport — no stale session issues on server restarts
- Provider architecture for easy addition of new platforms

### Middleware

The server uses FastMCP's middleware stack for reliability and observability:

| Middleware | Purpose |
|---|---|
| `ErrorHandlingMiddleware` | Converts raw exceptions to proper MCP error codes, logs errors consistently |
| `RetryMiddleware` | Automatic retry with exponential backoff on transient network failures (`ConnectionError`, `TimeoutError`) |
| `ResponseCachingMiddleware` | 5-minute TTL cache on read-only tools (list, search, get) — mutations are never cached |

### Tool Metadata

All tools include FastMCP metadata for better LLM integration:

- **Tags** — every tool is tagged by platform (`meetup`, `luma`) and domain (`events`, `groups`, `members`, etc.) for discovery and filtering
- **Timeouts** — 120-second timeout on upload-capable tools and all auto-paginating list tools to prevent hangs on slow networks
- **Output schemas** — key tools declare their response structure so LLM clients know what fields to expect
- **Annotations** — read-only tools are marked with `readOnlyHint`, idempotent tools with `idempotentHint`

## Quick start

See the [Getting Started guide](docs/getting-started.md) for full setup instructions.

### Cloud (deployed)

The server runs on AWS ECS Fargate behind CloudFront. Connect Claude Desktop or Claude Code directly:

```json
{
  "mcpServers": {
    "pulumi-events": {
      "command": "npx",
      "args": ["mcp-remote", "https://d3hhsm0lhey01y.cloudfront.net/mcp"]
    }
  }
}
```

Google OAuth handles MCP auth. Meetup authenticates automatically via JWT on server startup.

### Local development

```bash
# Prerequisites: Python 3.12+, uv, Pulumi CLI (logged in)
git clone https://github.com/dirien/pulumi-events.git
cd pulumi-events
uv sync

# Start the server (credentials injected via Pulumi ESC)
pulumi env run ediri/pulumi-idp/auth -- uv run pulumi-events
```

Then point Claude Code at `http://127.0.0.1:8080/mcp`.

## Tools

### Meetup

| Tool | Tags | Description |
|------|------|-------------|
| `list_platforms` | `platform` | List all configured platforms with auth status |
| `meetup_login` | `meetup`, `auth` | Start Meetup OAuth2 login flow |
| `meetup_get_event` | `meetup`, `events` | Get full details of a Meetup event by ID |
| `meetup_list_group_events` | `meetup`, `events` | List events for a group (including drafts) with status filter |
| `meetup_search_events` | `meetup`, `events`, `search` | Search events with filters (lat/lon required, date, type) |
| `meetup_search_groups` | `meetup`, `groups`, `search` | Search groups by keyword and location (lat/lon required) |
| `meetup_list_my_groups` | `meetup`, `groups` | List all groups you belong to |
| `meetup_create_event` | `meetup`, `events` | Create an event (defaults to DRAFT). Supports `featured_image_path` for cover photo upload |
| `meetup_edit_event` | `meetup`, `events` | Edit an existing event. Supports `featured_image_path` for cover photo upload |
| `meetup_event_action` | `meetup`, `events` | Delete, publish, announce, or manage RSVPs |
| `meetup_network_search` | `meetup`, `network`, `search` | Search events, groups, or members within a Pro network |
| `meetup_list_group_members` | `meetup`, `members` | List members of a group with roles and join dates |
| `meetup_get_member` | `meetup`, `members` | Get details of a specific member in a group |
| `meetup_find_member` | `meetup`, `members` | Find a member across all your groups (cross-group lookup) |
| `meetup_create_venue` | `meetup`, `venues` | Create a venue for events |

### Luma

| Tool | Tags | Description |
|------|------|-------------|
| `luma_list_events` | `luma`, `events` | List events from your Luma calendar |
| `luma_get_event` | `luma`, `events` | Get full details of a Luma event by API ID |
| `luma_create_event` | `luma`, `events` | Create a Luma event. Supports `cover_image_path` for cover image upload |
| `luma_update_event` | `luma`, `events` | Update a Luma event. Supports `cover_image_path` for cover image upload |
| `luma_cancel_event` | `luma`, `events` | Cancel a Luma event |
| `luma_list_people` | `luma`, `people` | List all people from your Luma calendar |
| `luma_list_guests` | `luma`, `guests` | List guests for a Luma event |

### Image Upload

Both platforms support event cover images through their create/update tools:

- **Luma**: Pass `cover_image_path` (local file path) to `luma_create_event` or `luma_update_event`. The server uploads to Luma's CDN via a presigned URL and sets the `cover_url` automatically.
- **Meetup**: Pass `featured_image_path` (local file path) to `meetup_create_event` or `meetup_edit_event`. The server uploads via Meetup's `createGroupEventPhoto` mutation and sets the `featuredPhotoId`. For create, the event is created first, then the photo is uploaded and attached via an edit (since Meetup's `CreateEventInput` doesn't support `featuredPhotoId`).

Supported image formats: JPEG, PNG, GIF, WebP, SVG, AVIF.

### Cross-Platform: Meetup to Luma

When copying an event from Meetup to Luma, the LLM should look up the venue's **Google Maps place ID** and pass it as `geo_address_json`:

```json
// Recommended — Google Maps place ID (most reliable)
{"type": "google", "place_id": "ChIJJzpTdyB0nkcRblzKCp3kxeQ"}
```

Luma resolves the full address, coordinates, and map pin from the place ID automatically. Do NOT pass raw Meetup venue objects — they use an incompatible format. The server also strips invalid `type` fields server-side as a safety net.

## Resources

| URI | Description |
|-----|-------------|
| `meetup://self` | Authenticated Meetup user profile |
| `meetup://group/{urlname}` | Meetup group details by URL name |
| `meetup://event/{event_id}` | Meetup event details by ID |
| `meetup://network/{urlname}` | Meetup Pro network info |
| `luma://self` | Authenticated Luma user profile |
| `luma://event/{event_id}` | Luma event details by API ID |

## Configuration

All settings are loaded from environment variables with the `PULUMI_EVENTS_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `PULUMI_EVENTS_MEETUP_CLIENT_ID` | — | Meetup OAuth client ID |
| `PULUMI_EVENTS_LUMA_API_KEY` | — | Luma API key (requires Luma Plus) |
| `PULUMI_EVENTS_SERVER_HOST` | `127.0.0.1` | Server bind address |
| `PULUMI_EVENTS_SERVER_PORT` | `8080` | Server port |
| `PULUMI_EVENTS_TOKEN_CACHE_DIR` | `~/.config/pulumi-events` | Token cache directory |
| `PULUMI_EVENTS_AUTH_TOKEN` | — | Bearer token for MCP endpoint auth (optional) |
| `PULUMI_EVENTS_AUTO_OPEN_BROWSER` | `false` | Auto-open browser for OAuth login |
| `PULUMI_EVENTS_MEETUP_PRO_NETWORK_URLNAME` | `pugs` | Default Meetup Pro network URL name |
| `PULUMI_EVENTS_BASE_URL` | — | Public URL override (e.g. CloudFront domain) |
| `PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY` | — | RSA private key PEM for Meetup JWT auth |
| `PULUMI_EVENTS_MEETUP_JWT_KEY_ID` | — | Meetup signing key ID (kid) |
| `PULUMI_EVENTS_MEETUP_MEMBER_ID` | — | Meetup member ID for JWT auth (sub claim) |
| `PULUMI_EVENTS_MEETUP_TOKEN_BACKEND` | `file` | Token backend: `file` or `env` |
| `PULUMI_EVENTS_GOOGLE_CLIENT_ID` | — | Google OAuth client ID (for MCP auth) |
| `PULUMI_EVENTS_GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |

## Authentication

The MCP endpoint supports optional bearer token authentication. When `PULUMI_EVENTS_AUTH_TOKEN` is set, all MCP requests must include an `Authorization: Bearer <token>` header. When unset, the server runs without auth (the default for local development).

To enable:

```bash
export PULUMI_EVENTS_AUTH_TOKEN="your-secret-token"
```

MCP clients must then send the token in the `Authorization` header. Example Claude Code config:

```json
{
  "mcpServers": {
    "pulumi-events": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8080/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    }
  }
}
```

Health (`/health`) and OAuth callback (`/auth/meetup/callback`) routes are not affected by MCP auth.

## Project Structure

```
src/pulumi_events/
├── server.py              # FastMCP instance, lifespan, middleware, custom routes
├── settings.py            # Pydantic Settings configuration
├── exceptions.py          # Exception hierarchy
├── utils.py               # Shared utilities (image MIME type detection)
├── auth/
│   ├── backends.py        # Pluggable token backends (File, Env)
│   ├── jwt_auth.py        # Meetup JWT auth (headless, server-to-server)
│   ├── oauth.py           # OAuth2 flow helpers (Meetup)
│   └── token_store.py     # Token persistence + auto-refresh
├── providers/
│   ├── base.py            # EventProvider protocol + capabilities
│   ├── registry.py        # Provider registry
│   ├── meetup/
│   │   ├── client.py      # GraphQL client with auto token refresh + binary upload
│   │   ├── provider.py    # MeetupProvider implementation + photo upload
│   │   ├── queries.py     # GraphQL query/mutation strings
│   │   └── models.py      # Pydantic response models
│   └── luma/
│       ├── client.py      # REST client for Luma public API + image upload
│       └── provider.py    # LumaProvider implementation
├── tools/
│   ├── _deps.py           # Shared dependency factories
│   ├── platform_tools.py  # list_platforms, meetup_login
│   ├── event_tools.py     # Meetup event mutations (with image upload)
│   ├── group_tools.py     # Meetup group tools
│   ├── member_tools.py    # Meetup member tools
│   ├── search_tools.py    # Meetup search tools
│   ├── venue_tools.py     # Meetup venue tools
│   └── luma_tools.py      # Luma event + guest tools (with image upload)
└── resources/
    ├── meetup_resources.py
    └── luma_resources.py
```

## Deployment

The server is deployed to AWS ECS Fargate via Pulumi. Infrastructure code lives in `deploy/`.

```
deploy/
├── __main__.py       # Pulumi program (VPC, ECR, ECS, ALB, CloudFront, Secrets Manager)
├── Pulumi.yaml       # Project config (org: pulumi, toolchain: uv)
├── Pulumi.dev.yaml   # Stack config (ESC environments: marketing/aws-auth, marketing/pulumi-events)
├── pyproject.toml    # Pulumi SDK dependencies
└── uv.lock
```

Architecture: CloudFront (HTTPS) → ALB (HTTP) → ECS Fargate (port 8080)

Meetup authenticates headlessly via JWT on every container startup. Secrets are stored in AWS Secrets Manager and injected via ECS task definition. All config comes from Pulumi ESC.

```bash
cd deploy
pulumi up    # deploy or update
pulumi logs  # tail container logs
```

## Development

```bash
make help       # Show all targets
make check      # Lint + format check
make format     # Auto-format
make test       # Run tests
make run        # Start the server
```

## License

MIT
