"""Ties the local appointment calendar (appointment_store.py) to Shopify:
books/cancels slots, and mirrors each booking onto the relevant Order or
Customer record as a metafield so store staff can see it in Shopify admin
without needing WhatsApp access.
"""

import json

import appointment_store
import shopify_client

ORDER_APPOINTMENT_TYPES = {"return_pickup", "delivery"}


def list_slots(appointment_type, days_ahead=None):
    return appointment_store.list_available_slots(appointment_type, days_ahead=days_ahead)


def book(appointment_type, slot_id, phone, order_id=None, service_name=None, notes=None):
    if appointment_type in ORDER_APPOINTMENT_TYPES and not order_id:
        raise ValueError(f"'{appointment_type}' appointments require an order_id")

    appointment = appointment_store.book_slot(
        appointment_type, slot_id, phone, order_id=order_id, service_name=service_name, notes=notes
    )
    _write_through(appointment)
    return appointment


def cancel(appointment_id):
    appointment = appointment_store.cancel_appointment(appointment_id)
    _write_through(appointment)
    return appointment


def find_by_phone(phone):
    return appointment_store.find_appointments_by_phone(phone)


def _write_through(appointment):
    """Best-effort: the local appointment_store record is always the source
    of truth for availability, so a Shopify write failure here does not
    undo the booking/cancellation — it's only logged."""
    key = f"{appointment['appointment_type']}_appointment"
    value = json.dumps(appointment)

    try:
        if appointment["appointment_type"] in ORDER_APPOINTMENT_TYPES:
            shopify_client.set_order_metafield(appointment["order_id"], "whatsapp_agent", key, value)
        else:
            customer_id = shopify_client.find_customer_id_by_phone(appointment["phone"])
            if customer_id:
                shopify_client.set_customer_metafield(customer_id, "whatsapp_agent", key, value)
    except Exception as exc:
        print(f"Failed to mirror appointment to Shopify: {exc}")
