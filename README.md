# pulumi-events

MCP server for managing events on Meetup.com (and later Luma) via AI assistants like Claude.

Built with [FastMCP 3.x](https://gofastmcp.com), it exposes Meetup's GraphQL API as MCP tools and resources so LLMs can search events, manage groups, create and publish events, and more.

## Features

- **10 tools** for searching, creating, editing, and managing Meetup events, groups, venues, and Pro networks
- **4 resources** for read-only lookups (user profile, group details, event details, network info)
- OAuth2 authentication with automatic token caching and refresh
- Streamable HTTP transport for production use
- Provider architecture ready for additional platforms (Luma, etc.)

## Quick Start

See the [Getting Started guide](docs/getting-started.md) for full setup instructions.

```bash
# Prerequisites: Python 3.12+, uv, Pulumi CLI (logged in)

# Clone and install
git clone https://github.com/dirien/pulumi-events.git
cd pulumi-events
uv sync

# Start the server (credentials injected via Pulumi ESC)
pulumi env run pulumi-idp/auth -- uv run pulumi-events
```

Then add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "pulumi-events": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `list_platforms` | List configured platforms with auth status |
| `meetup_login` | Start Meetup OAuth2 login flow |
| `meetup_search_events` | Search events with filters (location, date, type) |
| `meetup_search_groups` | Search groups by keyword and location |
| `meetup_list_my_groups` | List all groups you belong to |
| `meetup_create_event` | Create an event (defaults to DRAFT) |
| `meetup_edit_event` | Edit an existing event |
| `meetup_event_action` | Delete, publish, announce, or manage RSVPs |
| `meetup_network_search` | Search within a Pro network |
| `meetup_create_venue` | Create a venue for events |

## Resources

| URI | Description |
|-----|-------------|
| `meetup://self` | Authenticated user profile |
| `meetup://group/{urlname}` | Group details by URL name |
| `meetup://event/{event_id}` | Event details by ID |
| `meetup://network/{urlname}` | Pro network info |

## Configuration

All settings are loaded from environment variables with the `PULUMI_EVENTS_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `PULUMI_EVENTS_MEETUP_CLIENT_ID` | — | Meetup OAuth2 client ID |
| `PULUMI_EVENTS_MEETUP_CLIENT_SECRET` | — | Meetup OAuth2 client secret |
| `PULUMI_EVENTS_SERVER_HOST` | `127.0.0.1` | Server bind address |
| `PULUMI_EVENTS_SERVER_PORT` | `8080` | Server port |
| `PULUMI_EVENTS_MEETUP_REDIRECT_URI` | `http://127-0-0-1.nip.io:8080/auth/meetup/callback` | OAuth2 redirect URI |
| `PULUMI_EVENTS_TOKEN_CACHE_DIR` | `~/.config/pulumi-events` | Token cache directory |

## Project Structure

```
src/pulumi_events/
├── server.py              # FastMCP instance, lifespan, custom routes
├── settings.py            # Pydantic Settings configuration
├── exceptions.py          # Exception hierarchy
├── auth/
│   ├── oauth.py           # OAuth2 flow helpers
│   └── token_store.py     # Token persistence + auto-refresh
├── providers/
│   ├── base.py            # EventProvider protocol
│   ├── registry.py        # Provider registry
│   └── meetup/
│       ├── client.py      # GraphQL client with auto token refresh
│       ├── provider.py    # MeetupProvider implementation
│       ├── queries.py     # GraphQL query/mutation strings
│       └── models.py      # Pydantic response models
├── tools/                 # MCP tool definitions
│   ├── _deps.py           # Shared dependency factories
│   ├── platform_tools.py
│   ├── event_tools.py
│   ├── group_tools.py
│   ├── search_tools.py
│   └── venue_tools.py
└── resources/
    └── meetup_resources.py  # MCP resource templates
```

## Development

```bash
# Lint and format
uv run ruff check src/
uv run ruff format src/

# Run the server
uv run pulumi-events
```

## License

MIT
