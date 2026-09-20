"""Records proactive (agent-initiated) WhatsApp messages per phone number,
so the support agent can be told what a customer has already been sent.

This is deliberately separate from conversation_store.py's turn history: the
Messages API requires strict user/assistant role alternation, but a
proactive notification has no paired customer message, and two proactive
sends in a row (e.g. an order confirmation, then a status update before the
customer ever replies) would produce two consecutive "assistant" turns if
forced into that same list. Keeping this as a plain append-only log sidesteps
that entirely — it's folded into the *current* user turn's text as context
(see flask_app.py) rather than injected as fake history turns.
"""

import json
import os
from datetime import datetime

NOTIFICATION_LOG_PATH = os.environ.get("NOTIFICATION_LOG_PATH", "notification_log.json")
MAX_PER_PHONE = int(os.environ.get("NOTIFICATION_LOG_MAX_PER_PHONE", "5"))


def _load():
    if not os.path.exists(NOTIFICATION_LOG_PATH):
        return {}
    with open(NOTIFICATION_LOG_PATH, "r") as f:
        return json.load(f)


def _save(data):
    with open(NOTIFICATION_LOG_PATH, "w") as f:
        json.dump(data, f)


def log(phone, text):
    data = _load()
    entries = data.get(phone, [])
    entries.append({"text": text, "at": datetime.now().isoformat()})
    data[phone] = entries[-MAX_PER_PHONE:]
    _save(data)


def recent(phone):
    return _load().get(phone, [])
