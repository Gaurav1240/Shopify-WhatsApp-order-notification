import json

import flask_app


def test_order_webhook_invokes_notify_agent(monkeypatch):
    captured = {}

    def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return "sent"

    monkeypatch.setattr(flask_app, "run_agent", fake_run_agent)

    client = flask_app.app.test_client()
    payload = {"data": {"id": 1001, "name": "#1001", "email": "a@example.com", "total_price": "45.00"}}
    response = client.post("/order_webhook", data=json.dumps(payload), content_type="application/json")

    assert response.status_code == 200
    assert captured["tool_names"] == flask_app.NOTIFY_TOOLS
    assert "1001" in captured["user_message"]


def test_order_webhook_accepts_flat_payload(monkeypatch):
    monkeypatch.setattr(flask_app, "run_agent", lambda **k: "sent")

    client = flask_app.app.test_client()
    payload = {"id": 42, "name": "#42"}
    response = client.post("/order_webhook", data=json.dumps(payload), content_type="application/json")

    assert response.status_code == 200


def test_whatsapp_webhook_uses_and_updates_history(monkeypatch):
    monkeypatch.setattr(flask_app, "get_history", lambda phone: [{"role": "user", "content": "prior"}])

    saved_turns = []
    monkeypatch.setattr(
        flask_app,
        "append_turn",
        lambda phone, user_text, assistant_text: saved_turns.append((phone, user_text, assistant_text)),
    )

    captured = {}

    def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return "Sure, order #1001 is on its way!"

    monkeypatch.setattr(flask_app, "run_agent", fake_run_agent)

    client = flask_app.app.test_client()
    response = client.post(
        "/whatsapp_webhook",
        data={"From": "whatsapp:+15551234567", "Body": "where's my order?"},
    )

    assert response.status_code == 200
    assert "Sure, order #1001 is on its way!" in response.get_data(as_text=True)
    assert captured["history"] == [{"role": "user", "content": "prior"}]
    assert captured["tool_names"] == flask_app.SUPPORT_TOOLS
    assert saved_turns == [("+15551234567", "where's my order?", "Sure, order #1001 is on its way!")]


def test_support_tools_include_cancel_and_refund():
    assert "cancel_order" in flask_app.SUPPORT_TOOLS
    assert "refund_order" in flask_app.SUPPORT_TOOLS
