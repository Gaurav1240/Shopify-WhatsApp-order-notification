import appointments


def test_book_requires_order_id_for_order_appointment_types():
    for appointment_type in ("return_pickup", "delivery"):
        try:
            appointments.book(appointment_type, "2026-01-01T09:00:00", "+15551234567")
            assert False, f"expected ValueError for {appointment_type}"
        except ValueError:
            pass


def test_book_writes_through_to_order_metafield(monkeypatch):
    booked = {
        "id": "abc",
        "appointment_type": "delivery",
        "slot": "2026-01-01T09:00:00",
        "phone": "+1555",
        "order_id": "1001",
    }
    monkeypatch.setattr(appointments.appointment_store, "book_slot", lambda *a, **k: booked)

    calls = {}
    monkeypatch.setattr(
        appointments.shopify_client,
        "set_order_metafield",
        lambda order_id, namespace, key, value: calls.update(
            {"order_id": order_id, "namespace": namespace, "key": key, "value": value}
        ),
    )

    result = appointments.book("delivery", "2026-01-01T09:00:00", "+1555", order_id="1001")

    assert result == booked
    assert calls["order_id"] == "1001"
    assert calls["namespace"] == "whatsapp_agent"
    assert calls["key"] == "delivery_appointment"


def test_book_writes_through_to_customer_metafield_for_service_type(monkeypatch):
    booked = {
        "id": "abc",
        "appointment_type": "service",
        "slot": "2026-01-01T09:00:00",
        "phone": "+1555",
        "service_name": "fitting",
    }
    monkeypatch.setattr(appointments.appointment_store, "book_slot", lambda *a, **k: booked)
    monkeypatch.setattr(
        appointments.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/777"
    )

    calls = {}
    monkeypatch.setattr(
        appointments.shopify_client,
        "set_customer_metafield",
        lambda customer_id, namespace, key, value: calls.update({"customer_id": customer_id, "key": key}),
    )

    appointments.book("service", "2026-01-01T09:00:00", "+1555", service_name="fitting")

    assert calls == {"customer_id": "gid://shopify/Customer/777", "key": "service_appointment"}


def test_book_write_through_failure_does_not_raise(monkeypatch):
    booked = {
        "id": "abc",
        "appointment_type": "service",
        "slot": "2026-01-01T09:00:00",
        "phone": "+1555",
        "service_name": "fitting",
    }
    monkeypatch.setattr(appointments.appointment_store, "book_slot", lambda *a, **k: booked)
    monkeypatch.setattr(
        appointments.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/777"
    )

    def fail(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(appointments.shopify_client, "set_customer_metafield", fail)

    result = appointments.book("service", "2026-01-01T09:00:00", "+1555", service_name="fitting")

    assert result == booked


def test_cancel_writes_through(monkeypatch):
    cancelled = {
        "id": "abc",
        "appointment_type": "return_pickup",
        "slot": "2026-01-01T09:00:00",
        "phone": "+1555",
        "order_id": "1001",
    }
    monkeypatch.setattr(appointments.appointment_store, "cancel_appointment", lambda appointment_id: cancelled)

    calls = {}
    monkeypatch.setattr(
        appointments.shopify_client,
        "set_order_metafield",
        lambda order_id, namespace, key, value: calls.update({"order_id": order_id}),
    )

    result = appointments.cancel("abc")

    assert result == cancelled
    assert calls == {"order_id": "1001"}


def test_find_by_phone_delegates_to_store(monkeypatch):
    monkeypatch.setattr(appointments.appointment_store, "find_appointments_by_phone", lambda phone: [{"id": "x"}])

    assert appointments.find_by_phone("+1555") == [{"id": "x"}]


def test_list_slots_delegates_to_store(monkeypatch):
    monkeypatch.setattr(
        appointments.appointment_store,
        "list_available_slots",
        lambda appointment_type, days_ahead=None: [{"slot_id": "x"}],
    )

    assert appointments.list_slots("service") == [{"slot_id": "x"}]
