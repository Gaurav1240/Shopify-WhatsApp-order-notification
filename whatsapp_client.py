"""Thin wrapper around Meta's WhatsApp Business Cloud API (Graph API)."""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v21.0")


def _normalize_to(to):
    """Meta wants a bare number with country code, no '+' or 'whatsapp:' prefix."""
    return (to or "").removeprefix("whatsapp:").lstrip("+")


def _post_message(payload):
    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    access_token = os.environ["WHATSAPP_ACCESS_TOKEN"]

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()

    return response.json()["messages"][0]["id"]


def send_whatsapp_message(to, body):
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_to(to),
        "type": "text",
        "text": {"body": body},
    }
    message_id = _post_message(payload)
    return {"id": message_id, "to": to, "body": body}


def send_whatsapp_buttons(to, body, buttons):
    """Send a message with up to 3 tappable quick-reply buttons instead of
    plain text — Meta's hard limit, enforced here so a misconfigured agent
    call fails clearly instead of with an opaque Graph API error.

    `buttons` is a list of {"id": str, "title": str} (title is what the
    customer sees and taps; id is what comes back in the reply webhook).
    """
    if not buttons or len(buttons) > 3:
        raise ValueError(f"WhatsApp allows 1-3 buttons, got {len(buttons)}")

    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_to(to),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons
                ]
            },
        },
    }
    message_id = _post_message(payload)
    return {"id": message_id, "to": to, "body": body, "buttons": buttons}
