# Getting Started

This guide walks you through setting up and running the pulumi-events MCP server.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **[Pulumi CLI](https://www.pulumi.com/docs/install/)** — logged in (`pulumi login`)
- **Meetup OAuth2 app** — registered at [meetup.com/api/oauth/list](https://www.meetup.com/api/oauth/list/)
- **Luma API key** — requires a [Luma Plus](https://lu.ma) subscription

## 1. Meetup OAuth app setup

1. Go to [Meetup OAuth Consumers](https://www.meetup.com/api/oauth/list/) and create a new consumer
2. Set the **redirect URI** to your CloudFront domain (get it from `pulumi stack output cloudfront_url` after deploying):
   ```
   https://<your-cloudfront-domain>/auth/meetup/callback
   ```
   For local development, use `http://127-0-0-1.nip.io:8080/auth/meetup/callback` instead.
3. Note your **Client ID** (key)
4. Go to the **Signing Keys** section and click **Create First Signing Key**. Download the RSA private key -- you'll need it for JWT authentication.
5. Note the **Key ID** (kid) shown next to the signing key.

## 2. Configure credentials

The server authenticates with Meetup using the **JWT flow** (server-to-server, no browser needed). You need three things from step 1: the client ID, the RSA signing key, and the key ID. You also need your Meetup member ID (visible in your Meetup profile URL).

### Pulumi ESC (recommended)

All secrets are stored in the `pulumi/marketing/pulumi-events` ESC environment. The key values:

| ESC key | What it is |
|---|---|
| `meetupClientId` | Your Meetup OAuth client key |
| `meetupJwtSigningKey` | The RSA private key PEM |
| `meetupJwtKeyId` | The signing key ID (kid) |
| `meetupMemberId` | Your Meetup member ID |
| `lumaApiKey` | Luma API key |
| `googleClientId` / `googleClientSecret` | Google OAuth for MCP client auth |

### Plain environment variables (local dev)

```bash
export PULUMI_EVENTS_MEETUP_CLIENT_ID="your-meetup-client-id"
export PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY="$(cat /path/to/private-key.pem)"
export PULUMI_EVENTS_MEETUP_JWT_KEY_ID="your-key-id"
export PULUMI_EVENTS_MEETUP_MEMBER_ID="your-member-id"
export PULUMI_EVENTS_LUMA_API_KEY="your-luma-api-key"
```

When the JWT settings are configured, the server authenticates with Meetup automatically on startup. No need to run `meetup_login` or open a browser.

## 3. Install and Run

```bash
cd pulumi-events
uv sync

# With Pulumi ESC:
pulumi env run ediri/pulumi-idp/auth -- uv run pulumi-events

# Or with plain env vars:
uv run pulumi-events
```

The server starts on `http://127.0.0.1:8080` in stateless HTTP mode with:
- MCP endpoint at `/mcp`
- Health check at `/health`
- OAuth callback at `/auth/meetup/callback`

Stateless mode means each request creates a fresh transport — no stale session 404 errors after server restarts.

## 4. Connect to the cloud deployment

The server is already deployed to AWS and available at `https://<your-cloudfront-domain>`. This is the easiest way to get started -- no local setup required.

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pulumi-events": {
      "command": "npx",
      "args": ["mcp-remote", "https://<your-cloudfront-domain>/mcp"]
    }
  }
}
```

On first connect, you'll authenticate with your `@pulumi.com` Google account. Meetup and Luma are pre-authenticated on the server -- no extra login steps.

## 5. Connect Claude Code (local)

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

## 6. Secure the MCP endpoint (optional, local only)

To require bearer token authentication on all MCP requests, set `PULUMI_EVENTS_AUTH_TOKEN`. When unset, the server runs without auth (default for local development).

### Generate a token

```bash
openssl rand -hex 32
```

### Set the token

**Pulumi ESC:**

```bash
pulumi env set ediri/pulumi-idp/auth \
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

## 7. Authenticate with Meetup (local only)

Once connected, ask Claude to log in:

```
Use meetup_login to authenticate with Meetup
```

The server automatically opens your browser to the OAuth authorization page (disable with `PULUMI_EVENTS_AUTO_OPEN_BROWSER=false`). Authorize the app, and the server handles the callback automatically. Your token is cached at `~/.config/pulumi-events/meetup_token.json` and refreshes automatically.

Luma requires no login step — the API key is configured at startup.

## 8. Start using

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
| `PULUMI_EVENTS_MEETUP_CLIENT_ID` | — | Meetup OAuth client ID |
| `PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY` | — | RSA private key PEM for JWT auth |
| `PULUMI_EVENTS_MEETUP_JWT_KEY_ID` | — | Meetup signing key ID (kid) |
| `PULUMI_EVENTS_MEETUP_MEMBER_ID` | — | Meetup member ID for JWT auth |
| `PULUMI_EVENTS_LUMA_API_KEY` | — | Luma API key |
| `PULUMI_EVENTS_SERVER_HOST` | `127.0.0.1` | Server bind address |
| `PULUMI_EVENTS_SERVER_PORT` | `8080` | Server port |
| `PULUMI_EVENTS_BASE_URL` | — | Public URL override (CloudFront domain) |
| `PULUMI_EVENTS_TOKEN_CACHE_DIR` | `~/.config/pulumi-events` | Token cache location |
| `PULUMI_EVENTS_AUTH_TOKEN` | — | Bearer token for MCP endpoint auth (optional) |
| `PULUMI_EVENTS_MEETUP_TOKEN_BACKEND` | `file` | Token backend: `file` or `env` |
| `PULUMI_EVENTS_MEETUP_PRO_NETWORK_URLNAME` | `pugs` | Default Meetup Pro network URL name |
| `PULUMI_EVENTS_GOOGLE_CLIENT_ID` | — | Google OAuth client ID (MCP auth) |
| `PULUMI_EVENTS_GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |

## Troubleshooting

### Server won't start
- Check Python version: `python --version` (needs 3.12+)
- Check dependencies: `uv sync`
- Check credentials are set: `env | grep PULUMI_EVENTS`

### Meetup JWT auth fails on startup
- Check that `PULUMI_EVENTS_MEETUP_JWT_SIGNING_KEY`, `PULUMI_EVENTS_MEETUP_JWT_KEY_ID`, and `PULUMI_EVENTS_MEETUP_MEMBER_ID` are all set
- Verify the signing key hasn't been rotated on Meetup's side
- Check CloudWatch logs for the specific error

### Meetup token expired
With JWT auth configured, the server re-authenticates automatically via JWT when the token expires. No manual intervention needed.

### Luma API errors
- Verify your API key is valid and your Luma Plus subscription is active
- Check `env | grep LUMA` to confirm the key is set
