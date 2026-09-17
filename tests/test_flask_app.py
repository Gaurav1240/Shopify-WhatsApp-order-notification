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


def _meta_message_payload(from_number, body):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": from_number, "type": "text", "text": {"body": body}}
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_whatsapp_webhook_verification_succeeds_with_matching_token():
    client = flask_app.app.test_client()
    response = client.get(
        "/whatsapp_webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "challenge123",
        },
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "challenge123"


def test_whatsapp_webhook_verification_rejects_bad_token():
    client = flask_app.app.test_client()
    response = client.get(
        "/whatsapp_webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge123",
        },
    )

    assert response.status_code == 403


def test_whatsapp_webhook_uses_history_and_sends_reply(monkeypatch):
    monkeypatch.setattr(flask_app, "get_history", lambda phone: [{"role": "user", "content": "prior"}])

    saved_turns = []
    monkeypatch.setattr(
        flask_app,
        "append_turn",
        lambda phone, user_text, assistant_text: saved_turns.append((phone, user_text, assistant_text)),
    )

    captured_agent_call = {}

    def fake_run_agent(**kwargs):
        captured_agent_call.update(kwargs)
        return "Sure, order #1001 is on its way!"

    monkeypatch.setattr(flask_app, "run_agent", fake_run_agent)

    sent = []
    monkeypatch.setattr(
        flask_app, "send_whatsapp_message", lambda to, body: sent.append((to, body))
    )

    client = flask_app.app.test_client()
    response = client.post(
        "/whatsapp_webhook",
        json=_meta_message_payload("15551234567", "where's my order?"),
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "EVENT_RECEIVED"
    assert captured_agent_call["history"] == [{"role": "user", "content": "prior"}]
    assert captured_agent_call["tool_names"] == flask_app.SUPPORT_TOOLS
    assert "15551234567" in captured_agent_call["user_message"]
    assert saved_turns == [("15551234567", "where's my order?", "Sure, order #1001 is on its way!")]
    assert sent == [("15551234567", "Sure, order #1001 is on its way!")]


def test_whatsapp_webhook_ignores_non_message_events(monkeypatch):
    monkeypatch.setattr(flask_app, "run_agent", lambda **k: (_ for _ in ()).throw(AssertionError("should not run")))

    client = flask_app.app.test_client()
    response = client.post("/whatsapp_webhook", json={"entry": [{"changes": [{"value": {"statuses": []}}]}]})

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "EVENT_RECEIVED"


def test_support_tools_include_cancel_and_refund():
    assert "cancel_order" in flask_app.SUPPORT_TOOLS
    assert "refund_order" in flask_app.SUPPORT_TOOLS
    assert "send_whatsapp_message" not in flask_app.SUPPORT_TOOLS
