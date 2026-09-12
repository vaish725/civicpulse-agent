"""Shared structured-output schema for the agent's final report.

Kept separate from agent.py and digest.py to avoid a circular import: the
agent produces one of these (via Strands' structured_output_model), and the
digest renderer consumes it to build the review page deterministically,
without depending on however the model happened to format its free text.
"""

from pydantic import BaseModel


class ItemJudgment(BaseModel):
    """The agent's judgment for one item: this is the only shape the LLM
    itself produces. matter_file is included solely as a join key back to
    our own fetched item data; factual fields like the source link or
    meeting date are intentionally not part of this schema; a mistyped link
    or date restated from the model's memory, in the one place meant to let
    someone verify things themselves, would be actively harmful.
    """

    matter_file: str
    relevant: bool
    matched_priorities: list[str] = []
    relevance_reasoning: str
    # Optional, not just discouraged: classify_urgency should only ever be
    # called for relevant items, and making these fields required forced
    # the model to invent an urgency judgment for every item just to fill
    # in the schema, including ones already found not relevant.
    urgency_level: str | None = None  # "now", "digest", or "ignore"
    urgency_reason: str | None = None
    summary: str | None = None
    draft_comment: str | None = None


class AgendaJudgments(BaseModel):
    """The agent's structured final answer for one ingestion run."""

    items: list[ItemJudgment]


class ItemAssessment(BaseModel):
    """One agenda item's full judgment, ready for rendering.

    Built by merging an ItemJudgment with our own ground-truth item data
    (see agent.py); this is what digest.py actually renders.
    """

    matter_file: str
    title: str
    meeting_date: str
    source_url: str
    is_consent: bool
    relevant: bool
    matched_priorities: list[str]
    relevance_reasoning: str
    urgency_level: str
    urgency_reason: str
    summary: str | None = None
    draft_comment: str | None = None
