"""Webhook entry points for the Shopify <-> WhatsApp agent.

- /order_webhook: Shopify calls this on order creation. An agent drafts and
  sends the WhatsApp confirmation itself (see NOTIFY_SYSTEM_PROMPT).
- /whatsapp_webhook: Meta's WhatsApp Business Cloud API calls this (GET to
  verify the webhook, POST to deliver inbound messages). An agent looks up
  the sender's order(s) and replies conversationally; since Meta has no
  reply-in-the-webhook-response mechanism like Twilio's TwiML, the reply is
  sent back out explicitly via send_whatsapp_message.
"""

import json
import os

from dotenv import load_dotenv
from flask import Flask, request

from agent import run_agent
from conversation_store import append_turn, get_history
from whatsapp_client import send_whatsapp_message

load_dotenv()

app = Flask(__name__)

NOTIFY_TOOLS = ["get_order", "get_order_status", "send_whatsapp_message"]
SUPPORT_TOOLS = [
    "get_order",
    "get_order_status",
    "list_recent_orders",
    "find_orders_by_phone",
    "cancel_order",
    "refund_order",
    "find_abandoned_checkout_by_phone",
]

NOTIFY_SYSTEM_PROMPT = (
    "You are the order-notification agent for a Shopify store. You are given "
    "the details of an order that was just created. Write a short, warm "
    "WhatsApp message to the customer confirming their order (mention the "
    "order name/number and total price), and send it with the "
    "send_whatsapp_message tool to the customer's phone number. If the phone "
    "number is missing, do not send anything and just say so."
)

SUPPORT_SYSTEM_PROMPT = (
    "You are a friendly, concise customer-support agent for a Shopify store, "
    "replying to a customer over WhatsApp. Use the available tools to look up "
    "their orders (match them by their phone number) and answer questions "
    "about order status, contents, or totals. Never invent order details you "
    "haven't looked up. Keep replies short enough for a chat message.\n\n"
    "You can also cancel an order or issue a refund with the cancel_order / "
    "refund_order tools. These are irreversible, so never call them on the "
    "same turn a customer first asks for one: look up the order, summarize "
    "it, and explicitly ask them to confirm. Only call cancel_order or "
    "refund_order once the customer has clearly confirmed in a later message "
    "in this conversation (e.g. they say 'yes' after you asked).\n\n"
    "If a customer asks about something they were trying to buy or a cart "
    "they didn't finish, use find_abandoned_checkout_by_phone to check for "
    "an incomplete checkout and share the recovery link if you find one."
)


@app.route("/order_webhook", methods=["POST"])
def order_webhook():
    payload = json.loads(request.data.decode("utf-8"))
    order_data = payload.get("data", payload)

    run_agent(
        system_prompt=NOTIFY_SYSTEM_PROMPT,
        user_message=f"New order created:\n{json.dumps(order_data, default=str)}",
        tool_names=NOTIFY_TOOLS,
    )
    return "Webhook received", 200


@app.route("/whatsapp_webhook", methods=["GET"])
def whatsapp_webhook_verify():
    """Meta's one-time webhook verification handshake."""
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == os.environ.get("WHATSAPP_VERIFY_TOKEN")
    ):
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@app.route("/whatsapp_webhook", methods=["POST"])
def whatsapp_webhook():
    payload = request.get_json(silent=True) or {}

    try:
        value = payload["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
    except (KeyError, IndexError):
        # Delivery/read status callbacks and other non-message events land
        # here too; there's nothing for the agent to do with those.
        return "EVENT_RECEIVED", 200

    from_number = message["from"]
    body = message.get("text", {}).get("body", "")

    history = get_history(from_number)
    reply_text = run_agent(
        system_prompt=SUPPORT_SYSTEM_PROMPT,
        user_message=f"Message from {from_number}: {body}",
        tool_names=SUPPORT_TOOLS,
        history=history,
    )
    append_turn(from_number, body, reply_text)
    send_whatsapp_message(from_number, reply_text)

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(debug=True)
