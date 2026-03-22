<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Managed by agent: keep sections and order; edit content, not structure -->

# AGENTS.md

**Precedence:** the **closest `AGENTS.md`** to the files you're changing wins. Root holds global defaults only.

## Overview

MCP server for managing events on **Meetup.com** and **Luma** via AI assistants. Built with FastMCP 3.x (Python ≥3.12). Exposes 22 tools + 6 resources over streamable-http transport. Provider architecture: each platform implements `EventProvider` Protocol.

## Setup

```bash
uv sync                                                  # install deps
pulumi env run pulumi-idp/auth -- uv run pulumi-events   # run with secrets from Pulumi ESC
```

Env vars use `PULUMI_EVENTS_` prefix — see `src/pulumi_events/settings.py`.

## Commands
> Source: Makefile

| Task | Command | ~Time |
|------|---------|-------|
| Install | `uv sync` | ~5s |
| Lint | `uv run ruff check src/ tests/` | ~2s |
| Format | `uv run ruff format src/ tests/` | ~2s |
| Format check | `uv run ruff format --check src/ tests/` | ~1s |
| Test (all) | `make test` | ~5s |
| Test (single) | `uv run pytest tests/test_foo.py -v` | ~2s |
| Build | `uv build` | ~3s |
| Run server | `uv run pulumi-events` | — |
| Clean | `make clean` | ~1s |

## Code style

- **Linter/formatter**: `ruff` — config in `pyproject.toml`
- **Line length**: 99
- **Target**: Python 3.12
- **Imports**: `from __future__ import annotations` in every module; isort via ruff
- **Secrets**: always `SecretStr`, access via `.get_secret_value()`
- **Type annotations**: required on all public functions (ruff ANN rules enabled)

## Workflow
1. **Before coding**: Read nearest `AGENTS.md` + check Golden Samples
2. **After each change**: Run lint → single test
3. **Before committing**: Run full test suite if changes affect >2 files or touch shared code
4. **Before claiming done**: Show test output as evidence

## File Map
```
src/pulumi_events/
├── __main__.py          # CLI entrypoint → main()
├── server.py            # FastMCP instance, lifespan, middleware, custom routes
├── settings.py          # Pydantic Settings (PULUMI_EVENTS_ prefix)
├── exceptions.py        # AuthenticationError, ProviderError
├── utils.py             # guess_image_content_type
├── auth/                # Meetup OAuth2 + token cache
├── providers/
│   ├── base.py          # EventProvider Protocol + ProviderCapability enum
│   ├── registry.py      # ProviderRegistry
│   ├── meetup/          # GraphQL client, provider, models, queries
│   └── luma/            # REST client + provider
├── resources/           # @mcp.resource handlers (meetup://, luma://)
└── tools/               # @mcp.tool handlers + _deps.py + _errors.py
tests/conftest.py
docs/getting-started.md
```

## Golden Samples (follow these patterns)

| For | Reference | Key patterns |
|-----|-----------|--------------|
| New MCP tool | `tools/event_tools.py` | `@mcp.tool(tags=..., annotations=..., output_schema=...)`, `Depends(get_*_provider)`, `@handle_provider_errors` |
| New MCP resource | `resources/meetup_resources.py` | `@mcp.resource("meetup://...")` with typed URI templates |
| New provider | `providers/meetup/` | Protocol `EventProvider`, separate client/provider/models/queries |
| Dependency injection | `tools/_deps.py` | Factory funcs from lifespan context via `get_context()` |
| Error handling | `tools/_errors.py` | `@handle_provider_errors` converts exceptions → `ToolError` |
| Settings | `settings.py` | `pydantic-settings`, `SecretStr` for secrets |

## Examples

Adding a new tool:
```python
# In tools/my_tools.py
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_meetup_provider
from pulumi_events.tools._errors import handle_provider_errors

@mcp.tool(tags={"meetup", "events"}, annotations={"readOnlyHint": True})
@handle_provider_errors
async def meetup_my_tool(event_id: str, meetup: MeetupProvider = Depends(get_meetup_provider)):
    return await meetup.some_method(event_id)
```
Then import in `server.py` at the bottom with the other tool imports.

## Security

- **Secrets**: All credentials via `SecretStr` — never log or return `.get_secret_value()` in tool output
- **Endpoint validation**: HTTPS-only enforced by `Settings` validators
- **OAuth tokens**: cached on disk at `~/.config/pulumi-events/`, never committed
- **Auth**: Server supports Google OAuth or static token auth (configured in `server.py`)

## Utilities (check before creating new)

| Need | Use | Location |
|------|-----|----------|
| Get provider | `get_meetup_provider()` / `get_luma_provider()` | `tools/_deps.py` |
| Get settings | `get_settings()` | `tools/_deps.py` |
| Error wrapping | `@handle_provider_errors` | `tools/_errors.py` |
| Image MIME type | `guess_image_content_type()` | `utils.py` |

## Heuristics (quick decisions)

| When | Do |
|------|-----|
| Adding a new tool | `tools/`, `@mcp.tool`, import in `server.py` bottom |
| Adding a new resource | `resources/`, `@mcp.resource`, import in `server.py` |
| Adding a new platform | `providers/<name>/` with `client.py` + `provider.py` implementing `EventProvider` |
| Read-only tool | `annotations={"readOnlyHint": True}` |
| Mutation tool | Omit readOnlyHint, never add to cache list |
| Adding dependency | Ask first |
| Unsure about pattern | Check Golden Samples |

## Key Decisions

- **Provider pattern** — `EventProvider` Protocol; registered in `ProviderRegistry` during lifespan
- **DI via factories** — tools use `Depends(get_*_provider)`, NOT direct provider imports
- **All event logic in MCP tools** — no ad-hoc scripts
- **Meetup Pro network** — single-call create+publish, filter with `groupIds`, use `gql2` endpoint
- **Middleware** — error handling → retry → response caching in `server.py`

## Checklist

Before submitting changes:
- [ ] `uv run ruff check src/ tests/` passes
- [ ] `uv run ruff format --check src/ tests/` passes
- [ ] `make test` passes
- [ ] New tools have `tags`, `annotations`, and `@handle_provider_errors`
- [ ] New tools imported in `server.py`
- [ ] No secrets in code or logs

## Boundaries

### Always Do
- Run ruff before committing
- Add tests for new code paths
- Use conventional commit format: `type(scope): subject`
- Use `SecretStr` for credentials
- Tag tools with platform + domain

### Ask First
- Adding new dependencies
- Changing tool signatures (breaks LLM integrations)
- Adding a new provider/platform
- Modifying middleware configuration

### Never Do
- Commit secrets or credentials
- Modify `__pycache__` or generated files
- Push directly to main
- Import providers directly in tools — use `_deps.py`
- Add mutation tools to cache list in `server.py`

## When stuck

1. Check `docs/getting-started.md` for setup issues
2. Check `Makefile` for available commands
3. Check `settings.py` for env var names
4. Run `make help` for command reference

## Terminology

| Term | Means |
|------|-------|
| Provider | Platform adapter implementing `EventProvider` Protocol |
| Tool | MCP tool exposed via `@mcp.tool` |
| Resource | MCP resource for read-only lookups via `@mcp.resource` |
| Lifespan | FastMCP startup context that initializes shared state |
| Pro network | Meetup Pro network (urlname: `pugs`) |
| ESC | Pulumi ESC — injects secrets at runtime |

## Index of scoped AGENTS.md

No scoped AGENTS.md files — this is a single-package project. All conventions live here in the root.

## When instructions conflict
The nearest `AGENTS.md` wins. Explicit user prompts override files.
