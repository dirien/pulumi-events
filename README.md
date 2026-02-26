# pulumi-events

MCP server for managing events on Meetup.com and Luma via AI assistants like Claude.

Built with [FastMCP 3.x](https://gofastmcp.com), it exposes Meetup's GraphQL API and Luma's REST API as MCP tools and resources so LLMs can search events, manage groups, create and publish events, and more.

## Features

- **15 tools** across two platforms (Meetup + Luma)
- **6 resources** for read-only lookups (user profiles, group/event/network details)
- Meetup: OAuth2 authentication with automatic token caching and refresh
- Luma: API key authentication
- Streamable HTTP transport for production use
- Provider architecture for easy addition of new platforms

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

### Meetup

| Tool | Description |
|------|-------------|
| `list_platforms` | List all configured platforms with auth status |
| `meetup_login` | Start Meetup OAuth2 login flow |
| `meetup_search_events` | Search events with filters (location, date, type) |
| `meetup_search_groups` | Search groups by keyword and location |
| `meetup_list_my_groups` | List all groups you belong to |
| `meetup_create_event` | Create an event (defaults to DRAFT) |
| `meetup_edit_event` | Edit an existing event |
| `meetup_event_action` | Delete, publish, announce, or manage RSVPs |
| `meetup_network_search` | Search within a Pro network |
| `meetup_create_venue` | Create a venue for events |

### Luma

| Tool | Description |
|------|-------------|
| `luma_list_events` | List events from your Luma calendar |
| `luma_create_event` | Create a Luma event |
| `luma_update_event` | Update a Luma event |
| `luma_cancel_event` | Cancel a Luma event |
| `luma_list_guests` | List guests for a Luma event |

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
| `PULUMI_EVENTS_MEETUP_CLIENT_ID` | — | Meetup OAuth2 client ID |
| `PULUMI_EVENTS_MEETUP_CLIENT_SECRET` | — | Meetup OAuth2 client secret |
| `PULUMI_EVENTS_LUMA_API_KEY` | — | Luma API key (requires Luma Plus) |
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
│   ├── oauth.py           # OAuth2 flow helpers (Meetup)
│   └── token_store.py     # Token persistence + auto-refresh
├── providers/
│   ├── base.py            # EventProvider protocol + capabilities
│   ├── registry.py        # Provider registry
│   ├── meetup/
│   │   ├── client.py      # GraphQL client with auto token refresh
│   │   ├── provider.py    # MeetupProvider implementation
│   │   ├── queries.py     # GraphQL query/mutation strings
│   │   └── models.py      # Pydantic response models
│   └── luma/
│       ├── client.py      # REST client for Luma public API
│       └── provider.py    # LumaProvider implementation
├── tools/
│   ├── _deps.py           # Shared dependency factories
│   ├── platform_tools.py  # list_platforms, meetup_login
│   ├── event_tools.py     # Meetup event mutations
│   ├── group_tools.py     # Meetup group tools
│   ├── search_tools.py    # Meetup search tools
│   ├── venue_tools.py     # Meetup venue tools
│   └── luma_tools.py      # Luma event + guest tools
└── resources/
    ├── meetup_resources.py
    └── luma_resources.py
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
