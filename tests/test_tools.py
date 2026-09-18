import tools


def test_run_tool_dispatches_to_handler(monkeypatch):
    monkeypatch.setitem(tools._HANDLERS, "get_order", lambda i: {"id": i["order_id"], "called": True})

    assert tools.run_tool("get_order", {"order_id": "42"}) == {"id": "42", "called": True}


def test_run_tool_unknown_tool_returns_error():
    assert tools.run_tool("does_not_exist", {}) == {"error": "Unknown tool: does_not_exist"}


def test_run_tool_catches_handler_exceptions(monkeypatch):
    def boom(_):
        raise ValueError("kaboom")

    monkeypatch.setitem(tools._HANDLERS, "get_order", boom)

    assert tools.run_tool("get_order", {"order_id": "1"}) == {"error": "kaboom"}


def test_tool_schema_names_match_handlers():
    schema_names = {schema["name"] for schema in tools.TOOL_SCHEMAS}
    assert schema_names == set(tools._HANDLERS.keys())


def test_destructive_tools_require_order_id_in_schema():
    for name in ("cancel_order", "refund_order"):
        schema = next(s for s in tools.TOOL_SCHEMAS if s["name"] == name)
        assert "order_id" in schema["input_schema"]["required"]


def test_send_whatsapp_message_handler_calls_whatsapp_client(monkeypatch):
    calls = {}

    def fake_send(to, body):
        calls["to"] = to
        calls["body"] = body
        return {"sid": "SM123"}

    monkeypatch.setattr(tools.whatsapp_client, "send_whatsapp_message", fake_send)

    result = tools._HANDLERS["send_whatsapp_message"]({"to": "+1555", "body": "hi"})

    assert calls == {"to": "+1555", "body": "hi"}
    assert result == {"sid": "SM123"}


def test_cancel_order_handler_forwards_reason(monkeypatch):
    calls = {}

    def fake_cancel(order_id, reason=None):
        calls["order_id"] = order_id
        calls["reason"] = reason
        return {"id": order_id}

    monkeypatch.setattr(tools.shopify_client, "cancel_order", fake_cancel)

    tools._HANDLERS["cancel_order"]({"order_id": "1001", "reason": "customer"})

    assert calls == {"order_id": "1001", "reason": "customer"}


def test_refund_order_handler_forwards_amount_and_reason(monkeypatch):
    calls = {}

    def fake_refund(order_id, amount=None, reason=None):
        calls["order_id"] = order_id
        calls["amount"] = amount
        calls["reason"] = reason
        return {"id": order_id}

    monkeypatch.setattr(tools.shopify_client, "refund_order", fake_refund)

    tools._HANDLERS["refund_order"]({"order_id": "1001", "amount": "10.00", "reason": "damaged"})

    assert calls == {"order_id": "1001", "amount": "10.00", "reason": "damaged"}


def test_list_abandoned_checkouts_handler_defaults_hours_old(monkeypatch):
    calls = {}

    def fake_list(hours_old=None):
        calls["hours_old"] = hours_old
        return []

    monkeypatch.setattr(tools.shopify_client, "list_abandoned_checkouts", fake_list)

    tools._HANDLERS["list_abandoned_checkouts"]({})

    assert calls == {"hours_old": 1}


def test_find_abandoned_checkout_by_phone_handler_forwards_phone(monkeypatch):
    calls = {}

    def fake_find(phone):
        calls["phone"] = phone
        return []

    monkeypatch.setattr(tools.shopify_client, "find_abandoned_checkout_by_phone", fake_find)

    tools._HANDLERS["find_abandoned_checkout_by_phone"]({"phone": "+15551234567"})

    assert calls == {"phone": "+15551234567"}


def test_get_returnable_items_handler_forwards_order_id(monkeypatch):
    calls = {}

    def fake_get(order_id):
        calls["order_id"] = order_id
        return []

    monkeypatch.setattr(tools.shopify_client, "get_returnable_items", fake_get)

    tools._HANDLERS["get_returnable_items"]({"order_id": "1001"})

    assert calls == {"order_id": "1001"}


def test_request_return_handler_forwards_all_fields(monkeypatch):
    calls = {}

    def fake_request(order_id, items, reason=None, note=None):
        calls.update({"order_id": order_id, "items": items, "reason": reason, "note": note})
        return {"status": "OPEN"}

    monkeypatch.setattr(tools.shopify_client, "request_return", fake_request)

    items = [{"fulfillment_line_item_id": "gid://x/1", "quantity": 1}]
    tools._HANDLERS["request_return"]({"order_id": "1001", "items": items, "reason": "wrong_item", "note": "wrong size"})

    assert calls == {"order_id": "1001", "items": items, "reason": "wrong_item", "note": "wrong size"}


def test_save_customer_feedback_handler_resolves_customer_and_saves(monkeypatch):
    monkeypatch.setattr(tools.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/777")

    calls = {}

    def fake_save(customer_id, feedback_type, feedback):
        calls.update({"customer_id": customer_id, "feedback_type": feedback_type, "feedback": feedback})
        return {"metafield_id": "gid://shopify/Metafield/1"}

    monkeypatch.setattr(tools.shopify_client, "save_customer_feedback", fake_save)

    result = tools._HANDLERS["save_customer_feedback"](
        {"phone": "+15551234567", "feedback_type": "delivery", "comment": "fast!", "rating": 5, "order_id": "1001"}
    )

    assert calls == {
        "customer_id": "gid://shopify/Customer/777",
        "feedback_type": "delivery",
        "feedback": {"comment": "fast!", "rating": 5, "order_id": "1001"},
    }
    assert result == {"metafield_id": "gid://shopify/Metafield/1"}


def test_save_customer_feedback_handler_returns_error_when_no_customer_found(monkeypatch):
    monkeypatch.setattr(tools.shopify_client, "find_customer_id_by_phone", lambda phone: None)

    result = tools._HANDLERS["save_customer_feedback"]({"phone": "+15551234567", "feedback_type": "delivery", "comment": "fast!"})

    assert "error" in result


def test_save_customer_feedback_handler_omits_optional_fields_when_absent(monkeypatch):
    monkeypatch.setattr(tools.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/777")

    calls = {}
    monkeypatch.setattr(
        tools.shopify_client,
        "save_customer_feedback",
        lambda customer_id, feedback_type, feedback: calls.update({"feedback": feedback}),
    )

    tools._HANDLERS["save_customer_feedback"]({"phone": "+15551234567", "feedback_type": "return", "comment": "wrong size"})

    assert calls["feedback"] == {"comment": "wrong size"}
