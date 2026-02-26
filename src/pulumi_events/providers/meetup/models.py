"""Pydantic models for Meetup GraphQL response types."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "EventNode",
    "GraphQLError",
    "GroupNode",
    "MeetupSelf",
    "NetworkNode",
    "PageInfo",
    "PaginatedResponse",
    "VenueNode",
]


class GraphQLError(BaseModel):
    """A single error from a GraphQL response."""

    message: str
    code: str | None = None
    field: str | None = None


class PageInfo(BaseModel):
    """Cursor-based pagination info."""

    has_next_page: bool = Field(alias="hasNextPage")
    end_cursor: str | None = Field(default=None, alias="endCursor")


class VenueNode(BaseModel):
    """Venue data."""

    id: str | None = None
    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    lat: float | None = None
    lng: float | None = None


class GroupNode(BaseModel):
    """Minimal group data returned in search / event results."""

    id: str | None = None
    name: str | None = None
    urlname: str | None = None
    city: str | None = None
    country: str | None = None
    description: str | None = None
    member_count: int | None = None


class EventNode(BaseModel):
    """Event data returned in search results."""

    id: str
    title: str | None = None
    date_time: str | None = Field(default=None, alias="dateTime")
    duration: str | None = None
    going: int | None = None
    event_url: str | None = Field(default=None, alias="eventUrl")
    status: str | None = None
    group: GroupNode | None = None
    venue: VenueNode | None = None


class MeetupSelf(BaseModel):
    """Authenticated user info."""

    id: str
    name: str
    group_count: int | None = None


class NetworkNode(BaseModel):
    """Pro network info."""

    id: str
    name: str
    urlname: str
    description: str | None = None
    status: str | None = None
    link: str | None = None


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""

    total_count: int = Field(alias="totalCount")
    page_info: PageInfo = Field(alias="pageInfo")
    edges: list[dict[str, object]]
