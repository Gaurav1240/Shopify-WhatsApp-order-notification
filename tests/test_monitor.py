import monitor


def test_monitor_tools_include_send_whatsapp_buttons():
    assert "send_whatsapp_buttons" in monitor.MONITOR_TOOLS


def test_monitor_tools_include_create_order_compensation_code():
    assert "create_order_compensation_code" in monitor.MONITOR_TOOLS


def test_check_once_notifies_on_status_change(monkeypatch):
    orders = [
        {"id": 1001, "financial_status": "paid", "fulfillment_status": "fulfilled"},
        {"id": 1002, "financial_status": "paid", "fulfillment_status": None},
    ]
    monkeypatch.setattr(monitor.shopify_client, "list_recent_orders", lambda **k: orders)
    monkeypatch.setattr(monitor, "load_state", lambda: {"1001": "paid|unfulfilled", "1002": "paid|None"})

    saved = {}
    monkeypatch.setattr(monitor, "save_state", lambda state: saved.update(state))

    calls = []
    monkeypatch.setattr(monitor, "run_agent", lambda **kwargs: calls.append(kwargs))

    monitor.check_once()

    assert len(calls) == 1
    assert "1001" in calls[0]["user_message"]
    assert saved == {"1001": "paid|fulfilled", "1002": "paid|None"}


def test_check_once_does_not_notify_first_seen_orders(monkeypatch):
    orders = [{"id": 1001, "financial_status": "paid", "fulfillment_status": None}]
    monkeypatch.setattr(monitor.shopify_client, "list_recent_orders", lambda **k: orders)
    monkeypatch.setattr(monitor, "load_state", lambda: {})

    saved = {}
    monkeypatch.setattr(monitor, "save_state", lambda state: saved.update(state))

    calls = []
    monkeypatch.setattr(monitor, "run_agent", lambda **kwargs: calls.append(kwargs))

    monitor.check_once()

    assert calls == []
    assert saved == {"1001": "paid|None"}


def test_check_once_skips_unchanged_orders(monkeypatch):
    orders = [{"id": 1001, "financial_status": "paid", "fulfillment_status": "fulfilled"}]
    monkeypatch.setattr(monitor.shopify_client, "list_recent_orders", lambda **k: orders)
    monkeypatch.setattr(monitor, "load_state", lambda: {"1001": "paid|fulfilled"})
    monkeypatch.setattr(monitor, "save_state", lambda state: None)

    calls = []
    monkeypatch.setattr(monitor, "run_agent", lambda **kwargs: calls.append(kwargs))

    monitor.check_once()

    assert calls == []
