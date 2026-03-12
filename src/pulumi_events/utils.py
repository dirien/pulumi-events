"""Shared utilities for pulumi-events."""

from __future__ import annotations

import logging
from pathlib import Path

__all__ = ["guess_image_content_type"]

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
