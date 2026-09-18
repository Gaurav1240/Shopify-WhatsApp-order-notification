from datetime import datetime

import appointment_store


def test_list_available_slots_returns_future_business_hours_slots():
    slots = appointment_store.list_available_slots("service", days_ahead=7)

    assert len(slots) > 0
    for slot in slots:
        dt = datetime.fromisoformat(slot["starts_at"])
        assert dt.weekday() in appointment_store.WORKDAYS
        assert appointment_store.BUSINESS_HOURS_START <= dt.hour < appointment_store.BUSINESS_HOURS_END
        assert dt > datetime.now()


def test_book_slot_removes_it_from_availability():
    slots = appointment_store.list_available_slots("service")
    slot_id = slots[0]["slot_id"]

    appointment_store.book_slot("service", slot_id, "+15551234567", service_name="fitting")

    remaining_ids = [s["slot_id"] for s in appointment_store.list_available_slots("service")]
    assert slot_id not in remaining_ids


def test_book_slot_raises_when_already_taken():
    slots = appointment_store.list_available_slots("service")
    slot_id = slots[0]["slot_id"]
    appointment_store.book_slot("service", slot_id, "+15551234567")

    try:
        appointment_store.book_slot("service", slot_id, "+15559999999")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_different_appointment_types_can_share_a_slot():
    slots = appointment_store.list_available_slots("service")
    slot_id = slots[0]["slot_id"]

    appointment_store.book_slot("service", slot_id, "+15551234567")
    appointment_store.book_slot("delivery", slot_id, "+15551234567", order_id="1001")

    assert slot_id not in [s["slot_id"] for s in appointment_store.list_available_slots("service")]
    assert slot_id not in [s["slot_id"] for s in appointment_store.list_available_slots("delivery")]


def test_cancel_appointment_frees_the_slot():
    slots = appointment_store.list_available_slots("service")
    slot_id = slots[0]["slot_id"]
    appointment = appointment_store.book_slot("service", slot_id, "+15551234567")

    appointment_store.cancel_appointment(appointment["id"])

    remaining_ids = [s["slot_id"] for s in appointment_store.list_available_slots("service")]
    assert slot_id in remaining_ids


def test_cancel_appointment_raises_when_not_found():
    try:
        appointment_store.cancel_appointment("does-not-exist")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_find_appointments_by_phone_filters_by_phone():
    slots = appointment_store.list_available_slots("service")
    first = appointment_store.book_slot("service", slots[0]["slot_id"], "+15551234567")
    appointment_store.book_slot("service", slots[1]["slot_id"], "+15559999999")

    found = appointment_store.find_appointments_by_phone("+15551234567")

    assert [a["id"] for a in found] == [first["id"]]


def test_find_appointments_by_phone_excludes_cancelled_by_default():
    slots = appointment_store.list_available_slots("service")
    appointment = appointment_store.book_slot("service", slots[0]["slot_id"], "+15551234567")
    appointment_store.cancel_appointment(appointment["id"])

    assert appointment_store.find_appointments_by_phone("+15551234567") == []
    assert len(appointment_store.find_appointments_by_phone("+15551234567", include_cancelled=True)) == 1
