import asyncio
import json

import mcp.types as types
from starlette.requests import Request

import mcp_server


def _make_request(headers=None):
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "POST", "path": "/mcp", "headers": raw_headers})


def test_on_list_tools_maps_every_tool_schema():
    result = asyncio.run(mcp_server._on_list_tools(None, None))

    names = {t.name for t in result.tools}
    assert names == {schema["name"] for schema in mcp_server.tools.TOOL_SCHEMAS}


def test_on_list_tools_preserves_input_schema():
    result = asyncio.run(mcp_server._on_list_tools(None, None))

    tool = next(t for t in result.tools if t.name == "cancel_order")
    expected = next(s for s in mcp_server.tools.TOOL_SCHEMAS if s["name"] == "cancel_order")
    assert tool.input_schema == expected["input_schema"]
    assert tool.description == expected["description"]


def test_on_call_tool_dispatches_to_tools_run_tool_and_serializes_result(monkeypatch):
    monkeypatch.setattr(
        mcp_server.tools, "run_tool", lambda name, args: {"id": "1001", "called_with": args}
    )

    params = types.CallToolRequestParams(name="get_order", arguments={"order_id": "1001"})
    result = asyncio.run(mcp_server._on_call_tool(None, params))

    assert result.is_error is False
    assert json.loads(result.content[0].text) == {"id": "1001", "called_with": {"order_id": "1001"}}


def test_on_call_tool_marks_error_results():
    monkeypatch_value = {"error": "Order 9999 not found"}
    orig = mcp_server.tools.run_tool
    mcp_server.tools.run_tool = lambda name, args: monkeypatch_value
    try:
        params = types.CallToolRequestParams(name="get_order", arguments={"order_id": "9999"})
        result = asyncio.run(mcp_server._on_call_tool(None, params))
    finally:
        mcp_server.tools.run_tool = orig

    assert result.is_error is True
    assert json.loads(result.content[0].text) == {"error": "Order 9999 not found"}


def test_on_call_tool_handles_missing_arguments():
    orig = mcp_server.tools.run_tool
    captured = {}
    mcp_server.tools.run_tool = lambda name, args: captured.update(args=args) or {}
    try:
        params = types.CallToolRequestParams(name="list_recent_orders", arguments=None)
        asyncio.run(mcp_server._on_call_tool(None, params))
    finally:
        mcp_server.tools.run_tool = orig

    assert captured["args"] == {}


def test_bearer_auth_middleware_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(mcp_server, "MCP_BEARER_TOKEN", "secret")
    middleware = mcp_server.BearerAuthMiddleware(app=None)

    async def call_next(request):
        raise AssertionError("should not reach the wrapped app")

    response = asyncio.run(middleware.dispatch(_make_request(), call_next))

    assert response.status_code == 401


def test_bearer_auth_middleware_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(mcp_server, "MCP_BEARER_TOKEN", "secret")
    middleware = mcp_server.BearerAuthMiddleware(app=None)

    async def call_next(request):
        raise AssertionError("should not reach the wrapped app")

    request = _make_request({"Authorization": "Bearer wrong"})
    response = asyncio.run(middleware.dispatch(request, call_next))

    assert response.status_code == 401


def test_bearer_auth_middleware_allows_correct_token(monkeypatch):
    monkeypatch.setattr(mcp_server, "MCP_BEARER_TOKEN", "secret")
    middleware = mcp_server.BearerAuthMiddleware(app=None)

    async def call_next(request):
        return "ok"

    request = _make_request({"Authorization": "Bearer secret"})
    response = asyncio.run(middleware.dispatch(request, call_next))

    assert response == "ok"


def test_bearer_auth_middleware_rejects_everything_when_token_unset(monkeypatch):
    monkeypatch.setattr(mcp_server, "MCP_BEARER_TOKEN", None)
    middleware = mcp_server.BearerAuthMiddleware(app=None)

    async def call_next(request):
        raise AssertionError("should not reach the wrapped app")

    response = asyncio.run(middleware.dispatch(_make_request(), call_next))

    assert response.status_code == 503
