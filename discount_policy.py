"""Loads the merchant-configured abandoned-cart discount policy
(discount_policy.json) and computes a discount percent within it.

The policy sets hard bounds on what an abandoned-cart discount can be — the
agent never chooses a discount amount itself, it only calls
create_discount_code (tools.py), which applies this policy. Edit
discount_policy.json directly to tune it per store; no code change needed.
"""

import json
import os

DISCOUNT_POLICY_PATH = os.environ.get("DISCOUNT_POLICY_PATH", "discount_policy.json")

_DEFAULT_POLICY = {
    "max_discount_percent": 20,
    "tiers": [
        {"min_cart_value": 0, "discount_percent": 5},
        {"min_cart_value": 50, "discount_percent": 10},
        {"min_cart_value": 150, "discount_percent": 15},
    ],
    "long_abandoned_hours": 48,
    "long_abandoned_bonus_percent": 5,
    "order_issue_compensation_percent": 10,
    "code_expiry_hours": 72,
    "max_codes_per_customer": 2,
    "max_codes_window_days": 30,
}


def load_policy():
    if not os.path.exists(DISCOUNT_POLICY_PATH):
        return _DEFAULT_POLICY
    with open(DISCOUNT_POLICY_PATH, "r") as f:
        return {**_DEFAULT_POLICY, **json.load(f)}


def compute_discount_percent(cart_value, hours_since_abandoned=0, policy=None):
    """Highest tier whose min_cart_value the cart clears, plus a bonus for a
    long-abandoned cart, capped at max_discount_percent. Never above the cap
    regardless of tier/bonus values, so a misconfigured policy can't blow the
    ceiling."""
    policy = policy or load_policy()

    percent = 0
    for tier in sorted(policy["tiers"], key=lambda t: t["min_cart_value"]):
        if cart_value >= tier["min_cart_value"]:
            percent = tier["discount_percent"]

    if hours_since_abandoned >= policy["long_abandoned_hours"]:
        percent += policy["long_abandoned_bonus_percent"]

    return min(percent, policy["max_discount_percent"])
