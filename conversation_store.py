"""Tiny JSON-file persistence for per-phone-number WhatsApp conversation history.

This is what lets the support agent handle multi-turn flows like order
cancellation: it asks for confirmation in one message, and needs to still
know what was being confirmed when the customer replies "yes" in the next.
"""

import json
import os

HISTORY_PATH = os.environ.get("CONVERSATION_HISTORY_PATH", "conversation_history.json")
MAX_TURNS = int(os.environ.get("CONVERSATION_MAX_TURNS", "10"))


def _load_all():
    if not os.path.exists(HISTORY_PATH):
        return {}
    with open(HISTORY_PATH, "r") as f:
        return json.load(f)


def _save_all(data):
    with open(HISTORY_PATH, "w") as f:
        json.dump(data, f)


def get_history(phone):
    return _load_all().get(phone, [])


def append_turn(phone, user_text, assistant_text):
    data = _load_all()
    history = data.get(phone, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    data[phone] = history[-(MAX_TURNS * 2):]
    _save_all(data)
