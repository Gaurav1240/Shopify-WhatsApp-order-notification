import state_store


def test_load_state_returns_empty_dict_when_no_file():
    assert state_store.load_state() == {}


def test_save_and_load_round_trip():
    state_store.save_state({"1001": "paid|fulfilled"})

    assert state_store.load_state() == {"1001": "paid|fulfilled"}
