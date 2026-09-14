"""Wires the five tools into a single Strands agent and runs the core loop:
fetch new items, judge relevance, judge urgency, summarize, and draft a
comment when warranted. Nothing here ever sends, posts, or submits
anything; the output is a static digest page for a human to read and act
on themselves.
"""

import re
from datetime import datetime, timezone

from civicpulse.config import (
    ANTHROPIC_MODEL_ID,
    BEDROCK_MODEL_ID,
    BEDROCK_REGION,
    COUNCIL_BODY_ID,
    MODEL_PROVIDER,
)
from civicpulse.digest import render_digest
from civicpulse.legistar_client import fetch_agenda_with_fallback
from civicpulse.schemas import AgendaJudgments, ItemAssessment
from civicpulse.storage import filter_unseen, mark_seen
from civicpulse.tools import (
    assess_relevance,
    classify_urgency,
    draft_comment,
    fetch_agenda,
    summarize_plain_language,
)

SYSTEM_PROMPT = (
    "You are CivicPulse, an agent that helps a neighborhood group notice "
    "city government decisions that matter to them without having to read "
    "every agenda themselves. You will be given a reference date to treat "
    "as 'today'; always pass it as the reference_date argument every time "
    "you call classify_urgency, since the agenda data may come from a "
    "cached snapshot rather than a live fetch. For each agenda item you "
    "are given: call assess_relevance to judge whether it matches a stated "
    "priority. Only if it is relevant, call classify_urgency; never call "
    "classify_urgency for an item assess_relevance found not relevant, and "
    "never invent an urgency judgment for one. If the level is 'now' or "
    "'digest', call summarize_plain_language. Call draft_comment only when "
    "the level is exactly 'now'; never call it for a 'digest' or 'ignore' "
    "item, since a ready-to-send draft implies urgency that item does not "
    "have. In your final answer, report on every "
    "item you were given, one entry per item, using its matter_file "
    "exactly as given so it can be matched back to the source record; do "
    "not restate its title, meeting date, or source link yourself. For an "
    "item that is not relevant, leave urgency_level, urgency_reason, "
    "summary, and draft_comment unset. Never state a public comment "
    "deadline as a fact. Never use emojis anywhere in your reasoning or in "
    "any field of your answer."
)


def build_agent():
    """Construct the CivicPulse Strands agent. Imported lazily by callers so
    modules that don't need Bedrock (like the tests for individual tools)
    never have to import strands.models.

    Provider selection mirrors bedrock_client.py: MODEL_PROVIDER=anthropic
    routes the agent's own orchestrating model through the Anthropic API
    directly instead of Bedrock, for the same reason (an AWS-account-level
    Bedrock access issue, not anything provider-agnostic in the agent
    logic, tools, or schemas). See config.py and the README for why this
    switch exists.
    """
    from strands import Agent

    if MODEL_PROVIDER == "anthropic":
        from strands.models.anthropic import AnthropicModel

        model = AnthropicModel(model_id=ANTHROPIC_MODEL_ID, max_tokens=4096)
    else:
        from strands.models import BedrockModel

        model = BedrockModel(model_id=BEDROCK_MODEL_ID, region_name=BEDROCK_REGION)
    return Agent(
        model=model,
        tools=[fetch_agenda, assess_relevance, classify_urgency, summarize_plain_language, draft_comment],
        system_prompt=SYSTEM_PROMPT,
    )


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # pictographs, emoticons, transport, supplemental symbols
    "\U00002600-\U000027BF"  # misc symbols and dingbats
    "\U00002300-\U000023FF"  # misc technical (includes things like the pause/stop glyphs)
    "\U0001F1E6-\U0001F1FF"  # regional indicator symbols (flag letters)
    "\U0000FE0F"  # variation selector-16, forces emoji presentation
    "]+"
)


def _sanitize(text: str | None) -> str | None:
    """Strip emojis and em dashes from model-generated text before it ever
    reaches the digest. The system prompt already asks the model to avoid
    both, but that is a request, not a guarantee, and both are hard project
    rules for anything the project produces, model output included.
    """
    if text is None:
        return None
    text = _EMOJI_PATTERN.sub("", text)
    text = text.replace("—", ", ")
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _format_item(item: dict) -> str:
    """Render one raw agenda item as plain text for the agent's prompt."""
    return (
        f"[{item['matter_file']}] {item['title']}\n"
        f"Type: {item['matter_type']} (consent: {item['is_consent']})\n"
        f"Meeting date: {item['meeting_date']}\n"
        f"Source: {item['source_url']}"
    )


def _data_source_note(source: str, as_of: str) -> str:
    """One line stating where this run's data came from and how stale it is.

    Always present, and never left to the model to remember or phrase: a
    judge (or the presenter mid-demo) asking "is this live?" should get a
    reliable answer from the tool's own output, not from memory of which
    mode was running.
    """
    if source == "live":
        return f"live San Jose Legistar feed (fetched {as_of} UTC)"

    as_of_dt = datetime.fromisoformat(as_of)
    days_stale = (datetime.now(timezone.utc) - as_of_dt).days
    return (
        f"CACHED SNAPSHOT from {as_of} UTC (~{days_stale} day(s) old); "
        "the live feed was unreachable. All dates below are reasoned "
        "relative to the snapshot date, not today's actual date."
    )


def run_once(days_ahead: int = 30) -> AgendaJudgments | None:
    """Run one ingestion pass end to end and write the digest page.

    Fetching and seen-item filtering happen in plain Python, not as an agent
    tool call: there is no judgment involved in either step, so there is
    nothing to gain from routing them through the model, and it keeps the
    agent from re-spending tokens re-fetching what we already have.

    Returns None (and leaves any previous digest untouched) when there is
    nothing new to report, matching how a digest is supposed to behave: no
    new items means no new digest, not an emptied-out one.
    """
    fetched = fetch_agenda_with_fallback(COUNCIL_BODY_ID, days_ahead=days_ahead)
    source, as_of = fetched["source"], fetched["as_of"]
    data_source_note = _data_source_note(source, as_of)
    reference_date = as_of[:10]  # "2026-09-12T01:34:39+00:00" -> "2026-09-12"

    items = filter_unseen(fetched["items"])
    if not items:
        print(f"No new agenda items since the last run. (checked {data_source_note})")
        return None

    agent = build_agent()
    prompt = (
        f"Reference date (treat as 'today'): {reference_date}\n\n"
        "Here are the new agenda items to assess:\n\n"
        + "\n\n".join(_format_item(item) for item in items)
    )
    result = agent(prompt, structured_output_model=AgendaJudgments)
    judgments = {j.matter_file: j for j in result.structured_output.items}

    # Merge the model's judgment fields with our own ground-truth item data
    # rather than trusting the model to restate facts about itself; see
    # schemas.py for why source links and dates never come from the LLM.
    assessed_items = []
    for item in items:
        judgment = judgments.get(item["matter_file"])
        if judgment is None:
            continue  # the model didn't report on this one; skip rather than guess
        # Non-relevant items were never passed to classify_urgency, so these
        # fields legitimately come back empty; fill in a plain "ignore" here
        # for the digest's grouping logic rather than leaving it null.
        urgency_level = judgment.urgency_level or "ignore"
        urgency_reason = judgment.urgency_reason or (
            "Not relevant to any stated priority; urgency was not assessed."
            if not judgment.relevant
            else "No urgency reasoning was provided."
        )
        # A ready-to-send draft implies urgency; enforce that invariant here
        # rather than trust the model always follows the system prompt's
        # "only draft for 'now' items" instruction, since it has not always.
        draft_comment_text = judgment.draft_comment if urgency_level == "now" else None
        assessed_items.append(
            ItemAssessment(
                matter_file=item["matter_file"],
                title=item["title"],
                meeting_date=item["meeting_date"],
                source_url=item["source_url"],
                is_consent=item["is_consent"],
                relevant=judgment.relevant,
                matched_priorities=judgment.matched_priorities,
                relevance_reasoning=_sanitize(judgment.relevance_reasoning),
                urgency_level=urgency_level,
                urgency_reason=_sanitize(urgency_reason),
                summary=_sanitize(judgment.summary),
                draft_comment=_sanitize(draft_comment_text),
            )
        )

    for item in items:
        mark_seen(item["matter_id"])

    digest_path = render_digest(assessed_items, data_source_note=data_source_note)
    print(f"Digest written to {digest_path}")
    return result.structured_output


if __name__ == "__main__":
    run_once()
