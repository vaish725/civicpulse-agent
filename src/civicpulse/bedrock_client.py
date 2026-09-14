"""Shared helper for one-off Claude calls outside the agent loop.

Each reasoning tool in tools.py needs its own tightly scoped prompt (one
task, one job) rather than sharing the agent's general conversation, so
they call Claude directly through this module instead of going back through
the orchestrating Strands agent. Centralizing the call here keeps request
building and JSON parsing in one place instead of five.

Supports two providers behind the same invoke()/invoke_json() interface,
selected by config.MODEL_PROVIDER: Bedrock (the default, AWS-native path)
or the Anthropic API directly. This exists because Bedrock model invocation
can be blocked by AWS-account-level issues entirely unrelated to this
project's code (see README), and this module is where every reasoning
tool's actual model call happens, not just the top-level agent's; switching
providers only at the Agent level would leave these calls still pointed at
Bedrock.
"""

import json

from civicpulse.config import ANTHROPIC_MODEL_ID, BEDROCK_MODEL_ID, BEDROCK_REGION, MODEL_PROVIDER

_client = None


def _get_client():
    global _client
    if _client is None:
        if MODEL_PROVIDER == "anthropic":
            import anthropic

            _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        else:
            import boto3

            _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


def invoke(system_prompt: str, user_content: str, max_tokens: int = 1024) -> str:
    """Call Claude and return the raw text of its reply, via whichever
    provider MODEL_PROVIDER selects.
    """
    if MODEL_PROVIDER == "anthropic":
        response = _get_client().messages.create(
            model=ANTHROPIC_MODEL_ID,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

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
