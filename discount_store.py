"""Tracks discount codes already issued for abandoned-cart recovery.

Two jobs: let a checkout that's messaged more than once (e.g. the poller
runs again before the customer buys) reuse its existing code instead of
minting a new one, and let discounts.py enforce the policy's cap on how many
codes one customer can collect in a rolling window.
"""

import json
import os
from datetime import datetime, timedelta

DISCOUNT_CODES_PATH = os.environ.get("DISCOUNT_CODES_PATH", "discount_codes.json")


def _load():
    if not os.path.exists(DISCOUNT_CODES_PATH):
        return []
    with open(DISCOUNT_CODES_PATH, "r") as f:
        return json.load(f)


def _save(codes):
    with open(DISCOUNT_CODES_PATH, "w") as f:
        json.dump(codes, f)


def find_active_code(checkout_id):
    checkout_id = str(checkout_id)
    now = datetime.now().isoformat()
    for record in _load():
        if record["checkout_id"] == checkout_id and record["expires_at"] > now:
            return record
    return None


def record_code(checkout_id, customer_key, code, percent, expires_at):
    record = {
        "checkout_id": str(checkout_id),
        "customer_key": str(customer_key),
        "code": code,
        "percent": percent,
        "expires_at": expires_at,
        "created_at": datetime.now().isoformat(),
    }
    codes = _load()
    codes.append(record)
    _save(codes)
    return record


def count_recent_codes(customer_key, days):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    customer_key = str(customer_key)
    return sum(
        1
        for record in _load()
        if record["customer_key"] == customer_key and record["created_at"] >= cutoff
    )
