import agent


class TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, id, name, input):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


class FakeResponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeBeta:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


class FakeClient:
    def __init__(self, responses, beta_responses=None):
        self.messages = FakeMessages(responses)
        self.beta = FakeBeta(beta_responses or [])


def test_run_agent_returns_text_when_no_tool_use(monkeypatch):
    fake_client = FakeClient([FakeResponse("end_turn", [TextBlock("Hello there")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    result = agent.run_agent("system prompt", "hi", tool_names=[])

    assert result == "Hello there"
    assert fake_client.messages.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


def test_run_agent_executes_tool_then_returns_final_text(monkeypatch):
    tool_call = ToolUseBlock("toolu_1", "get_order", {"order_id": "1001"})
    fake_client = FakeClient(
        [
            FakeResponse("tool_use", [tool_call]),
            FakeResponse("end_turn", [TextBlock("Order found!")]),
        ]
    )
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    recorded = {}

    def fake_run_tool(name, tool_input):
        recorded["name"] = name
        recorded["input"] = tool_input
        return {"id": "1001"}

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)

    result = agent.run_agent("system prompt", "where's my order?", tool_names=["get_order"])

    assert result == "Order found!"
    assert recorded == {"name": "get_order", "input": {"order_id": "1001"}}

    second_call_messages = fake_client.messages.calls[1]["messages"]
    assert second_call_messages[-1]["content"][0]["tool_use_id"] == "toolu_1"


def test_run_agent_gives_up_after_max_iterations(monkeypatch):
    tool_call = ToolUseBlock("toolu_1", "get_order", {"order_id": "1"})
    responses = [FakeResponse("tool_use", [tool_call]) for _ in range(agent.MAX_TOOL_ITERATIONS)]
    fake_client = FakeClient(responses)
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)
    monkeypatch.setattr(agent, "run_tool", lambda name, i: {})

    result = agent.run_agent("sys", "hi", tool_names=["get_order"])

    assert "wasn't able to finish" in result


def test_run_agent_prepends_history(monkeypatch):
    fake_client = FakeClient([FakeResponse("end_turn", [TextBlock("ok")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    history = [
        {"role": "user", "content": "earlier msg"},
        {"role": "assistant", "content": "earlier reply"},
    ]
    agent.run_agent("sys", "new msg", tool_names=[], history=history)

    sent_messages = fake_client.messages.calls[0]["messages"]
    assert sent_messages[0] == history[0]
    assert sent_messages[1] == history[1]
    assert sent_messages[2] == {"role": "user", "content": "new msg"}


def test_run_agent_filters_tools_by_tool_names(monkeypatch):
    fake_client = FakeClient([FakeResponse("end_turn", [TextBlock("ok")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    agent.run_agent("sys", "hi", tool_names=["send_whatsapp_message"])

    sent_tools = fake_client.messages.calls[0]["tools"]
    assert [t["name"] for t in sent_tools] == ["send_whatsapp_message"]


def test_run_agent_with_no_tool_names_sends_all_tools(monkeypatch):
    fake_client = FakeClient([FakeResponse("end_turn", [TextBlock("ok")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    agent.run_agent("sys", "hi")

    sent_tools = fake_client.messages.calls[0]["tools"]
    assert len(sent_tools) == len(agent.TOOL_SCHEMAS)


def test_run_agent_with_mcp_server_url_uses_beta_client(monkeypatch):
    fake_client = FakeClient(responses=[], beta_responses=[FakeResponse("end_turn", [TextBlock("policy says 30 days")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    result = agent.run_agent("sys", "what's your return policy?", mcp_server_url="https://store.myshopify.com/api/mcp")

    assert result == "policy says 30 days"
    assert fake_client.messages.calls == []  # never used the non-beta path
    beta_call = fake_client.beta.messages.calls[0]
    assert beta_call["mcp_servers"] == [
        {"type": "url", "url": "https://store.myshopify.com/api/mcp", "name": "shopify_storefront"}
    ]
    assert beta_call["betas"] == ["mcp-client-2025-04-04"]


def test_run_agent_without_mcp_server_url_uses_plain_client(monkeypatch):
    fake_client = FakeClient([FakeResponse("end_turn", [TextBlock("ok")])])
    monkeypatch.setattr(agent, "_get_client", lambda: fake_client)

    agent.run_agent("sys", "hi")

    assert fake_client.beta.messages.calls == []
