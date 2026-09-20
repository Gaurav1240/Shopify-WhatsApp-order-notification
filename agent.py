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


def run_agent(system_prompt, user_message, tool_names=None, max_tokens=1024, history=None, mcp_server_url=None):
    """Run a tool-using agent to completion and return its final text reply.

    The agent decides for itself which of the allowed tools to call (if any)
    and in what order, looping until it produces a plain-text response or the
    iteration budget runs out.

    `history` is an optional list of prior plain-text {"role", "content"}
    turns (as produced by conversation_store) to give the agent memory of an
    earlier exchange with the same user — for example so it can act on "yes,
    go ahead" after it asked for confirmation in a previous message. Only the
    final text reply is meant to be persisted back into that history; the
    tool-call scaffolding built up within a single run_agent call is not.

    `mcp_server_url`, when given, connects the agent to that remote MCP
    server (e.g. a Shopify store's Storefront MCP) via the Anthropic API's
    MCP connector — those tools are discovered and executed server-side by
    Anthropic, not through this file's local run_tool() dispatch.
    """
    client = _get_client()
    tools = TOOL_SCHEMAS if tool_names is None else [t for t in TOOL_SCHEMAS if t["name"] in tool_names]

    messages = list(history or []) + [{"role": "user", "content": user_message}]

    create_kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system_prompt, tools=tools)
    messages_api = client.messages
    if mcp_server_url:
        create_kwargs["mcp_servers"] = [{"type": "url", "url": mcp_server_url, "name": "shopify_storefront"}]
        create_kwargs["betas"] = ["mcp-client-2025-04-04"]
        messages_api = client.beta.messages

    for _ in range(MAX_TOOL_ITERATIONS):
        response = messages_api.create(messages=messages, **create_kwargs)

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
