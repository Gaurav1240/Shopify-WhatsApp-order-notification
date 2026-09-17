"""Thin wrapper around the Twilio WhatsApp API used by the agent's tools."""

import os

from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _client


def send_whatsapp_message(to, body):
    client = _get_client()
    from_number = os.environ["TWILIO_WHATSAPP_FROM"].removeprefix("whatsapp:")
    to_number = to.removeprefix("whatsapp:") if to else to

    message = client.messages.create(
        from_=f"whatsapp:{from_number}",
        body=body,
        to=f"whatsapp:{to_number}",
    )
    return {"sid": message.sid, "to": message.to, "body": message.body}
