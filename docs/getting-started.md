# Getting Started

This guide walks you through setting up and running the pulumi-events MCP server.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **[Pulumi CLI](https://www.pulumi.com/docs/install/)** — logged in (`pulumi login`)
- **Meetup OAuth2 app** — registered at [meetup.com/api/oauth/list](https://www.meetup.com/api/oauth/list/)
- **Luma API key** — requires a [Luma Plus](https://lu.ma) subscription

## 1. Meetup OAuth2 App Setup

1. Go to [Meetup OAuth Consumers](https://www.meetup.com/api/oauth/list/) and create a new consumer
2. Set the **redirect URI** to:
   ```
   http://127-0-0-1.nip.io:8080/auth/meetup/callback
   ```
3. Note your **Client ID** (key) and **Client Secret**

## 2. Configure Credentials

The server reads credentials from environment variables. The recommended approach uses Pulumi ESC to manage secrets.

### Option A: Pulumi ESC (recommended)

Make sure your Pulumi ESC environment (e.g. `pulumi-idp/auth`) exports:

```yaml
environmentVariables:
  PULUMI_EVENTS_MEETUP_CLIENT_ID: ${meetup.key}
  PULUMI_EVENTS_MEETUP_CLIENT_SECRET: ${meetup.secret}
  PULUMI_EVENTS_LUMA_API_KEY: ${lumaApIKey}
```

You can add these with the Pulumi CLI:

```bash
pulumi env set pulumi-idp/auth \
  'environmentVariables.PULUMI_EVENTS_MEETUP_CLIENT_ID' '${meetup.key}'
pulumi env set pulumi-idp/auth \
  'environmentVariables.PULUMI_EVENTS_MEETUP_CLIENT_SECRET' '${meetup.secret}'
pulumi env set pulumi-idp/auth \
  'environmentVariables.PULUMI_EVENTS_LUMA_API_KEY' '${lumaApIKey}'
```

### Option B: Plain environment variables

```bash
export PULUMI_EVENTS_MEETUP_CLIENT_ID="your-meetup-client-id"
export PULUMI_EVENTS_MEETUP_CLIENT_SECRET="your-meetup-client-secret"
export PULUMI_EVENTS_LUMA_API_KEY="your-luma-api-key"
```

## 3. Install and Run

```bash
cd pulumi-events
uv sync

# With Pulumi ESC:
pulumi env run pulumi-idp/auth -- uv run pulumi-events

# Or with plain env vars:
uv run pulumi-events
```

The server starts on `http://127.0.0.1:8080` in stateless HTTP mode with:
- MCP endpoint at `/mcp`
- Health check at `/health`
- OAuth callback at `/auth/meetup/callback`

Stateless mode means each request creates a fresh transport — no stale session 404 errors after server restarts.

## 4. Connect Claude Code

Add to `~/.claude/settings.json` (or project-level `.claude/settings.json`):

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

## 5. Secure the MCP Endpoint (Optional)

To require bearer token authentication on all MCP requests, set `PULUMI_EVENTS_AUTH_TOKEN`. When unset, the server runs without auth (default for local development).

### Generate a token

```bash
openssl rand -hex 32
```

### Set the token

**Pulumi ESC:**

```bash
pulumi env set pulumi-idp/auth \
  'environmentVariables.PULUMI_EVENTS_AUTH_TOKEN' 'your-generated-token'
```

**Plain environment variable:**

```bash
export PULUMI_EVENTS_AUTH_TOKEN="your-generated-token"
```

### Update Claude Code config

Add the `headers` field with the token to your MCP server config:

```json
{
  "mcpServers": {
    "pulumi-events": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8080/mcp",
      "headers": {
        "Authorization": "Bearer your-generated-token"
      }
    }
  }
}
```

Requests without a valid `Authorization: Bearer <token>` header will receive a 401 response. Health (`/health`) and OAuth callback (`/auth/meetup/callback`) routes are not affected.

## 6. Authenticate with Meetup

Once connected, ask Claude to log in:

```
Use meetup_login to authenticate with Meetup
```

The server automatically opens your browser to the OAuth authorization page (disable with `PULUMI_EVENTS_AUTO_OPEN_BROWSER=false`). Authorize the app, and the server handles the callback automatically. Your token is cached at `~/.config/pulumi-events/meetup_token.json` and refreshes automatically.

Luma requires no login step — the API key is configured at startup.

## 7. Start Using

After authentication, you can:

```
# Meetup
List my Meetup groups
Get details of Meetup event 12345
List draft events in berlin-pulumi-user-group
List all events in tel-aviv-pulumi-user-group
Search for Pulumi events on Meetup
Create a draft event in berlin-pulumi-user-group
Create a draft event in berlin-pulumi-user-group with cover image /tmp/banner.png
Read meetup://group/berlin-pulumi-user-group
List members of berlin-pulumi-user-group
Get details of member 12345 in berlin-pulumi-user-group
Find member 12345 across all my groups
Search for organizers in my Pro network
Search network members who attended at least 5 events

# Luma
List my Luma events
Get details of Luma event evt-abc123
Read luma://self
Create a Luma event called "Demo Night" on March 15
Create a Luma event with cover image /tmp/event-banner.jpg
Update luma event evt-abc123 with a new cover image /tmp/new-banner.png
List guests for luma event evt-abc123
List all people in my Luma calendar
```

### Image Upload

Both `meetup_create_event` / `meetup_edit_event` and `luma_create_event` / `luma_update_event` accept a local file path for cover images. The server handles CDN upload automatically:

- **Luma**: pass `cover_image_path` — uploads via presigned URL to Luma CDN
- **Meetup**: pass `featured_image_path` (requires `group_urlname`) — uploads via Meetup's photo API and sets the featured photo

Supported formats: JPEG, PNG, GIF, WebP, SVG, AVIF.

### Cross-Platform Events

You can ask the LLM to copy events between platforms:

```
Read meetup event 12345 and create a matching Luma event
```

The LLM will read the Meetup event details and use the Google Maps place ID to set the venue on Luma. The server strips invalid address fields server-side as a safety net.

## Architecture

### Middleware Stack

The server uses FastMCP's middleware for reliability and performance:

- **ErrorHandlingMiddleware** — transforms raw Python exceptions into proper MCP error codes so LLM clients receive actionable error messages instead of tracebacks
- **RetryMiddleware** — automatically retries on transient `ConnectionError` / `TimeoutError` with exponential backoff (2 retries, 1–10s delay)
- **ResponseCachingMiddleware** — caches responses from read-only tools (list, search, get) for 5 minutes to reduce API calls; mutation tools are never cached

### Tool Metadata

All 22 tools include metadata for better LLM integration:

- **Tags** — platform (`meetup`, `luma`) and domain (`events`, `groups`, `members`, etc.) for filtering
- **Timeouts** — 120s on upload-capable tools and all auto-paginating list tools to prevent hangs
- **Output schemas** — key tools declare their response structure for structured LLM parsing
- **Annotations** — `readOnlyHint` and `idempotentHint` help LLM clients decide when to cache or retry

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PULUMI_EVENTS_MEETUP_CLIENT_ID` | — | Meetup OAuth2 client ID |
| `PULUMI_EVENTS_MEETUP_CLIENT_SECRET` | — | Meetup OAuth2 client secret |
| `PULUMI_EVENTS_LUMA_API_KEY` | — | Luma API key |
| `PULUMI_EVENTS_SERVER_HOST` | `127.0.0.1` | Server bind address |
| `PULUMI_EVENTS_SERVER_PORT` | `8080` | Server port |
| `PULUMI_EVENTS_MEETUP_REDIRECT_URI` | `http://127-0-0-1.nip.io:8080/auth/meetup/callback` | OAuth2 redirect URI |
| `PULUMI_EVENTS_TOKEN_CACHE_DIR` | `~/.config/pulumi-events` | Token cache location |
| `PULUMI_EVENTS_LUMA_API_ENDPOINT` | `https://public-api.luma.com/v1` | Luma API base URL |
| `PULUMI_EVENTS_AUTH_TOKEN` | — | Bearer token for MCP endpoint auth (optional, disabled if unset) |
| `PULUMI_EVENTS_AUTO_OPEN_BROWSER` | `true` | Auto-open browser for OAuth login |
| `PULUMI_EVENTS_MEETUP_PRO_NETWORK_URLNAME` | `pugs` | Default Meetup Pro network URL name |

## Troubleshooting

### Server won't start
- Check Python version: `python --version` (needs 3.12+)
- Check dependencies: `uv sync`
- Check credentials are set: `env | grep PULUMI_EVENTS`

### OAuth callback fails (Meetup)
- Verify the redirect URI in your Meetup OAuth app matches exactly:
  `http://127-0-0-1.nip.io:8080/auth/meetup/callback`
- Make sure the server is running when you click authorize
- Check server logs for detailed error messages

### 404 on /mcp after server restart
The server runs in stateless HTTP mode, so this should not happen. If you see 404 errors, restart your MCP client (Claude Code or Claude Desktop) to clear any cached session state.

### Meetup token expired
The server refreshes tokens automatically. If refresh fails, run `meetup_login` again.

### Luma API errors
- Verify your API key is valid and your Luma Plus subscription is active
- Check `env | grep LUMA` to confirm the key is set
