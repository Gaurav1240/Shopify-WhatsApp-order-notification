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


def find_orders_by_phone(phone, days_back=90):
    target = _normalize_phone(phone)
    if not target:
        return []
    orders = list_recent_orders(days_back=days_back, limit=250)
    return [order for order in orders if _normalize_phone(order.get("phone")) == target]
