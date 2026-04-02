"""Typed configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


def _default_token_cache_dir() -> Path:
    """Return the default token cache directory (evaluated at runtime, not import time)."""
    return Path.home() / ".config" / "pulumi-events"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables prefixed with PULUMI_EVENTS_."""

    model_config = SettingsConfigDict(env_prefix="PULUMI_EVENTS_")

    # -- Secrets (use .get_secret_value() to read) --
    meetup_client_id: SecretStr = SecretStr("")
    meetup_client_secret: SecretStr = SecretStr("")
    luma_api_key: SecretStr = SecretStr("")
    auth_token: SecretStr = SecretStr("")
    google_client_id: SecretStr = SecretStr("")
    google_client_secret: SecretStr = SecretStr("")

    # -- Endpoint URLs (validated to start with https://) --
    meetup_graphql_endpoint: str = "https://api.meetup.com/gql-ext"
    meetup_graphql_endpoint_v2: str = "https://api.meetup.com/gql2"
    luma_api_endpoint: str = "https://public-api.luma.com/v1"
    meetup_auth_endpoint: str = "https://secure.meetup.com/oauth2/authorize"
    meetup_token_endpoint: str = "https://secure.meetup.com/oauth2/access"

    # Redirect URI kept as plain str — may use http:// or custom schemes.
    meetup_redirect_uri: str = "http://127-0-0-1.nip.io:8080/auth/meetup/callback"

    token_cache_dir: Path = Path()  # replaced by validator below
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    auto_open_browser: bool = False
    meetup_pro_network_urlname: str = "pugs"

    # -- Deployment settings --
    base_url: str = ""  # e.g. "https://d1234abcd.cloudfront.net"
    meetup_token_backend: str = "file"  # "file" | "env"
    meetup_token_json: SecretStr = SecretStr("")  # token JSON for "env" backend

    # -- Meetup JWT auth (headless, server-to-server) --
    meetup_jwt_signing_key: SecretStr = SecretStr("")  # RSA private key PEM
    meetup_jwt_key_id: str = ""  # signing key ID (kid)
    meetup_member_id: str = ""  # Meetup member ID (sub claim)

    @field_validator(
        "meetup_graphql_endpoint",
        "meetup_graphql_endpoint_v2",
        "luma_api_endpoint",
        "meetup_auth_endpoint",
        "meetup_token_endpoint",
    )
    @classmethod
    def _validate_https_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            msg = f"Endpoint URL must start with https://, got: {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("token_cache_dir", mode="before")
    @classmethod
    def _default_cache_dir(cls, v: object) -> object:
        """Use Path.home() default only when no value is provided."""
        if v is None or v == "" or v == Path():
            return _default_token_cache_dir()
        return v
