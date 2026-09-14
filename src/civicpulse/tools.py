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
def classify_urgency(item_text: str, meeting_date: str, is_consent: bool, reference_date: str) -> dict:
    """Judge how time-sensitive an agenda item is.

    Legistar does not reliably expose a structured public-comment deadline,
    so this reasons from the meeting date and the item's consent status
    instead of a claimed deadline, and the caller must still tell the human
    to verify any date on the primary source. A consent-calendar item passes
    automatically as part of a batch vote unless someone requests it be
    pulled for individual discussion before the meeting, so the actionable
    step for a consent item is "request it be pulled," not "a vote is
    imminent, comment now."

    reference_date must be passed explicitly rather than left for the model
    to assume: this tool is also used against a cached fallback snapshot
    when the live feed is down, where "today" is whenever the snapshot was
    captured, not the real current date. Judging "3 days away" against the
    wrong anchor date is exactly how a comment window gets reported as open
    after it has actually closed.

    Args:
        item_text: the agenda item's title and any other descriptive text available.
        meeting_date: the date (YYYY-MM-DD) of the meeting this item is on.
        is_consent: whether the item is on the consent calendar.
        reference_date: the date (YYYY-MM-DD) to treat as "today" for this judgment.
    """
    system_prompt = (
        "You are classifying the urgency of a city government agenda item "
        "for a resident who does not have time to track every meeting. "
        "You are given an explicit reference_date to treat as 'today'; do "
        "not substitute any other assumption about the current date, since "
        "this data may come from a cached snapshot captured on a different "
        "day than when you are running. Compute how many days away the "
        "meeting is from reference_date and reason from that.\n\n"
        "These two cases use different defaults; do not blend them:\n\n"
        "NON-CONSENT item: if it is scheduled for a specific vote or "
        "decision on a date that has not passed and has not been deferred "
        "or dropped, classify it as 'now'. That is enough by itself. Do "
        "NOT require the item's title or text to itself signal controversy, "
        "drama, or public interest before treating it as actionable: a "
        "specific tax or fee waiver for a named project, or a permit "
        "decision, is exactly the kind of real, imminent, individually-"
        "decided matter this exists to surface, even when it is described "
        "in flat administrative language. Requiring visible controversy "
        "before flagging an item would systematically miss the ones that "
        "matter most, since a routine-sounding title is exactly how a "
        "consequential decision hides in a government agenda.\n\n"
        "CONSENT-CALENDAR item: it passes automatically as part of a batch "
        "vote unless someone requests it be pulled for individual "
        "discussion before the meeting, so consent status is a genuine, "
        "distinct reason for a higher bar. Classify a consent item as "
        "'now' only if its own text shows a concrete signal of something "
        "non-routine (real controversy, meaningful cost, or an unusual "
        "provision) that would make requesting a pull worthwhile; "
        "otherwise 'digest' if still worth awareness, or 'ignore' if "
        "purely routine.\n\n"
        "Use 'ignore' for: purely informational items with no vote at all, "
        "items whose meeting date has already passed relative to "
        "reference_date, or items the text itself says have been deferred "
        "or dropped from the agenda.\n\n"
        "Never state a specific comment deadline as fact; you were not "
        "given one. Respond with only JSON, no other text, of exactly this "
        'form: {"level": "now" or "digest" or "ignore", "reason": "one '
        'sentence explaining the judgment, stated relative to reference_date"}'
    )
    user_content = (
        f"Reference date (treat as 'today'): {reference_date}\n"
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
