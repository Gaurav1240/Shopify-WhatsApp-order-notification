import cart_state_store


def test_load_notified_returns_empty_set_when_no_file():
    assert cart_state_store.load_notified() == set()


def test_save_and_load_round_trip():
    cart_state_store.save_notified({"1001", "1002"})

    assert cart_state_store.load_notified() == {"1001", "1002"}
