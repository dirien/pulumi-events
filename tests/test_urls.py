"""Tests for URL building/parsing helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from pulumi_events.auth.oauth import build_auth_url
from pulumi_events.providers.luma.client import LumaClient
from pulumi_events.settings import Settings
from pulumi_events.utils import download_image_to_temp


@pytest.mark.asyncio
async def test_build_auth_url_encodes_params() -> None:
    settings = Settings(meetup_redirect_uri="http://x.test/cb?a=1&b=2")
    url = await build_auth_url("cid", settings)
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == settings.meetup_auth_endpoint
    assert parse_qs(parts.query) == {
        "client_id": ["cid"],
        "response_type": ["code"],
        "redirect_uri": ["http://x.test/cb?a=1&b=2"],
    }


@pytest.mark.asyncio
async def test_luma_client_joins_path_and_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    settings = Settings(luma_api_key="k", luma_api_endpoint="https://api.test/v1/")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = LumaClient(http, settings)
        await client.get("/event/get", {"id": "a b"})
    assert seen[0].url.path == "/v1/event/get"
    assert seen[0].url.params["id"] == "a b"


def test_settings_rejects_non_https_endpoint() -> None:
    with pytest.raises(ValidationError):
        Settings(luma_api_endpoint="http://insecure.test/v1")


@pytest.mark.asyncio
async def test_download_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="must start with http"):
        await download_image_to_temp("file:///etc/passwd")


@pytest.mark.asyncio
async def test_download_suffix_ignores_query_and_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda _r: httpx.Response(
            200, content=b"x", headers={"content-type": "application/octet-stream"}
        )
    )
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    path = await download_image_to_temp("https://cdn.test/a/pic.png?x=1.jpg#frag.gif")
    try:
        assert path.suffix == ".png"
    finally:
        path.unlink(missing_ok=True)
