"""Wires the five tools into a single Strands agent and runs the core loop:
fetch new items, judge relevance, judge urgency, summarize, and draft a
comment when warranted. Nothing here ever sends, posts, or submits
anything; the return value is meant for a human review surface (digest
email, CLI output, etc.) that a person reads and acts on themselves.
"""

from civicpulse.config import BEDROCK_MODEL_ID, BEDROCK_REGION, COUNCIL_BODY_ID
from civicpulse.legistar_client import fetch_agenda as fetch_raw_agenda
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
    "every agenda themselves. For each agenda item you are given: call "
    "assess_relevance to judge whether it matches a stated priority. If it "
    "is not relevant, say so briefly and move on. If it is relevant, call "
    "classify_urgency. If the level is 'ignore', say so briefly and move "
    "on. If the level is 'now' or 'digest', call summarize_plain_language. "
    "If the level is specifically 'now', also call draft_comment. For every "
    "item you report on, state: the relevance verdict and its reasoning, "
    "the urgency level and its reason, the plain-language summary if one "
    "was produced, and the draft comment if one was produced, plus the "
    "item's source link. Never state a public comment deadline or "
    "submission method as a fact; always tell the reader to verify dates "
    "and how to submit on the primary agenda source before acting."
)


def build_agent():
    """Construct the CivicPulse Strands agent. Imported lazily by callers so
    modules that don't need Bedrock (like the tests for individual tools)
    never have to import strands.models.
    """
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=BEDROCK_MODEL_ID, region_name=BEDROCK_REGION)
    return Agent(
        model=model,
        tools=[fetch_agenda, assess_relevance, classify_urgency, summarize_plain_language, draft_comment],
        system_prompt=SYSTEM_PROMPT,
    )


def _format_item(item: dict) -> str:
    """Render one raw agenda item as plain text for the agent's prompt."""
    return (
        f"[{item['matter_file']}] {item['title']}\n"
        f"Type: {item['matter_type']} (consent: {item['is_consent']})\n"
        f"Meeting date: {item['meeting_date']}\n"
        f"Source: {item['source_url']}"
    )


def run_once(days_ahead: int = 30) -> str:
    """Run one ingestion pass end to end.

    Fetching and seen-item filtering happen in plain Python, not as an agent
    tool call: there is no judgment involved in either step, so there is
    nothing to gain from routing them through the model, and it keeps the
    agent from re-spending tokens re-fetching what we already have.
    """
    items = filter_unseen(fetch_raw_agenda(COUNCIL_BODY_ID, days_ahead=days_ahead))
    if not items:
        # Nothing else prints in this branch (the agent never runs, so there
        # is no console trace to duplicate), so this is the one place that
        # needs to say so itself.
        message = "No new agenda items since the last run."
        print(message)
        return message

    agent = build_agent()
    prompt = "Here are the new agenda items to assess:\n\n" + "\n\n".join(
        _format_item(item) for item in items
    )
    # Not printed here: the agent already streams its reasoning and final
    # answer to the console live (Strands' default callback handler), so
    # printing the return value again would just duplicate everything shown.
    result = agent(prompt)

    for item in items:
        mark_seen(item["matter_id"])

    return str(result)


if __name__ == "__main__":
    run_once()
