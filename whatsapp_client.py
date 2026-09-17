"""Thin wrapper around Meta's WhatsApp Business Cloud API (Graph API)."""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_VERSION = os.environ.get("WHATSAPP_API_VERSION", "v21.0")


def _normalize_to(to):
    """Meta wants a bare number with country code, no '+' or 'whatsapp:' prefix."""
    return (to or "").removeprefix("whatsapp:").lstrip("+")


def send_whatsapp_message(to, body):
    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    access_token = os.environ["WHATSAPP_ACCESS_TOKEN"]

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_to(to),
        "type": "text",
        "text": {"body": body},
    }

    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()

    message_id = response.json()["messages"][0]["id"]
    return {"id": message_id, "to": to, "body": body}
