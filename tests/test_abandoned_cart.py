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
