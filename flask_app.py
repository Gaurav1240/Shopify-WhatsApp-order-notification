"""Webhook entry points for the Shopify <-> WhatsApp agent.

- /order_webhook: Shopify calls this on order creation. An agent drafts and
  sends the WhatsApp confirmation itself (see NOTIFY_SYSTEM_PROMPT).
- /whatsapp_webhook: Twilio calls this when a customer messages the WhatsApp
  number. An agent looks up their order(s) and replies conversationally.
"""

import json

from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

from agent import run_agent
from conversation_store import append_turn, get_history

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
    "in this conversation (e.g. they say 'yes' after you asked)."
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


@app.route("/whatsapp_webhook", methods=["POST"])
def whatsapp_webhook():
    from_number = request.form.get("From", "").removeprefix("whatsapp:")
    body = request.form.get("Body", "")

    history = get_history(from_number)
    reply_text = run_agent(
        system_prompt=SUPPORT_SYSTEM_PROMPT,
        user_message=f"Message from {from_number}: {body}",
        tool_names=SUPPORT_TOOLS,
        history=history,
    )
    append_turn(from_number, body, reply_text)

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return str(twiml)


if __name__ == "__main__":
    app.run(debug=True)
