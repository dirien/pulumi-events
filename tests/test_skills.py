"""Tests for MCP skills (skill:// resources) and tool registration."""

from __future__ import annotations

import pytest
from fastmcp import Client

from pulumi_events.server import SKILLS_DIR, mcp

EXPECTED_TOOL_COUNT = 27
EXPECTED_SKILLS = {"create-edit-events", "luma-send-invites", "meetup-network-search"}


def test_skill_folders_match_expected() -> None:
    found = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    assert found == EXPECTED_SKILLS


async def test_all_tools_registered() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert len(tools) == EXPECTED_TOOL_COUNT


async def test_skills_listed_as_resources() -> None:
    async with Client(mcp) as client:
        resources = await client.list_resources()
    uris = {str(r.uri) for r in resources}
    for name in EXPECTED_SKILLS:
        assert f"skill://{name}/SKILL.md" in uris


@pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
async def test_skill_readable(name: str) -> None:
    async with Client(mcp) as client:
        contents = await client.read_resource(f"skill://{name}/SKILL.md")
    text = contents[0].text
    assert text.startswith("---")
    assert f"name: {name}" in text


async def test_existing_resource_templates_still_registered() -> None:
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    uris = {t.uri_template for t in templates}
    assert "meetup://group/{urlname}" in uris
    assert "luma://event/{event_id}" in uris


async def test_skills_extension_advertised() -> None:
    async with Client(mcp) as client:
        extensions = client.server_capabilities.extensions or {}
    assert "io.modelcontextprotocol/skills" in extensions
