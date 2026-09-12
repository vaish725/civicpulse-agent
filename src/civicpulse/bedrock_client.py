"""Shared helper for one-off Claude calls on Bedrock outside the agent loop.

Each reasoning tool in tools.py needs its own tightly scoped prompt (one
task, one job) rather than sharing the agent's general conversation, so
they call Claude directly through this module instead of going back through
the orchestrating Strands agent. Centralizing the call here keeps request
building and JSON parsing in one place instead of five.
"""

import json

import boto3

from civicpulse.config import BEDROCK_MODEL_ID, BEDROCK_REGION

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


def invoke(system_prompt: str, user_content: str, max_tokens: int = 1024) -> str:
    """Call Claude on Bedrock and return the raw text of its reply."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    response = _get_client().invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    return payload["content"][0]["text"]


def invoke_json(system_prompt: str, user_content: str, max_tokens: int = 1024) -> dict:
    """Call Claude and parse its reply as JSON.

    Every prompt that uses this asks explicitly for JSON-only output; this
    still strips a ```json code fence defensively in case the model wraps
    its answer in one anyway.
    """
    text = invoke(system_prompt, user_content, max_tokens=max_tokens).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            text = rest if first_line.strip().lower() in ("json", "") else text
    return json.loads(text)
