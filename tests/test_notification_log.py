import notification_log


def test_recent_returns_empty_list_when_no_file():
    assert notification_log.recent("+15551234567") == []


def test_log_and_recent_round_trip():
    notification_log.log("+1555", "your order shipped!")

    entries = notification_log.recent("+1555")

    assert len(entries) == 1
    assert entries[0]["text"] == "your order shipped!"
    assert "at" in entries[0]


def test_log_is_isolated_per_phone_number():
    notification_log.log("+1111", "a")
    notification_log.log("+2222", "b")

    assert [e["text"] for e in notification_log.recent("+1111")] == ["a"]
    assert [e["text"] for e in notification_log.recent("+2222")] == ["b"]


def test_log_trims_to_max_per_phone(monkeypatch):
    monkeypatch.setattr(notification_log, "MAX_PER_PHONE", 2)

    for i in range(5):
        notification_log.log("+1555", f"msg{i}")

    entries = notification_log.recent("+1555")

    assert [e["text"] for e in entries] == ["msg3", "msg4"]
