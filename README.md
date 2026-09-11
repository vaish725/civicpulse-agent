# CivicPulse

CivicPulse reads the agendas so your neighborhood doesn't have to, and only speaks up when there's a real decision on the table.

Built for the AWS "Agents for Humans" hackathon, Good Neighbor Agents track.

## The problem

Local government decides zoning, bike lanes, school budgets, and policing budgets: things that hit daily life harder than most federal policy. Almost nobody attends or reads city agendas anyway, because:

- Agendas are released on inconsistent schedules, often just days before a meeting.
- They are dense, jargon-heavy legal documents ("R-2 zoning density variance" instead of "apartment building near you").
- There is no way to filter for "does this affect my street or my specific concern" without reading everything.
- By the time someone notices an item matters, the public comment period has often closed.

Civic participation ends up skewed toward retirees, professional lobbyists, and people with a direct financial stake, not the broader neighborhood.

## Who this is for

- **Neighborhood association volunteers** who want to flag genuinely important city items to their list without reading every agenda from multiple local bodies.
- **Individual residents** who care about a couple of specific things (school funding, bike lane safety, a nearby zoning change) and want a single low-noise alert instead of parsing city government themselves.

This is not built for policy professionals or lobbyists who already monitor everything full time.

## What it does

CivicPulse is a single agent, built with the Strands Agents SDK, that:

1. Ingests newly published agenda items for a real city (San Jose, CA, via the Legistar Web API).
2. Judges whether each item is relevant to a neighborhood group's stated priorities, using semantic reasoning rather than keyword matching, so an item can match a priority even when it shares no words with it.
3. Classifies urgency: is a vote imminent, is a public comment window closing soon, or is this an informational item with no near-term action.
4. Summarizes relevant, time-sensitive items in plain language.
5. Optionally drafts a neutral public-comment template for a human to personalize and submit themselves.
6. Never sends, posts, or submits anything without explicit human approval.

Routine and non-time-sensitive items are batched into a periodic digest instead of generating an interrupt. Only relevant items with an imminent vote or closing comment window are surfaced immediately.

## What it deliberately does not do

- It does not submit public comments automatically. A human always reviews and sends.
- It does not support multiple cities in this version. One real city, done well.
- It does not take a political position. It explains what an item does and why it matches a stated priority, and is explicitly prompted to present trade-offs neutrally rather than advocate.
- It does not guarantee deadline accuracy. Every deadline-related claim links back to the primary agenda source with an explicit reminder to verify the date there.

## Architecture

```
Scheduler (daily)
      |
      v
Ingestion tool ---fetches---> City agenda source (Legistar Web API)
      |
      v
CivicPulse agent
  - fetch_agenda
  - assess_relevance(item, group_priorities)
  - classify_urgency(item)
  - summarize_plain_language(item)
  - draft_comment(item, priorities)   [only when relevance and urgency are both high]
      |
      v
Human review queue  --approve / edit / reject-->  Digest email or comment draft
```

Model: Claude via Amazon Bedrock. Persistence: a local store of previously seen agenda item IDs, so re-runs do not re-surface the same item. A single well-scoped agent with a handful of tools is used instead of a multi-agent architecture; that tradeoff is discussed in the codebase as the project develops.

## Data source

City of San Jose, CA, via the public Legistar Web API (`https://webapi.legistar.com/v1/sanjose/`). This is a real, live, publicly accessible data source, not a synthetic dataset. A cached snapshot of a real pull is kept locally as a fallback so a demo never depends on the live government site being reachable at the time.

## Status

Actively in development. Setup and run instructions will be added here as the implementation lands.

## License

MIT. See [LICENSE](LICENSE).
