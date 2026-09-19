"""MCP server exposing this project's Shopify/WhatsApp tools (tools.py) to
any external MCP-compatible client, over Streamable HTTP — the "plug this
into another agentic-commerce system" integration point.

Run standalone: `python mcp_server.py`. Requires MCP_BEARER_TOKEN; every
request must send `Authorization: Bearer <token>` or gets a 401 before it
ever reaches an MCP handler — this is a single shared secret, not OAuth, and
is only appropriate for a trusted system plugging in directly, not a public
multi-tenant deployment.

Guardrail note: this exposes the full tool set, including cancel_order,
refund_order, and request_return. Inside this project, those are only ever
called after the WhatsApp support agent's system prompt has told it to wait
for the customer's explicit confirmation — but that's a system-prompt-level
instruction to a specific Claude agent, not something enforced here. Any
client holding MCP_BEARER_TOKEN can call any tool, including those, with no
confirmation step of its own. That responsibility belongs entirely to
whatever system holds the token — confirm it enforces its own gate before
plugging it in.

Built and smoke-tested (live HTTP round trip: initialize, tools/list,
tools/call) against mcp==2.2.0 / uvicorn==0.53.0 — pin those exact versions
in requirements.txt, since this SDK's Streamable HTTP API is young enough to
plausibly change between versions.
"""

import json
import os

import uvicorn
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import mcp.types as types
from mcp.server.lowlevel import Server

import tools

load_dotenv()

MCP_BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))


async def _on_list_tools(context, params):
    return types.ListToolsResult(
        tools=[
            types.Tool(name=schema["name"], description=schema["description"], input_schema=schema["input_schema"])
            for schema in tools.TOOL_SCHEMAS
        ]
    )


async def _on_call_tool(context, params):
    result = tools.run_tool(params.name, params.arguments or {})
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, default=str))],
        is_error=isinstance(result, dict) and "error" in result,
    )


server = Server(
    name="shopify-whatsapp-commerce",
    version="0.1.0",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Static shared-secret check in front of the MCP endpoint. Fails closed:
    an unset MCP_BEARER_TOKEN rejects every request (503) rather than
    silently allowing them through — matters because the `if __name__ ==
    "__main__"` guard below is only hit by `python mcp_server.py`, not by
    `uvicorn mcp_server:app`, which some hosts use directly."""

    async def dispatch(self, request: Request, call_next):
        if not MCP_BEARER_TOKEN:
            return JSONResponse({"error": "server misconfigured: MCP_BEARER_TOKEN is not set"}, status_code=503)
        if request.headers.get("authorization") != f"Bearer {MCP_BEARER_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_app():
    app = server.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware)
    return app


app = build_app()


if __name__ == "__main__":
    if not MCP_BEARER_TOKEN:
        raise SystemExit("Set MCP_BEARER_TOKEN before running mcp_server.py — it would otherwise be open to anyone.")
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
