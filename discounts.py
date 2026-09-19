"""Auto-creates personalized abandoned-cart discount codes, bounded by the
merchant's discount policy (discount_policy.json).

The agent never picks a discount amount itself — it calls get_or_create,
which is the only place a percentage is decided, applying the policy's
tiers/bonus/cap and its per-customer rate limit before ever calling Shopify.
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
    customer_id = shopify_client.find_customer_id_by_phone(phone)
    customer_key = customer_id or phone

    if discount_store.count_recent_codes(customer_key, policy["max_codes_window_days"]) >= policy["max_codes_per_customer"]:
        return {"eligible": False, "reason": "Customer has reached the maximum discount codes allowed in this window"}

    percent = discount_policy.compute_discount_percent(cart_value, hours_since_abandoned, policy)
    code = _generate_code(percent)
    expires_at = (datetime.now() + timedelta(hours=policy["code_expiry_hours"])).isoformat()

    shopify_client.create_discount_code(code, percent, expires_at)

    return discount_store.record_code(
        checkout_id=checkout_id,
        customer_key=customer_key,
        code=code,
        percent=percent,
        expires_at=expires_at,
    )


def _generate_code(percent):
    return f"SAVE{int(percent)}-{uuid.uuid4().hex[:6].upper()}"
