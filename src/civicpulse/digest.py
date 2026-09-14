"""Renders the agent's assessed items into a single static HTML digest page:
the human review surface a person actually reads and acts on. Read-only by
design (see project scope): a person reviews, personalizes, and submits any
draft comment themselves using the linked primary source. Nothing here ever
sends or submits anything on its own.
"""

import html
from pathlib import Path

from civicpulse.config import NEIGHBORHOOD_PRIORITIES
from civicpulse.schemas import ItemAssessment

DEFAULT_DIGEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "digest" / "latest.html"


def _escape(text: str | None) -> str:
    return html.escape(text) if text else ""


CONSENT_OVERRIDE_NOTE = (
    "This is on the consent calendar, so it passes automatically as part of a batch vote "
    "unless someone requests it be pulled for individual discussion before the meeting. "
    "To request that, contact the City Clerk's office before the meeting date; see the "
    "primary source link for current contact details."
)


def _item_card(item: ItemAssessment) -> str:
    """Render one agenda item as a self-contained review card."""
    matched = ", ".join(item.matched_priorities) if item.matched_priorities else "none"
    parts = [
        '<div class="item">',
        f"<h3>{_escape(item.title)}</h3>",
        f'<p class="meta">Matter {_escape(item.matter_file)} | Meeting {_escape(item.meeting_date)}'
        f'{" | consent calendar item" if item.is_consent else ""}</p>',
        f'<p class="meta">Matched priorities: {_escape(matched)}</p>',
        f"<p><strong>Relevance:</strong> {_escape(item.relevance_reasoning)}</p>",
        f"<p><strong>Urgency ({_escape(item.urgency_level)}):</strong> {_escape(item.urgency_reason)}</p>",
    ]
    if item.summary:
        parts.append(f"<p><strong>Summary:</strong> {_escape(item.summary)}</p>")
    if item.draft_comment:
        parts.append(
            "<p><strong>Draft public comment</strong> "
            "(review, personalize, and submit yourself; nothing is sent automatically):</p>"
            f'<pre class="draft">{_escape(item.draft_comment)}</pre>'
        )
    if item.is_consent:
        # A "no action needed" judgment on a consent item is still a real
        # decision made on the reader's behalf; the least the digest owes
        # them is the mechanism to override it if they disagree with it.
        parts.append(f'<p class="meta">{_escape(CONSENT_OVERRIDE_NOTE)}</p>')
    parts.append(f'<p><a href="{_escape(item.source_url)}">View on the primary agenda source</a></p>')
    parts.append("</div>")
    return "\n".join(parts)


def _reviewed_item_line(item: ItemAssessment) -> str:
    """Render one line for the collapsed "reviewed, no action" list.

    Includes matched_priorities, not just the title and reason: the whole
    point of this list is showing an item was genuinely reasoned about, and
    the matched-priority field is the one that actually proves that (for
    example, showing an item matched "housing_accessibility" and not
    "housing_affordability" despite sharing housing-adjacent language).
    Hiding that field here would bury the digest's best evidence of real
    semantic judgment behind a collapsed summary.
    """
    matched = ", ".join(item.matched_priorities) if item.matched_priorities else "none"
    line = (
        f"<li>{_escape(item.title)} (matter {_escape(item.matter_file)}). "
        f"Matched: {_escape(matched)}. {_escape(item.urgency_reason)}"
    )
    if item.is_consent:
        line += f" {_escape(CONSENT_OVERRIDE_NOTE)}"
    return line + "</li>"


def render_digest(
    items: list[ItemAssessment], data_source_note: str, output_path: Path = DEFAULT_DIGEST_PATH
) -> Path:
    """Build the static digest page from assessed items and write it to disk.

    Grouped by urgency so the one or two items that actually need a
    decision are not buried under routine ones: "now" items first, then
    "digest"-level items for awareness, then a collapsed list of relevant
    items with no action needed, then a plain count of everything judged
    not relevant, kept for transparency without cluttering the page.
    """
    now_items = [i for i in items if i.urgency_level == "now"]
    digest_items = [i for i in items if i.urgency_level == "digest"]
    reviewed_items = [i for i in items if i.relevant and i.urgency_level not in ("now", "digest")]
    not_relevant_count = sum(1 for i in items if not i.relevant)

    priorities_list = "".join(
        f"<li>{_escape(p['name'])}: {_escape(p['description'])}</li>" for p in NEIGHBORHOOD_PRIORITIES
    )

    sections = []
    if now_items:
        sections.append("<h2>Needs attention now</h2>" + "\n".join(_item_card(i) for i in now_items))
    if digest_items:
        sections.append(
            "<h2>On your radar (not urgent yet)</h2>" + "\n".join(_item_card(i) for i in digest_items)
        )
    if reviewed_items:
        reviewed_list = "".join(_reviewed_item_line(i) for i in reviewed_items)
        sections.append(
            "<details><summary>Reviewed and relevant, but no action needed right now "
            f"({len(reviewed_items)})</summary><ul>{reviewed_list}</ul></details>"
        )
    if not now_items and not digest_items and not reviewed_items:
        sections.append("<p>No relevant items in this batch.</p>")
    sections.append(
        f'<p class="meta">{not_relevant_count} other item(s) in this batch were reviewed '
        "and found not relevant to the priorities below.</p>"
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CivicPulse Digest</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 780px; margin: 2rem auto;
          padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }}
  h1 {{ margin-bottom: 0.25rem; }}
  .meta {{ color: #555; font-size: 0.9rem; }}
  .item {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
  .draft {{ white-space: pre-wrap; background: #f6f6f6; border: 1px solid #e0e0e0;
            border-radius: 6px; padding: 0.75rem; font-family: inherit; }}
  a {{ color: #1a5fb4; }}
  details {{ margin: 1rem 0; }}
  .banner {{ background: #fff6e5; border: 1px solid #e8c47a; border-radius: 6px;
             padding: 0.75rem 1rem; margin-bottom: 1.5rem; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>CivicPulse Digest</h1>
<div class="banner">
  <strong>Data source:</strong> {_escape(data_source_note)}<br>
  Nothing on this page has been sent or submitted anywhere. Review each item, personalize
  any draft comment, and submit it yourself using its primary source link, verifying the
  current meeting date and comment deadline there before you act.
</div>
<h2>Neighborhood priorities on file</h2>
<ul>{priorities_list}</ul>
{"".join(sections)}
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc)
    return output_path
