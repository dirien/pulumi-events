"""Shared utilities for pulumi-events."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import httpx

__all__ = ["download_image_to_temp", "guess_image_content_type"]

logger = logging.getLogger(__name__)

_IMAGE_CONTENT_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
}

_CONTENT_TYPE_TO_SUFFIX: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB — Meetup/Luma both accept up to this
_DOWNLOAD_TIMEOUT_SECONDS = 30.0


def guess_image_content_type(file_path: Path) -> str:
    """Return the MIME content type for an image file based on its extension.

    Falls back to ``image/jpeg`` and logs a warning if the extension is
    unrecognised.
    """
    content_type = _IMAGE_CONTENT_TYPES.get(file_path.suffix.lower())
    if content_type is None:
        content_type = "image/jpeg"
        logger.warning(
            "Could not determine MIME type for %s; defaulting to %s",
            file_path.name,
            content_type,
        )
    return content_type


async def download_image_to_temp(url: str) -> Path:
    """Fetch a remote image URL and write it to a temp file for upload.

    The MCP server typically runs on a different machine than the caller,
    so accepting a local file path is unreliable. Callers can provide a
    public URL instead; this helper downloads the bytes on the server side
    and returns a local ``Path`` that the existing upload flow can use.

    The caller is responsible for deleting the returned file once the
    upload is complete (``Path.unlink(missing_ok=True)``).

    Args:
        url: HTTP(S) URL pointing to an image. The response must have a
            supported ``Content-Type`` (jpeg/png/gif/webp/svg/avif).

    Raises:
        ValueError: if the URL is not http(s), the response is not OK,
            the content type is unsupported, or the image exceeds 20 MB.
    """
    if not url.startswith(("http://", "https://")):
        msg = f"Image URL must start with http:// or https://, got {url!r}"
        raise ValueError(msg)

    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as http:
        resp = await http.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        suffix = _CONTENT_TYPE_TO_SUFFIX.get(content_type)
        if suffix is None:
            # Fall back to the URL's path suffix — some CDNs return
            # generic "application/octet-stream" but the URL ends in .png.
            suffix = Path(url.split("?", 1)[0]).suffix.lower()
            if suffix not in _CONTENT_TYPE_TO_SUFFIX.values():
                msg = (
                    f"Unsupported image content type {content_type!r} at {url!r}. "
                    "Expected jpeg/png/gif/webp/svg/avif."
                )
                raise ValueError(msg)

        content = resp.content
        if len(content) > _MAX_IMAGE_BYTES:
            msg = (
                f"Image at {url!r} is {len(content)} bytes, "
                f"exceeds limit of {_MAX_IMAGE_BYTES} bytes (20 MB)."
            )
            raise ValueError(msg)

        # delete=False so we can close the handle and hand the Path to
        # downstream readers (e.g. anyio.Path(..).read_bytes()).
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded image from %s (%d bytes, %s) to %s",
            url,
            len(content),
            content_type or "unknown",
            tmp_path,
        )
        return tmp_path
