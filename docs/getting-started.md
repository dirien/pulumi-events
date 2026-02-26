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

The server starts on `http://127.0.0.1:8080` with:
- MCP endpoint at `/mcp`
- Health check at `/health`
- OAuth callback at `/auth/meetup/callback`

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

## 5. Authenticate with Meetup

Once connected, ask Claude to log in:

```
Use meetup_login to authenticate with Meetup
```

This returns an OAuth URL. Open it in your browser, authorize the app, and the server handles the callback automatically. Your token is cached at `~/.config/pulumi-events/meetup_token.json` and refreshes automatically.

Luma requires no login step — the API key is configured at startup.

## 6. Start Using

After authentication, you can:

```
# Meetup
List my Meetup groups
Search for Pulumi events on Meetup
Create a draft event in berlin-pulumi-user-group
Read meetup://group/berlin-pulumi-user-group

# Luma
List my Luma events
Read luma://self
Create a Luma event called "Demo Night" on March 15
List guests for luma event evt-abc123
```

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

### Meetup token expired
The server refreshes tokens automatically. If refresh fails, run `meetup_login` again.

### Luma API errors
- Verify your API key is valid and your Luma Plus subscription is active
- Check `env | grep LUMA` to confirm the key is set
