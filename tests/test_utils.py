"""Unit tests for utils helpers, specifically download_image_to_temp."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from pulumi_events.utils import download_image_to_temp


def _mock_transport(
    *, content: bytes = b"fake-image-bytes", content_type: str = "image/png", status: int = 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(status, content=content, headers=headers)

    return httpx.MockTransport(handler)


class TestDownloadImageToTemp:
    """Covers the URL-to-temp-file helper used by create/edit event tools."""

    @pytest.mark.asyncio
    async def test_http_url_required(self) -> None:
        with pytest.raises(ValueError, match="must start with http"):
            await download_image_to_temp("ftp://example.com/img.png")

    @pytest.mark.asyncio
    async def test_empty_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="must start with http"):
            await download_image_to_temp("")

    @pytest.mark.asyncio
    async def test_png_downloads_and_returns_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        content = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
        monkeypatch.setattr(
            httpx, "AsyncClient", _patched_async_client(_mock_transport(content=content))
        )
        result = await download_image_to_temp("https://cdn.example.com/banner.png")
        try:
            assert result.exists()
            assert result.suffix == ".png"
            assert result.read_bytes() == content
        finally:
            result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_jpeg_content_type_maps_to_jpg_suffix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            _patched_async_client(_mock_transport(content_type="image/jpeg")),
        )
        result = await download_image_to_temp("https://cdn.example.com/banner")
        try:
            assert result.suffix == ".jpg"
        finally:
            result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_unsupported_content_type_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            _patched_async_client(_mock_transport(content_type="application/pdf")),
        )
        with pytest.raises(ValueError, match="Unsupported image content type"):
            await download_image_to_temp("https://cdn.example.com/doc")

    @pytest.mark.asyncio
    async def test_generic_content_type_falls_back_to_url_suffix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Some CDNs return application/octet-stream but the URL's extension
        # tells us the real format. Accept it if the suffix is recognised.
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            _patched_async_client(_mock_transport(content_type="application/octet-stream")),
        )
        result = await download_image_to_temp("https://cdn.example.com/banner.png")
        try:
            assert result.suffix == ".png"
        finally:
            result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_oversized_image_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        huge = b"\x00" * (21 * 1024 * 1024)  # 21 MB, over the 20 MB limit
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            _patched_async_client(_mock_transport(content=huge)),
        )
        with pytest.raises(ValueError, match="exceeds limit"):
            await download_image_to_temp("https://cdn.example.com/huge.png")

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            _patched_async_client(_mock_transport(status=404)),
        )
        with pytest.raises(httpx.HTTPStatusError):
            await download_image_to_temp("https://cdn.example.com/missing.png")

    @pytest.mark.asyncio
    async def test_follows_redirects(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # A 301 should transparently land on the final image.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/short":
                return httpx.Response(
                    301, headers={"location": "https://cdn.example.com/final.png"}
                )
            return httpx.Response(
                200, content=b"final-image", headers={"content-type": "image/png"}
            )

        monkeypatch.setattr(
            httpx, "AsyncClient", _patched_async_client(httpx.MockTransport(handler))
        )
        result = await download_image_to_temp("https://cdn.example.com/short")
        try:
            assert result.read_bytes() == b"final-image"
        finally:
            result.unlink(missing_ok=True)


def _patched_async_client(
    transport: httpx.MockTransport,
) -> Callable[..., httpx.AsyncClient]:
    """Return a factory that mimics httpx.AsyncClient but uses a mock transport.

    We swap the module-level ``httpx.AsyncClient`` at import time so the
    helper under test transparently uses our transport without altering its
    source.
    """
    original = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return original(*args, transport=transport, **kwargs)  # type: ignore[arg-type]

    return factory
