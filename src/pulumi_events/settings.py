"""Typed configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables prefixed with PULUMI_EVENTS_."""

    model_config = SettingsConfigDict(env_prefix="PULUMI_EVENTS_")

    meetup_client_id: str = ""
    meetup_client_secret: str = ""
    meetup_graphql_endpoint: str = "https://api.meetup.com/gql-ext"
    luma_api_key: str = ""
    luma_api_endpoint: str = "https://public-api.luma.com/v1"
    meetup_auth_endpoint: str = "https://secure.meetup.com/oauth2/authorize"
    meetup_token_endpoint: str = "https://secure.meetup.com/oauth2/access"
    meetup_redirect_uri: str = "http://127-0-0-1.nip.io:8080/auth/meetup/callback"
    token_cache_dir: Path = Path.home() / ".config" / "pulumi-events"
    server_host: str = "127.0.0.1"
    server_port: int = 8080
