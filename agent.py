"""A small tool-using agent loop built on the Anthropic Messages API."""

import json
import os

import anthropic
from dotenv import load_dotenv

from tools import TOOL_SCHEMAS, run_tool

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ITERATIONS = 6

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def run_agent(system_prompt, user_message, tool_names=None, max_tokens=1024):
    """Run a tool-using agent to completion and return its final text reply.

    The agent decides for itself which of the allowed tools to call (if any)
    and in what order, looping until it produces a plain-text response or the
    iteration budget runs out.
    """
    client = _get_client()
    tools = TOOL_SCHEMAS if tool_names is None else [t for t in TOOL_SCHEMAS if t["name"] in tool_names]

    messages = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = run_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "I wasn't able to finish that within the allotted number of steps."
