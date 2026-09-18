"""Local appointment calendar: available slots and booked appointments.

Shopify has no built-in scheduling concept, so this is the source of truth
for availability and double-booking prevention — appointments.py mirrors
each booking onto the relevant Shopify record separately, best-effort.

Simplification: slots are naive local time (no timezone handling) and each
appointment_type has exactly one "resource" per slot (e.g. one pickup per
hour, one fitting room per hour) — different appointment_types don't
compete for the same slot. Good enough for a single small store; a busier
one would want per-type capacity and real timezone awareness.
"""

import json
import os
import uuid
from datetime import datetime, timedelta

APPOINTMENTS_PATH = os.environ.get("APPOINTMENTS_PATH", "appointments.json")

BUSINESS_HOURS_START = int(os.environ.get("APPOINTMENT_HOURS_START", "9"))
BUSINESS_HOURS_END = int(os.environ.get("APPOINTMENT_HOURS_END", "17"))
SLOT_MINUTES = int(os.environ.get("APPOINTMENT_SLOT_MINUTES", "60"))
DEFAULT_DAYS_AHEAD = int(os.environ.get("APPOINTMENT_DAYS_AHEAD", "7"))
WORKDAYS = {0, 1, 2, 3, 4}  # Monday-Friday


def _load():
    if not os.path.exists(APPOINTMENTS_PATH):
        return []
    with open(APPOINTMENTS_PATH, "r") as f:
        return json.load(f)


def _save(appointments):
    with open(APPOINTMENTS_PATH, "w") as f:
        json.dump(appointments, f)


def _candidate_slots(days_ahead):
    now = datetime.now()
    slots = []
    for day_offset in range(days_ahead + 1):
        day = now + timedelta(days=day_offset)
        if day.weekday() not in WORKDAYS:
            continue
        slot_start = day.replace(hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=BUSINESS_HOURS_END, minute=0, second=0, microsecond=0)
        while slot_start < day_end:
            if slot_start > now:
                slots.append(slot_start)
            slot_start += timedelta(minutes=SLOT_MINUTES)
    return slots


def list_available_slots(appointment_type, days_ahead=None):
    days_ahead = DEFAULT_DAYS_AHEAD if days_ahead is None else days_ahead
    taken = {
        a["slot"]
        for a in _load()
        if a["appointment_type"] == appointment_type and a["status"] == "booked"
    }
    return [
        {"slot_id": slot.isoformat(), "starts_at": slot.isoformat()}
        for slot in _candidate_slots(days_ahead)
        if slot.isoformat() not in taken
    ]


def book_slot(appointment_type, slot_id, phone, order_id=None, service_name=None, notes=None):
    appointments = _load()
    already_taken = any(
        a["slot"] == slot_id and a["appointment_type"] == appointment_type and a["status"] == "booked"
        for a in appointments
    )
    if already_taken:
        raise ValueError("That slot is no longer available")

    appointment = {
        "id": str(uuid.uuid4()),
        "appointment_type": appointment_type,
        "slot": slot_id,
        "phone": phone,
        "order_id": order_id,
        "service_name": service_name,
        "notes": notes,
        "status": "booked",
        "created_at": datetime.now().isoformat(),
    }
    appointments.append(appointment)
    _save(appointments)
    return appointment


def cancel_appointment(appointment_id):
    appointments = _load()
    for appointment in appointments:
        if appointment["id"] == appointment_id:
            appointment["status"] = "cancelled"
            _save(appointments)
            return appointment
    raise ValueError(f"Appointment {appointment_id} not found")


def find_appointments_by_phone(phone, include_cancelled=False):
    appointments = [a for a in _load() if a["phone"] == phone]
    if not include_cancelled:
        appointments = [a for a in appointments if a["status"] == "booked"]
    return appointments
