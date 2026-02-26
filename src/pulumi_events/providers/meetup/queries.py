"""GraphQL query and mutation string constants for Meetup API."""

from __future__ import annotations

__all__ = [
    "ANNOUNCE_EVENT",
    "CLOSE_EVENT_RSVPS",
    "CREATE_EVENT",
    "CREATE_VENUE",
    "DELETE_EVENT",
    "EVENT_BY_ID",
    "GROUP_BY_URLNAME",
    "GROUP_MEMBERS",
    "GROUP_MEMBER_BY_ID",
    "LIST_MY_GROUPS",
    "NETWORK_BY_URLNAME",
    "NETWORK_SEARCH_EVENTS",
    "NETWORK_SEARCH_GROUPS",
    "NETWORK_SEARCH_MEMBERS",
    "OPEN_EVENT_RSVPS",
    "PUBLISH_EVENT",
    "SEARCH_EVENTS",
    "SEARCH_GROUPS",
    "SELF_QUERY",
    "UPDATE_EVENT",
]

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

SELF_QUERY = """
query {
  self {
    id
    name
    memberships {
      totalCount
    }
  }
}
"""

GROUP_BY_URLNAME = """
query($urlname: String!) {
  groupByUrlname(urlname: $urlname) {
    id
    name
    urlname
    description
    city
    country
    latitude
    longitude
    memberships {
      totalCount
    }
    link
    timezone
    logo {
      baseUrl
    }
  }
}
"""

EVENT_BY_ID = """
query($eventId: ID!) {
  event(id: $eventId) {
    id
    title
    description
    dateTime
    duration
    endTime
    eventUrl
    status
    going
    maxTickets
    rsvpSettings {
      rsvpOpenTime
      rsvpCloseTime
      rsvpLimit
    }
    venue {
      id
      name
      address
      city
      state
      country
      lat
      lng
    }
    group {
      id
      name
      urlname
    }
    hosts {
      id
      name
    }
  }
}
"""

NETWORK_BY_URLNAME = """
query($urlname: String!) {
  proNetworkByUrlname(urlname: $urlname) {
    id
    name
    urlname
    description
    groupCount
    memberCount
    logo {
      baseUrl
    }
  }
}
"""

LIST_MY_GROUPS = """
query($first: Int, $after: String) {
  self {
    memberships(first: $first, after: $after) {
      totalCount
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          id
          name
          urlname
          city
          country
          memberships {
            totalCount
          }
        }
      }
    }
  }
}
"""

SEARCH_EVENTS = """
query(
  $query: String!,
  $first: Int,
  $after: String,
  $lat: Float,
  $lon: Float,
  $startDateRange: ZonedDateTime,
  $endDateRange: ZonedDateTime,
  $eventType: EventType
) {
  searchEvents(
    input: {
      query: $query,
      first: $first,
      after: $after,
      lat: $lat,
      lon: $lon,
      startDateRange: $startDateRange,
      endDateRange: $endDateRange,
      eventType: $eventType
    }
  ) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        dateTime
        duration
        going
        eventUrl
        group {
          name
          urlname
        }
        venue {
          name
          city
          country
        }
      }
    }
  }
}
"""

SEARCH_GROUPS = """
query($query: String!, $first: Int, $after: String, $lat: Float, $lon: Float) {
  searchGroups(
    input: {
      query: $query,
      first: $first,
      after: $after,
      lat: $lat,
      lon: $lon
    }
  ) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        urlname
        city
        country
        description
        memberships {
          totalCount
        }
      }
    }
  }
}
"""

NETWORK_SEARCH_EVENTS = """
query(
  $urlname: String!,
  $query: String,
  $status: ProNetworkEventStatus,
  $first: Int,
  $after: String
) {
  proNetworkByUrlname(urlname: $urlname) {
    eventsSearch(input: { query: $query, status: $status, first: $first, after: $after }) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id title dateTime going eventUrl
          group { name urlname }
        }
      }
    }
  }
}
"""

NETWORK_SEARCH_GROUPS = """
query($urlname: String!, $query: String, $first: Int, $after: String) {
  proNetworkByUrlname(urlname: $urlname) {
    groupsSearch(input: { query: $query, first: $first, after: $after }) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id name urlname city country
          memberships { totalCount }
        }
      }
    }
  }
}
"""

NETWORK_SEARCH_MEMBERS = """
query($urlname: String!, $query: String, $first: Int, $after: String) {
  proNetworkByUrlname(urlname: $urlname) {
    membersSearch(input: { query: $query, first: $first, after: $after }) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id name
        }
      }
    }
  }
}
"""

GROUP_MEMBERS = """
query(
  $urlname: String!,
  $first: Int,
  $after: String,
  $status: [MembershipStatus!]
) {
  groupByUrlname(urlname: $urlname) {
    memberships(first: $first, after: $after, filter: { status: $status }) {
      totalCount
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          id
          name
          bio
          city
          country
          memberUrl
          username
          isOrganizer
          memberPhoto {
            baseUrl
          }
        }
        metadata {
          role
          joinTime
          status
          bio
          lastAccessTime
        }
      }
    }
  }
}
"""

GROUP_MEMBER_BY_ID = """
query($urlname: String!, $memberIds: [ID!]) {
  groupByUrlname(urlname: $urlname) {
    memberships(filter: { memberIds: $memberIds }) {
      edges {
        node {
          id
          name
          bio
          city
          country
          memberUrl
          username
          isOrganizer
          memberPhoto {
            baseUrl
          }
        }
        metadata {
          role
          joinTime
          status
          bio
          lastAccessTime
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

CREATE_EVENT = """
mutation($input: CreateEventInput!) {
  createEvent(input: $input) {
    event {
      id
      title
      dateTime
      eventUrl
      status
      group {
        urlname
      }
    }
    errors {
      message
      code
      field
    }
  }
}
"""

UPDATE_EVENT = """
mutation($input: EditEventInput!) {
  editEvent(input: $input) {
    event {
      id
      title
      dateTime
      eventUrl
      status
    }
    errors {
      message
      code
      field
    }
  }
}
"""

DELETE_EVENT = """
mutation($input: DeleteEventInput!) {
  deleteEvent(input: $input) {
    success
    errors {
      message
      code
    }
  }
}
"""

PUBLISH_EVENT = """
mutation($input: PublishEventInput!) {
  publishEvent(input: $input) {
    event {
      id
      title
      status
      eventUrl
    }
    errors {
      message
      code
    }
  }
}
"""

ANNOUNCE_EVENT = """
mutation($input: AnnounceEventInput!) {
  announceEvent(input: $input) {
    success
    errors {
      message
      code
    }
  }
}
"""

CLOSE_EVENT_RSVPS = """
mutation($input: CloseEventRsvpsInput!) {
  closeEventRsvps(input: $input) {
    event {
      id
      rsvpSettings {
        rsvpLimit
      }
    }
    errors {
      message
      code
    }
  }
}
"""

OPEN_EVENT_RSVPS = """
mutation($input: OpenEventRsvpsInput!) {
  openEventRsvps(input: $input) {
    event {
      id
      rsvpSettings {
        rsvpLimit
      }
    }
    errors {
      message
      code
    }
  }
}
"""

CREATE_VENUE = """
mutation($input: CreateVenueInput!) {
  createVenue(input: $input) {
    venue {
      id
      name
      address
      city
      country
    }
    errors {
      message
      code
      field
    }
  }
}
"""
