import abandoned_cart


def test_check_once_notifies_new_abandoned_checkout(monkeypatch):
    checkouts = [
        {"id": 1, "phone": "+15551234567", "line_items": [{"title": "Mug", "quantity": 1}]},
    ]
    monkeypatch.setattr(abandoned_cart.shopify_client, "list_abandoned_checkouts", lambda **k: checkouts)
    monkeypatch.setattr(abandoned_cart, "load_notified", lambda: set())

    saved = set()
    monkeypatch.setattr(abandoned_cart, "save_notified", lambda notified: saved.update(notified))

    calls = []
    monkeypatch.setattr(abandoned_cart, "run_agent", lambda **kwargs: calls.append(kwargs))

    abandoned_cart.check_once()

    assert len(calls) == 1
    assert calls[0]["tool_names"] == abandoned_cart.CART_TOOLS
    assert "Mug" in calls[0]["user_message"]
    assert saved == {"1"}


def test_cart_tools_include_create_discount_code():
    assert "create_discount_code" in abandoned_cart.CART_TOOLS


def test_check_once_includes_hours_since_abandoned_in_message(monkeypatch):
    import json

    checkouts = [
        {"id": 1, "phone": "+15551234567", "created_at": "2026-01-01T00:00:00Z", "line_items": []},
    ]
    monkeypatch.setattr(abandoned_cart.shopify_client, "list_abandoned_checkouts", lambda **k: checkouts)
    monkeypatch.setattr(abandoned_cart, "load_notified", lambda: set())
    monkeypatch.setattr(abandoned_cart, "save_notified", lambda notified: None)
    monkeypatch.setattr(abandoned_cart, "_hours_since_abandoned", lambda created_at: 51.25)

    calls = []
    monkeypatch.setattr(abandoned_cart, "run_agent", lambda **kwargs: calls.append(kwargs))

    abandoned_cart.check_once()

    payload = json.loads(calls[0]["user_message"].split("\n", 1)[1])
    assert payload["hours_since_abandoned"] == 51.2


def test_hours_since_abandoned_handles_missing_created_at():
    assert abandoned_cart._hours_since_abandoned(None) == 0


def test_hours_since_abandoned_computes_from_iso_timestamp():
    from datetime import datetime, timedelta, timezone

    created_at = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    hours = abandoned_cart._hours_since_abandoned(created_at)

    assert 4.9 <= hours <= 5.1


def test_check_once_skips_already_notified_checkouts(monkeypatch):
    checkouts = [{"id": 1, "phone": "+15551234567", "line_items": []}]
    monkeypatch.setattr(abandoned_cart.shopify_client, "list_abandoned_checkouts", lambda **k: checkouts)
    monkeypatch.setattr(abandoned_cart, "load_notified", lambda: {"1"})
    monkeypatch.setattr(abandoned_cart, "save_notified", lambda notified: None)

    calls = []
    monkeypatch.setattr(abandoned_cart, "run_agent", lambda **kwargs: calls.append(kwargs))

    abandoned_cart.check_once()

    assert calls == []


def test_check_once_skips_and_marks_checkouts_without_phone(monkeypatch):
    checkouts = [{"id": 1, "phone": None, "line_items": []}]
    monkeypatch.setattr(abandoned_cart.shopify_client, "list_abandoned_checkouts", lambda **k: checkouts)
    monkeypatch.setattr(abandoned_cart, "load_notified", lambda: set())

    saved = set()
    monkeypatch.setattr(abandoned_cart, "save_notified", lambda notified: saved.update(notified))

    calls = []
    monkeypatch.setattr(abandoned_cart, "run_agent", lambda **kwargs: calls.append(kwargs))

    abandoned_cart.check_once()

    assert calls == []
    assert saved == {"1"}  # marked so we don't keep re-checking a dead end
