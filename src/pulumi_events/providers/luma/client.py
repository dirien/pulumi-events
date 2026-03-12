"""Async REST client for the Luma public API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import anyio

from pulumi_events.exceptions import AuthenticationError, ProviderError
from pulumi_events.utils import guess_image_content_type

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

    from pulumi_events.settings import Settings

__all__ = ["LumaClient"]

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 10


class LumaClient:
    """Low-level async HTTP client for the Luma REST API."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._base = settings.luma_api_endpoint
        self._api_key = settings.luma_api_key

    @property
    def is_authenticated(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            msg = "Luma API key not configured — set PULUMI_EVENTS_LUMA_API_KEY"
            raise AuthenticationError(msg)
        return {"x-luma-api-key": self._api_key}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request against the Luma API."""
        resp = await self._http.get(
            f"{self._base}{path}",
            params=params,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a POST request against the Luma API."""
        resp = await self._http.post(
            f"{self._base}{path}",
            json=json,
            headers=self._headers(),
        )
        return self._handle_response(resp)

    async def get_all_pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated Luma endpoint.

        Collects ``entries`` arrays across pages until ``has_more`` is false,
        the *max_pages* safety cap is reached, or *limit* total items have
        been collected.
        """
        all_entries: list[dict[str, Any]] = []
        cursor: str | None = None
        params = dict(params) if params else {}

        for _ in range(max_pages):
            if cursor is not None:
                params["pagination_cursor"] = cursor

            page = await self.get(path, params or None)
            entries = page.get("entries", [])
            all_entries.extend(entries)

            if limit is not None and len(all_entries) >= limit:
                all_entries = all_entries[:limit]
                break

            if not page.get("has_more", False):
                break

            cursor = page.get("next_cursor")
            if not cursor:
                break

        return all_entries

    async def upload_image(self, file_path: Path) -> str:
        """Upload a local image to Luma CDN. Returns the CDN URL."""
        apath = anyio.Path(file_path)
        if not await apath.is_file():
            msg = f"Image file not found: {file_path}"
            raise ProviderError(msg)

        content_type = guess_image_content_type(file_path)
        try:
            file_bytes = await apath.read_bytes()
        except OSError as exc:
            msg = f"Failed to read image file {file_path}: {exc}"
            raise ProviderError(msg) from exc

        # Step 1: get a presigned upload URL
        data = await self.post("/images/create-upload-url", json={"purpose": "event-cover"})
        upload_url = data.get("upload_url") or data.get("url")
        cdn_url = data.get("file_url") or data.get("image_url")
        if not upload_url or not cdn_url:
            msg = f"Unexpected Luma upload response: {data}"
            raise ProviderError(msg)

        # Step 2: PUT the binary to the presigned URL
        resp = await self._http.put(
            upload_url,
            content=file_bytes,
            headers={"Content-Type": content_type},
        )
        if resp.status_code >= 400:
            msg = f"Luma image upload failed ({resp.status_code}): {resp.text}"
            raise ProviderError(msg)

        return cdn_url

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            try:
                body = resp.json()
                message = body.get("message", resp.text)
            except Exception:
                message = resp.text
            msg = f"Luma API error ({resp.status_code}): {message}"
            raise ProviderError(msg)
        return resp.json()
