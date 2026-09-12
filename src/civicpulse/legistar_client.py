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

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from civicpulse.config import CITY_ID, LEGISTAR_BASE_URL

REQUEST_TIMEOUT_SECONDS = 15
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# A real snapshot pulled from the live feed, kept on disk so a demo never
# depends on the government site being reachable at the time. Refresh it by
# running scripts/save_fallback_snapshot.py; this is real data (not
# synthetic), just captured at a point in time rather than fetched live.
FALLBACK_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fallback" / "agenda_snapshot.json"


def _get(path: str, params: dict | None = None) -> list | dict:
    """Issue a GET against the Legistar API and return decoded JSON.

    Government sites are not built for reliability demos: a dropped
    connection here should not be treated the same as a real 404 or 500, so
    transient network errors get a few short retries before giving up.
    Raises on a genuine non-2xx response so callers see a clear failure
    instead of silently getting an empty result.
    """
    url = f"{LEGISTAR_BASE_URL}/{path}"
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise last_error


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
                try:
                    item["attachments"] = [
                        {"name": a.get("MatterAttachmentName"), "url": a.get("MatterAttachmentHyperlink")}
                        for a in get_matter_attachments(matter_id)
                    ]
                except requests.exceptions.RequestException:
                    # Attachments are a nice-to-have next to the item's own
                    # source_url; one flaky call here should not sink an
                    # otherwise-successful pull of the rest of the agenda.
                    pass
            items.append(item)
    return items


def save_fallback_snapshot(body_id: int, days_ahead: int = 30) -> int:
    """Pull a real, current agenda and save it as the demo fallback snapshot.

    Meant to be run manually (see scripts/save_fallback_snapshot.py) a short
    while before a demo, not called as part of the regular ingestion loop.
    Returns the number of items saved.
    """
    items = fetch_agenda(body_id, days_ahead=days_ahead)
    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "body_id": body_id,
        "items": items,
    }
    FALLBACK_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2))
    return len(items)


def fetch_agenda_with_fallback(body_id: int, days_ahead: int = 30) -> dict:
    """Fetch the live agenda, falling back to the cached snapshot on failure.

    This is the function the agent's core loop should call. It tries the
    real feed first so day-to-day runs always see current data, and only
    drops to the cached snapshot if the live site is genuinely unreachable,
    so a demo is never at the mercy of a government website's uptime.

    Returns {"source": "live" or "cached_snapshot", "as_of": an ISO
    timestamp, "items": the agenda items}. "as_of" matters as much as the
    items themselves: on a cache hit it is the moment the snapshot was
    captured, not now, and callers must reason about meeting dates and
    deadlines relative to it, not to today's real date, or a stale snapshot
    can confidently report a comment window as "still open" after it has
    actually closed.
    """
    try:
        items = fetch_agenda(body_id, days_ahead=days_ahead)
        return {"source": "live", "as_of": datetime.now(timezone.utc).isoformat(), "items": items}
    except requests.exceptions.RequestException as e:
        if not FALLBACK_SNAPSHOT_PATH.exists():
            raise
        print(f"Warning: live Legistar fetch failed ({e}); using cached fallback snapshot.")
        snapshot = json.loads(FALLBACK_SNAPSHOT_PATH.read_text())
        return {"source": "cached_snapshot", "as_of": snapshot["fetched_at_utc"], "items": snapshot["items"]}
