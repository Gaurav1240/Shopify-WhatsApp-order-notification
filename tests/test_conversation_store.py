import conversation_store


def test_get_history_returns_empty_list_when_no_file():
    assert conversation_store.get_history("+15551234567") == []


def test_append_turn_persists_and_round_trips():
    conversation_store.append_turn("+1555", "hi", "hello!")
    conversation_store.append_turn("+1555", "how are you", "great, thanks!")

    assert conversation_store.get_history("+1555") == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello!"},
        {"role": "user", "content": "how are you"},
        {"role": "assistant", "content": "great, thanks!"},
    ]


def test_history_is_isolated_per_phone_number():
    conversation_store.append_turn("+1111", "a", "b")
    conversation_store.append_turn("+2222", "c", "d")

    assert conversation_store.get_history("+1111") == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    assert conversation_store.get_history("+2222") == [
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]


def test_history_trims_to_max_turns(monkeypatch):
    monkeypatch.setattr(conversation_store, "MAX_TURNS", 2)

    for i in range(5):
        conversation_store.append_turn("+1555", f"msg{i}", f"reply{i}")

    history = conversation_store.get_history("+1555")

    assert len(history) == 4
    assert history[0] == {"role": "user", "content": "msg3"}
    assert history[-1] == {"role": "assistant", "content": "reply4"}
