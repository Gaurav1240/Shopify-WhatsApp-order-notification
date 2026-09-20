"""Auto-creates personalized discount codes, bounded by the merchant's
discount policy (discount_policy.json), for two triggers:

- get_or_create — an abandoned-cart recovery nudge (cart-value tiered).
- get_or_create_for_order — proactive compensation the monitoring agent can
  offer when an order's status change is bad news (a flat policy percent).

Neither the cart-recovery agent nor the monitoring agent ever picks a
percentage itself — these functions are the only place one is decided,
applying the policy and its per-customer rate limit before ever calling
Shopify. `subject_id` below is whatever the caller wants deduplication
against: a checkout id for the cart flow, an order id for the compensation
flow — either way, a second call for the same subject reuses its code
rather than minting a new one.
"""

import uuid
from datetime import datetime, timedelta

import discount_policy
import discount_store
import shopify_client


def get_or_create(checkout_id, phone, cart_value, hours_since_abandoned=0):
    existing = discount_store.find_active_code(checkout_id)
    if existing:
        return existing

    policy = discount_policy.load_policy()
    percent = discount_policy.compute_discount_percent(cart_value, hours_since_abandoned, policy)
    return _issue_code(checkout_id, phone, percent, policy)


def get_or_create_for_order(order_id, phone, reason=None):
    existing = discount_store.find_active_code(order_id)
    if existing:
        return existing

    policy = discount_policy.load_policy()
    percent = min(policy["order_issue_compensation_percent"], policy["max_discount_percent"])
    return _issue_code(order_id, phone, percent, policy)


def _issue_code(subject_id, phone, percent, policy):
    customer_id = shopify_client.find_customer_id_by_phone(phone)
    customer_key = customer_id or phone

    if discount_store.count_recent_codes(customer_key, policy["max_codes_window_days"]) >= policy["max_codes_per_customer"]:
        return {"eligible": False, "reason": "Customer has reached the maximum discount codes allowed in this window"}

    code = _generate_code(percent)
    expires_at = (datetime.now() + timedelta(hours=policy["code_expiry_hours"])).isoformat()

    shopify_client.create_discount_code(code, percent, expires_at)

    return discount_store.record_code(
        checkout_id=subject_id,
        customer_key=customer_key,
        code=code,
        percent=percent,
        expires_at=expires_at,
    )


def _generate_code(percent):
    return f"SAVE{int(percent)}-{uuid.uuid4().hex[:6].upper()}"
