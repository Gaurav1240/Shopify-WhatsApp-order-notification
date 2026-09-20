"""Autonomous agent that polls Shopify for order-status changes it wasn't told about.

Run standalone: `python monitor.py`. On each poll it fetches recent orders,
diffs their financial/fulfillment status against what it last saw, and — for
anything that changed — hands the decision of whether (and what) to tell the
customer over to the agent itself, rather than a hardcoded notification rule.
"""

import json
import os
import time

from dotenv import load_dotenv

import shopify_client
from agent import run_agent
from state_store import load_state, save_state

load_dotenv()

POLL_INTERVAL_SECONDS = int(os.environ.get("MONITOR_INTERVAL_SECONDS", "300"))
LOOKBACK_DAYS = int(os.environ.get("ORDER_LOOKBACK_DAYS", "14"))

MONITOR_TOOLS = ["send_whatsapp_message", "send_whatsapp_buttons", "create_order_compensation_code"]

MONITOR_SYSTEM_PROMPT = (
    "You are an autonomous order-monitoring agent for a Shopify store. "
    "You will be shown an order whose status just changed (for example it "
    "shipped, was fulfilled, was cancelled, or was refunded). Decide whether "
    "the customer would want a WhatsApp update about this change. If so, "
    "write a short, friendly message and send it to their phone number. If "
    "the change isn't worth notifying the customer about, or there is no "
    "phone number on file, do nothing and briefly say why not.\n\n"
    "If the order just became fulfilled/delivered, add a brief, casual ask "
    "for delivery feedback at the end of the message (e.g. 'How was your "
    "delivery experience? Just reply and let us know!') — whatever they "
    "reply with will be picked up and saved automatically, you don't need "
    "to do anything else with it here.\n\n"
    "If the change is bad news for the customer (cancelled, payment failed, "
    "or similar) that the store caused rather than the customer asking for "
    "it, call create_order_compensation_code (with the order's id and "
    "phone) to see if you can offer a one-time discount code as an apology "
    "— include it in your message if you get one. If it returns "
    "{\"eligible\": false}, don't mention compensation at all. Prefer "
    "send_whatsapp_buttons over send_whatsapp_message for bad news, closing "
    "with buttons for what they'd want to do next (e.g. 'Talk to someone', "
    "'Track order') instead of just leaving them to type a reply. For a "
    "routine update (shipped, fulfilled) plain send_whatsapp_message is "
    "fine and no compensation is needed."
)


def _status_key(order):
    return f"{order.get('financial_status')}|{order.get('fulfillment_status')}"


def check_once():
    state = load_state()
    orders = shopify_client.list_recent_orders(days_back=LOOKBACK_DAYS)

    for order in orders:
        order_id = str(order["id"])
        previous = state.get(order_id)
        current = _status_key(order)

        if previous is not None and previous != current:
            run_agent(
                system_prompt=MONITOR_SYSTEM_PROMPT,
                user_message=(
                    f"Order status changed from '{previous}' to '{current}'.\n"
                    f"Order details:\n{json.dumps(order, default=str)}"
                ),
                tool_names=MONITOR_TOOLS,
            )

        state[order_id] = current

    save_state(state)


def run_forever():
    while True:
        try:
            check_once()
        except Exception as exc:
            print(f"Monitor check failed: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
