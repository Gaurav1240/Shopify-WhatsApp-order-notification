"""Autonomous agent that nudges customers who abandoned their cart.

Run standalone: `python abandoned_cart.py`. On each poll it fetches
checkouts that were started but never completed and are old enough that the
customer has plausibly given up (not still mid-purchase), and — for each one
it hasn't already messaged — hands it to an agent that drafts and sends a
friendly WhatsApp reminder with the recovery link. `cart_state_store.py`
remembers which checkouts were already nudged so nobody gets messaged twice.
"""

import json
import os
import time
from datetime import datetime

from dotenv import load_dotenv

import shopify_client
from agent import run_agent
from cart_state_store import load_notified, save_notified

load_dotenv()

POLL_INTERVAL_SECONDS = int(os.environ.get("CART_POLL_INTERVAL_SECONDS", "900"))
ABANDON_AFTER_HOURS = float(os.environ.get("CART_ABANDON_AFTER_HOURS", "1"))
CHECKOUT_LOOKBACK_HOURS = int(os.environ.get("CART_LOOKBACK_HOURS", "48"))

CART_TOOLS = ["send_whatsapp_message", "create_discount_code"]

CART_SYSTEM_PROMPT = (
    "You are a cart-recovery agent for a Shopify store. You are shown a "
    "checkout that a customer started but never completed, including the "
    "items they added, its total price, how many hours it's been abandoned "
    "(hours_since_abandoned), and a recovery link (abandoned_checkout_url). "
    "Call create_discount_code (with the checkout's id, phone, cart_value, "
    "and hours_since_abandoned) to get a personalized discount code within "
    "the store's policy. If it returns {\"eligible\": false}, don't mention "
    "a discount at all. Write a short, friendly WhatsApp message reminding "
    "them what's in their cart (mention 1-2 specific items by name), "
    "include the discount code and percent off if you got one, and the "
    "recovery link so they can finish buying. Do not use pushy urgency or "
    "scarcity language. Send it with send_whatsapp_message to their phone "
    "number. If there is no phone number, do not send anything and just "
    "say so."
)


def _hours_since_abandoned(created_at):
    if not created_at:
        return 0
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.now(created.tzinfo)
    return max((now - created).total_seconds() / 3600, 0)


def check_once():
    notified = load_notified()
    checkouts = shopify_client.list_abandoned_checkouts(
        hours_old=ABANDON_AFTER_HOURS, lookback_hours=CHECKOUT_LOOKBACK_HOURS
    )

    for checkout in checkouts:
        checkout_id = str(checkout["id"])
        if checkout_id in notified:
            continue

        if not checkout.get("phone"):
            notified.add(checkout_id)  # nothing we can do, stop re-checking it
            continue

        checkout_for_agent = {
            **checkout,
            "hours_since_abandoned": round(_hours_since_abandoned(checkout.get("created_at")), 1),
        }

        run_agent(
            system_prompt=CART_SYSTEM_PROMPT,
            user_message=f"Abandoned checkout:\n{json.dumps(checkout_for_agent, default=str)}",
            tool_names=CART_TOOLS,
        )
        notified.add(checkout_id)

    save_notified(notified)


def run_forever():
    while True:
        try:
            check_once()
        except Exception as exc:
            print(f"Abandoned-cart check failed: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
