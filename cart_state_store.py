"""Tracks which abandoned checkouts have already been messaged, so a customer
never gets nudged twice for the same cart."""

import json
import os

NOTIFIED_PATH = os.environ.get("CART_NOTIFIED_PATH", "abandoned_cart_notified.json")


def load_notified():
    if not os.path.exists(NOTIFIED_PATH):
        return set()
    with open(NOTIFIED_PATH, "r") as f:
        return set(json.load(f))


def save_notified(notified):
    with open(NOTIFIED_PATH, "w") as f:
        json.dump(sorted(notified), f)
