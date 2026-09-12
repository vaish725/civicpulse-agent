"""Thin client for the Legistar Web API (San Jose's public agenda system).

No Strands or Bedrock dependency here on purpose: this module only talks to
the real government data source, so it can be tested and iterated on without
touching the LLM at all. The `@tool`-wrapped version lives in tools.py.

Legistar's data model, relevant to us:
  Body    -> a legislative body (e.g. "City Council").
  Event   -> one meeting of a body, on a date, with a published agenda PDF.
  EventItem -> one line on that meeting's agenda. Most carry a Matter (the
               actual legislation/action); a few are boilerplate meeting
               instructions with no Matter attached, and we filter those out.
  Matter  -> the underlying legislative file (title, type, attachments).
"""

from datetime import datetime, timedelta, timezone

import requests

from civicpulse.config import CITY_ID, LEGISTAR_BASE_URL

REQUEST_TIMEOUT_SECONDS = 15


def _get(path: str, params: dict | None = None) -> list | dict:
    """Issue a GET against the Legistar API and return decoded JSON.

    Raises requests.HTTPError on a non-2xx response so callers (and the
    agent) see a clear failure instead of silently getting an empty result.
    """
    url = f"{LEGISTAR_BASE_URL}/{path}"
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def get_upcoming_events(body_id: int, days_ahead: int = 30) -> list[dict]:
    """Return meetings for a body between today and `days_ahead` from now.

    Only events with a published agenda PDF are returned: a meeting entry
    can exist in Legistar before its agenda is finalized, and an unpublished
    agenda has nothing yet for the agent to reason about.
    """
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days_ahead)
    odata_filter = (
        f"EventBodyId eq {body_id} "
        f"and EventDate ge datetime'{today.isoformat()}' "
        f"and EventDate le datetime'{end.isoformat()}'"
    )
    events = _get("events", params={"$filter": odata_filter, "$orderby": "EventDate asc"})
    return [e for e in events if e.get("EventAgendaFile")]


def get_event_items(event_id: int) -> list[dict]:
    """Return the raw agenda line items for one meeting."""
    return _get(f"events/{event_id}/eventitems")


def get_matter_attachments(matter_id: int) -> list[dict]:
    """Return linked documents (staff memos, ordinance text, etc.) for a matter."""
    return _get(f"matters/{matter_id}/attachments")


def _matter_detail_url(matter_id: int, matter_guid: str) -> str:
    """Build the public, human-readable Legistar page for one legislative file.

    This is the "verify this yourself" primary-source link the agent must
    always attach next to any relevance or urgency claim.
    """
    return f"https://{CITY_ID}.legistar.com/LegislationDetail.aspx?ID={matter_id}&GUID={matter_guid}"


def fetch_agenda(body_id: int, days_ahead: int = 30, include_attachments: bool = True) -> list[dict]:
    """Fetch and flatten upcoming agenda items for one body into a clean list.

    Combines the fetch and parse steps: boilerplate/instructional agenda
    lines (no attached Matter) are dropped, and each remaining item is
    enriched with its meeting date, source PDF, and a direct Legistar link,
    so downstream reasoning tools never have to touch raw Legistar shapes.
    """
    items = []
    for event in get_upcoming_events(body_id, days_ahead=days_ahead):
        meeting_date = event["EventDate"][:10]  # "2026-09-15T00:00:00" -> "2026-09-15"
        for raw in get_event_items(event["EventId"]):
            matter_id = raw.get("EventItemMatterId")
            if not matter_id:
                continue  # boilerplate line (translation instructions, etc.), not a real item

            matter_type = raw.get("EventItemMatterType") or ""
            item = {
                "matter_id": matter_id,
                "matter_file": raw.get("EventItemMatterFile"),
                "title": raw.get("EventItemTitle"),
                "matter_type": matter_type,
                "is_consent": "consent" in matter_type.lower(),
                "meeting_date": meeting_date,
                "meeting_body": event.get("EventBodyName"),
                "agenda_pdf_url": event.get("EventAgendaFile"),
                "source_url": _matter_detail_url(matter_id, raw.get("EventItemMatterGuid", "")),
                "attachments": [],
            }
            if include_attachments:
                item["attachments"] = [
                    {"name": a.get("MatterAttachmentName"), "url": a.get("MatterAttachmentHyperlink")}
                    for a in get_matter_attachments(matter_id)
                ]
            items.append(item)
    return items
