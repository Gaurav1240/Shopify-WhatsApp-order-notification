"""Thin wrapper around the Shopify API used by the agent's tools."""

import os
import re
from datetime import datetime, timedelta

import shopify
from dotenv import load_dotenv

load_dotenv()

_configured = False


def _configure():
    global _configured
    if _configured:
        return
    shopify.Session.setup(
        api_key=os.environ["SHOPIFY_API_KEY"],
        secret=os.environ["SHOPIFY_API_PASSWORD"],
    )
    shopify.ShopifyResource.set_site(f"https://{os.environ['SHOPIFY_STORE_NAME']}")
    _configured = True


def _order_to_dict(order):
    address = getattr(order, "shipping_address", None)
    phone = getattr(address, "phone", None) if address is not None else None
    customer = getattr(order, "customer", None)
    if not phone and customer is not None:
        phone = getattr(customer, "phone", None)

    return {
        "id": order.id,
        "name": order.name,
        "email": order.email,
        "phone": phone,
        "total_price": order.total_price,
        "financial_status": order.financial_status,
        "fulfillment_status": order.fulfillment_status,
        "created_at": order.created_at,
        "line_items": [
            {"title": item.title, "quantity": item.quantity}
            for item in getattr(order, "line_items", [])
        ],
    }


def get_order(order_id):
    _configure()
    return _order_to_dict(shopify.Order.find(order_id))


def get_order_status(order_id):
    order = get_order(order_id)
    return {
        "id": order["id"],
        "financial_status": order["financial_status"],
        "fulfillment_status": order["fulfillment_status"],
    }


def list_recent_orders(days_back=7, limit=100):
    _configure()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    orders = shopify.Order.find(created_at_min=start_date, created_at_max=end_date, limit=limit)
    return [_order_to_dict(order) for order in orders]


def _normalize_phone(phone):
    return re.sub(r"\D", "", phone or "")


def _phones_match(a, b):
    """Compare by the last 10 digits so a missing/differing country code (e.g.
    WhatsApp's E.164 +1... vs. a locally-entered Shopify phone) still matches."""
    a, b = _normalize_phone(a), _normalize_phone(b)
    return bool(a) and bool(b) and a[-10:] == b[-10:]


def find_orders_by_phone(phone, days_back=90):
    if not _normalize_phone(phone):
        return []
    orders = list_recent_orders(days_back=days_back, limit=250)
    return [order for order in orders if _phones_match(order.get("phone"), phone)]


def _checkout_to_dict(checkout):
    customer = getattr(checkout, "customer", None)
    phone = getattr(checkout, "phone", None)
    if not phone and customer is not None:
        phone = getattr(customer, "phone", None)

    return {
        "id": checkout.id,
        "token": getattr(checkout, "token", None),
        "email": getattr(checkout, "email", None),
        "phone": phone,
        "total_price": getattr(checkout, "total_price", None),
        "abandoned_checkout_url": getattr(checkout, "abandoned_checkout_url", None),
        "created_at": checkout.created_at,
        "line_items": [
            {"title": item.title, "quantity": item.quantity, "price": getattr(item, "price", None)}
            for item in getattr(checkout, "line_items", [])
        ],
    }


def list_abandoned_checkouts(hours_old=1, lookback_hours=48, limit=100):
    """Checkouts started but never completed, old enough that the customer

    has plausibly given up rather than still being mid-purchase.
    `hours_old` sets that minimum age; `lookback_hours` bounds how far back
    to search so the query stays cheap on a busy store.
    """
    _configure()
    now = datetime.now()
    created_at_max = (now - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%S")
    created_at_min = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    checkouts = shopify.Checkout.find(created_at_min=created_at_min, created_at_max=created_at_max, limit=limit)
    return [_checkout_to_dict(c) for c in checkouts if getattr(c, "completed_at", None) is None]


def find_abandoned_checkout_by_phone(phone, lookback_hours=48):
    if not _normalize_phone(phone):
        return []
    checkouts = list_abandoned_checkouts(hours_old=0, lookback_hours=lookback_hours, limit=250)
    return [c for c in checkouts if _phones_match(c.get("phone"), phone)]


def cancel_order(order_id, reason=None):
    """Cancel an order. Irreversible — callers must have explicit customer confirmation."""
    _configure()
    order = shopify.Order.find(order_id)
    order.cancel(reason=reason)
    return get_order(order_id)


def refund_order(order_id, amount=None, reason=None):
    """Refund an order's original payment in full (or `amount`) as a single transaction.

    This is a simplified, whole-order refund: it does not itemize specific
    line items, only reissues money against the order's captured payment.
    Irreversible — callers must have explicit customer confirmation.
    """
    _configure()
    order = shopify.Order.find(order_id)
    transactions = order.transactions()
    parent = next(
        (t for t in transactions if t.kind in ("sale", "capture") and t.status == "success"),
        None,
    )
    if parent is None:
        raise ValueError(f"No refundable payment transaction found for order {order_id}")

    refund_amount = str(amount) if amount is not None else order.total_price
    transaction = shopify.Transaction(
        {
            "order_id": order.id,
            "kind": "refund",
            "amount": refund_amount,
            "parent_id": parent.id,
        }
    )
    if not transaction.save():
        raise RuntimeError(f"Refund failed: {transaction.errors.full_messages()}")

    return {
        "order_id": order.id,
        "refund_transaction_id": transaction.id,
        "amount": refund_amount,
        "reason": reason,
    }
