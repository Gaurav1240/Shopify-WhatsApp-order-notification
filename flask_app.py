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
from notification_log import recent as get_recent_notifications
from whatsapp_client import send_whatsapp_message

load_dotenv()

app = Flask(__name__)

# Optional: a Shopify store's Storefront MCP endpoint (product catalog,
# policies/FAQs). When set, the support agent can consult the store's real
# return policy instead of guessing. See README for the expected URL shape.
STOREFRONT_MCP_URL = os.environ.get("STOREFRONT_MCP_URL")

NOTIFY_TOOLS = ["get_order", "get_order_status", "send_whatsapp_message", "send_whatsapp_buttons"]
SUPPORT_TOOLS = [
    "get_order",
    "get_order_status",
    "list_recent_orders",
    "find_orders_by_phone",
    "cancel_order",
    "refund_order",
    "find_abandoned_checkout_by_phone",
    "get_returnable_items",
    "request_return",
    "save_customer_feedback",
    "list_appointment_slots",
    "book_appointment",
    "cancel_appointment",
    "find_appointments_by_phone",
]

NOTIFY_SYSTEM_PROMPT = (
    "You are the order-notification agent for a Shopify store. You are given "
    "the details of an order that was just created. Write a short, warm "
    "WhatsApp message to the customer confirming their order (mention the "
    "order name/number and total price). Prefer send_whatsapp_buttons over "
    "send_whatsapp_message, closing with buttons for the obvious next "
    "actions (e.g. 'Track order', 'Need help?') so the customer can tap "
    "instead of typing a reply — fall back to send_whatsapp_message only if "
    "no button makes sense. If the phone number is missing, do not send "
    "anything and just say so."
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
    "an incomplete checkout and share the recovery link if you find one.\n\n"
    "If a customer wants to return or exchange an item: first, if you have "
    "storefront tools available, check the store's actual return policy "
    "(window, excluded items, who pays shipping) rather than guessing. Then "
    "use get_returnable_items to see what's eligible on their order, "
    "summarize it, and ask which item(s) and why before doing anything. "
    "Only call request_return once the customer has clearly confirmed in a "
    "later message in this conversation. Always ask why they're returning "
    "it if they haven't already said, and once you have that reason, save "
    "it with save_customer_feedback (feedback_type='return') in addition to "
    "calling request_return — the store can't see a WhatsApp conversation, "
    "so this is what makes their reason visible to staff.\n\n"
    "If a customer replies with feedback about their delivery experience "
    "(a rating, or comments like 'arrived fast' or 'box was damaged'), "
    "thank them briefly and save it with save_customer_feedback "
    "(feedback_type='delivery') so store staff can see it too.\n\n"
    "You can also book appointments with list_appointment_slots, "
    "book_appointment, find_appointments_by_phone, and cancel_appointment:\n"
    "- 'return_pickup': once a return has been requested, offer to schedule "
    "a courier pickup for the item.\n"
    "- 'delivery': if a customer wants to choose when their order arrives, "
    "look up the order first so you have its order_id to pass along.\n"
    "- 'service': anything not tied to a specific order — a fitting, "
    "consultation, repair, or similar in-store visit — ask what it's for "
    "and pass that as service_name.\n"
    "Always show 2-3 available slot times from list_appointment_slots and "
    "let the customer pick one before calling book_appointment. If booking "
    "fails because the slot was just taken, get a fresh list and offer "
    "alternatives rather than giving up."
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
    if message.get("type") == "interactive":
        # A tap on a send_whatsapp_buttons quick-reply arrives here, not as
        # a "text" message — without this branch, message.get("text", {})
        # is {} and the tap is silently read as an empty message.
        body = message.get("interactive", {}).get("button_reply", {}).get("title", "")
    else:
        body = message.get("text", {}).get("body", "")

    history = get_history(from_number)
    user_message = f"Message from {from_number}: {body}"

    notifications = get_recent_notifications(from_number)
    if notifications:
        recent_lines = "\n".join(f"- {n['text']}" for n in notifications)
        user_message = (
            f"Recent proactive notifications already sent to this customer "
            f"(they may be asking about one of these):\n{recent_lines}\n\n{user_message}"
        )

    reply_text = run_agent(
        system_prompt=SUPPORT_SYSTEM_PROMPT,
        user_message=user_message,
        tool_names=SUPPORT_TOOLS,
        history=history,
        mcp_server_url=STOREFRONT_MCP_URL,
    )
    append_turn(from_number, body, reply_text)
    send_whatsapp_message(from_number, reply_text)

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(debug=True)
