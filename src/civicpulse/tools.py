"""The five Strands tools that make up the CivicPulse agent's toolset.

fetch_agenda is plain data retrieval. The other four are genuine reasoning
calls to Claude: each one is deliberately scoped to a single judgment
(relevance, urgency, plain-language summary, or a neutral comment draft) so
its prompt, and its failure modes, stay legible and easy to check against
real agenda items.
"""

from strands import tool

from civicpulse.bedrock_client import invoke, invoke_json
from civicpulse.config import COUNCIL_BODY_ID, NEIGHBORHOOD_PRIORITIES
from civicpulse.legistar_client import fetch_agenda as _fetch_agenda


@tool
def fetch_agenda(days_ahead: int = 30) -> list[dict]:
    """Fetch upcoming San Jose City Council agenda items from the live Legistar feed.

    Args:
        days_ahead: how many days ahead of today to look for published meeting agendas.
    """
    return _fetch_agenda(COUNCIL_BODY_ID, days_ahead=days_ahead)


@tool
def assess_relevance(item_text: str) -> dict:
    """Judge whether an agenda item is relevant to any neighborhood priority.

    This is a semantic reasoning call, not a keyword match: an item can
    match a priority even when it shares no words with it (a zoning
    variance can be an affordable-housing item), and can share words with a
    priority while being unrelated to it (a "reasonable accommodation"
    zoning item is disability access, not affordable housing). If an item
    plausibly affects a priority in conflicting ways, say so honestly
    rather than picking a side.

    Args:
        item_text: the agenda item's title and any other descriptive text available.
    """
    priorities_text = "\n".join(f"- {p['name']}: {p['description']}" for p in NEIGHBORHOOD_PRIORITIES)
    system_prompt = (
        "You are assessing whether a city government agenda item is relevant "
        "to a neighborhood group's stated priorities. Judge by what the item "
        "actually does, not by shared keywords. If an item plausibly affects "
        "a priority in conflicting ways (for example, more housing supply "
        "but also more parking pressure), say so honestly instead of picking "
        "a side. Do not force a match just because a priority exists on the "
        "list; a genuinely unrelated item should come back not relevant. "
        "Respond with only JSON, no other text, of exactly this form: "
        '{"relevant": true or false, "matched_priorities": [list of matching '
        'priority names, empty if none], "reasoning": "one or two plain '
        'language sentences explaining the judgment"}'
    )
    user_content = f"Neighborhood priorities:\n{priorities_text}\n\nAgenda item:\n{item_text}"
    return invoke_json(system_prompt, user_content)


@tool
def classify_urgency(item_text: str, meeting_date: str, is_consent: bool) -> dict:
    """Judge how time-sensitive an agenda item is.

    Legistar does not reliably expose a structured public-comment deadline,
    so this reasons from the meeting date and the item's consent status
    instead of a claimed deadline, and the caller must still tell the human
    to verify any date on the primary source. A consent-calendar item passes
    automatically as part of a batch vote unless someone requests it be
    pulled for individual discussion before the meeting, so the actionable
    step for a consent item is "request it be pulled," not "a vote is
    imminent, comment now."

    Args:
        item_text: the agenda item's title and any other descriptive text available.
        meeting_date: the date (YYYY-MM-DD) of the meeting this item is on.
        is_consent: whether the item is on the consent calendar.
    """
    system_prompt = (
        "You are classifying the urgency of a city government agenda item "
        "for a resident who does not have time to track every meeting. "
        "A consent-calendar item passes automatically as part of a batch "
        "vote unless someone requests it be pulled for individual discussion "
        "before the meeting; for those items the actionable step is "
        "requesting it be pulled, not commenting on an open vote. "
        "Classify the level as exactly one of: now, digest, ignore. Use "
        "'now' only when there is a genuinely imminent, specific action a "
        "person could still take given the meeting date. Use 'ignore' for "
        "routine or purely informational items with no real decision at "
        "stake. Never state a specific comment deadline as fact; you were "
        "not given one. Respond with only JSON, no other text, of exactly "
        'this form: {"level": "now" or "digest" or "ignore", "reason": '
        '"one sentence explaining the judgment"}'
    )
    user_content = (
        f"Meeting date: {meeting_date}\n"
        f"On consent calendar: {is_consent}\n"
        f"Agenda item:\n{item_text}"
    )
    return invoke_json(system_prompt, user_content)


@tool
def summarize_plain_language(item_text: str) -> str:
    """Summarize an agenda item in two to three plain-language sentences.

    States what the item does and, if identifiable, who is proposing it,
    instead of restating the agenda's legal or zoning-code language.

    Args:
        item_text: the agenda item's title and any other descriptive text available.
    """
    system_prompt = (
        "Summarize this city government agenda item in two to three plain "
        "language sentences for a resident with no policy background. State "
        "what the item actually does and, if identifiable from the text, "
        "who is proposing it. Do not restate legal or zoning-code language "
        "verbatim. Describe it neutrally; do not say whether it is good or "
        "bad. Respond with only the summary text, no preamble."
    )
    return invoke(system_prompt, item_text, max_tokens=300)


@tool
def draft_comment(item_text: str, matched_priorities: list[str]) -> str:
    """Draft a neutral public-comment template for a human to personalize and submit.

    Presents trade-offs honestly rather than advocating a position: if the
    item plausibly helps one stated priority while working against another,
    the draft says so explicitly instead of picking a side. Never states a
    submission method or deadline as fact, since neither is reliably known
    from the agenda feed alone.

    Args:
        item_text: the agenda item's title and any other descriptive text available.
        matched_priorities: the neighborhood priority names this item was judged relevant to.
    """
    system_prompt = (
        "Draft a neutral public-comment template about this city government "
        "agenda item, for a resident to personalize and submit themselves. "
        "Present relevant trade-offs honestly rather than advocating for or "
        "against the item: if it plausibly helps one stated priority while "
        "working against another, say so explicitly instead of picking a "
        "side. Never state a specific deadline or submission method as "
        "fact; instead instruct the reader to verify the current deadline "
        "and submission process on the primary agenda source. Leave a "
        "bracketed placeholder for the reader's own personal reason for "
        "caring about this item. Respond with only the draft text."
    )
    priorities_text = ", ".join(matched_priorities) if matched_priorities else "the flagged priority"
    user_content = f"Priorities this item matches: {priorities_text}\n\nAgenda item:\n{item_text}"
    return invoke(system_prompt, user_content, max_tokens=400)
