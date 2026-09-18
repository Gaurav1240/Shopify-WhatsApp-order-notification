"""Shopify Admin GraphQL API client used by the agent's tools.

Talks directly to /admin/api/<version>/graphql.json with a single Admin API
access token — no SDK, no REST. NOTE: the exact field/enum names below for
orderCancel, refundCreate, abandonedCheckouts and returnRequest are written
from Shopify's published GraphQL docs, not verified against a live schema
(this environment has no network access to shopify.dev or a real store) —
smoke-test against a dev store before relying on this in production.
"""

import os
import re
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-01")  # bump to Shopify's current quarterly version


def _graphql(query, variables=None):
    url = f"https://{os.environ['SHOPIFY_STORE_NAME']}/admin/api/{API_VERSION}/graphql.json"
    response = requests.post(
        url,
        headers={
            "X-Shopify-Access-Token": os.environ["SHOPIFY_ACCESS_TOKEN"],
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables or {}},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"Shopify GraphQL error: {payload['errors']}")
    return payload["data"]


def _to_gid(resource, id_value):
    id_value = str(id_value)
    return id_value if id_value.startswith("gid://") else f"gid://shopify/{resource}/{id_value}"


def _gid_to_id(gid):
    return int(gid.rsplit("/", 1)[-1])


_ORDER_FIELDS = """
  id
  name
  email
  displayFinancialStatus
  displayFulfillmentStatus
  createdAt
  totalPriceSet { shopMoney { amount currencyCode } }
  shippingAddress { phone }
  customer { phone }
  lineItems(first: 50) {
    edges { node { title quantity } }
  }
"""


def _order_from_node(node):
    phone = (node.get("shippingAddress") or {}).get("phone")
    if not phone:
        phone = (node.get("customer") or {}).get("phone")

    return {
        "id": _gid_to_id(node["id"]),
        "name": node["name"],
        "email": node.get("email"),
        "phone": phone,
        "total_price": node["totalPriceSet"]["shopMoney"]["amount"],
        "financial_status": node.get("displayFinancialStatus"),
        "fulfillment_status": node.get("displayFulfillmentStatus"),
        "created_at": node["createdAt"],
        "line_items": [
            {"title": edge["node"]["title"], "quantity": edge["node"]["quantity"]}
            for edge in node["lineItems"]["edges"]
        ],
    }


def get_order(order_id):
    data = _graphql(
        f"query GetOrder($id: ID!) {{ order(id: $id) {{ {_ORDER_FIELDS} }} }}",
        {"id": _to_gid("Order", order_id)},
    )
    node = data["order"]
    if node is None:
        raise ValueError(f"Order {order_id} not found")
    return _order_from_node(node)


def get_order_status(order_id):
    order = get_order(order_id)
    return {
        "id": order["id"],
        "financial_status": order["financial_status"],
        "fulfillment_status": order["fulfillment_status"],
    }


def list_recent_orders(days_back=7, limit=100):
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    data = _graphql(
        f"""
        query ListOrders($first: Int!, $query: String) {{
          orders(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {{
            edges {{ node {{ {_ORDER_FIELDS} }} }}
          }}
        }}
        """,
        {"first": limit, "query": f"created_at:>={start_date}"},
    )
    return [_order_from_node(edge["node"]) for edge in data["orders"]["edges"]]


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


def cancel_order(order_id, reason=None):
    """Cancel an order. Irreversible — callers must have explicit customer
    confirmation. Does not issue a refund (that's a separate, explicit
    refund_order call) but does restock the cancelled items."""
    result = _graphql(
        """
        mutation CancelOrder($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!) {
          orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock) {
            job { id done }
            orderCancelUserErrors { field message }
          }
        }
        """,
        {
            "orderId": _to_gid("Order", order_id),
            "reason": (reason or "other").upper(),
            "refund": False,
            "restock": True,
        },
    )["orderCancel"]

    errors = result["orderCancelUserErrors"]
    if errors:
        raise RuntimeError(f"Cancel failed: {errors}")

    return get_order(order_id)


def refund_order(order_id, amount=None, reason=None):
    """Refund an order's original payment in full (or `amount`) as a single
    transaction. Irreversible — callers must have explicit customer
    confirmation."""
    gid = _to_gid("Order", order_id)
    data = _graphql(
        """
        query OrderForRefund($id: ID!) {
          order(id: $id) {
            id
            totalPriceSet { shopMoney { amount currencyCode } }
            transactions(first: 20) { id kind status }
          }
        }
        """,
        {"id": gid},
    )
    order = data["order"]
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    parent = next(
        (t for t in order["transactions"] if t["kind"] in ("SALE", "CAPTURE") and t["status"] == "SUCCESS"),
        None,
    )
    if parent is None:
        raise ValueError(f"No refundable payment transaction found for order {order_id}")

    refund_amount = str(amount) if amount is not None else order["totalPriceSet"]["shopMoney"]["amount"]

    result = _graphql(
        """
        mutation CreateRefund($input: RefundInput!) {
          refundCreate(input: $input) {
            refund { id totalRefundedSet { shopMoney { amount currencyCode } } }
            userErrors { field message }
          }
        }
        """,
        {
            "input": {
                "orderId": gid,
                "note": reason,
                "transactions": [
                    {"orderId": gid, "parentId": parent["id"], "amount": refund_amount, "kind": "REFUND"}
                ],
            }
        },
    )["refundCreate"]

    errors = result["userErrors"]
    if errors:
        raise RuntimeError(f"Refund failed: {errors}")

    return {
        "order_id": order_id,
        "refund_id": result["refund"]["id"],
        "amount": refund_amount,
        "reason": reason,
    }


def _checkout_from_node(node):
    customer = node.get("customer") or {}
    return {
        "id": _gid_to_id(node["id"]),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "total_price": (node.get("totalPriceSet") or {}).get("shopMoney", {}).get("amount"),
        "abandoned_checkout_url": node.get("abandonedCheckoutUrl"),
        "created_at": node.get("createdAt"),
        "line_items": [
            {"title": edge["node"]["title"], "quantity": edge["node"]["quantity"]}
            for edge in (node.get("lineItems") or {}).get("edges", [])
        ],
    }


def list_abandoned_checkouts(hours_old=1, lookback_hours=48, limit=100):
    """Checkouts started but never completed, old enough that the customer
    has plausibly given up rather than still being mid-purchase.
    `hours_old` sets that minimum age; `lookback_hours` bounds how far back
    to search so the query stays cheap on a busy store."""
    now = datetime.now()
    created_at_max = (now - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%S")
    created_at_min = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    data = _graphql(
        """
        query AbandonedCheckouts($first: Int!, $query: String) {
          abandonedCheckouts(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {
            edges {
              node {
                id
                createdAt
                abandonedCheckoutUrl
                totalPriceSet { shopMoney { amount currencyCode } }
                customer { phone email }
                lineItems(first: 20) { edges { node { title quantity } } }
              }
            }
          }
        }
        """,
        {"first": limit, "query": f"created_at:>={created_at_min} AND created_at:<={created_at_max}"},
    )
    return [_checkout_from_node(edge["node"]) for edge in data["abandonedCheckouts"]["edges"]]


def find_abandoned_checkout_by_phone(phone, lookback_hours=48):
    if not _normalize_phone(phone):
        return []
    checkouts = list_abandoned_checkouts(hours_old=0, lookback_hours=lookback_hours, limit=250)
    return [c for c in checkouts if _phones_match(c.get("phone"), phone)]


def get_returnable_items(order_id):
    """List an order's fulfilled line items available to return, each with
    the fulfillment-line-item ID the returnRequest mutation needs."""
    data = _graphql(
        """
        query ReturnableItems($id: ID!) {
          order(id: $id) {
            id
            fulfillments(first: 10) {
              fulfillmentLineItems(first: 50) {
                edges { node { id quantity lineItem { title } } }
              }
            }
          }
        }
        """,
        {"id": _to_gid("Order", order_id)},
    )
    order = data["order"]
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    items = []
    for fulfillment in order["fulfillments"]:
        for edge in fulfillment["fulfillmentLineItems"]["edges"]:
            node = edge["node"]
            items.append(
                {
                    "fulfillment_line_item_id": node["id"],
                    "title": node["lineItem"]["title"],
                    "quantity": node["quantity"],
                }
            )
    return items


def request_return(order_id, items, reason=None, note=None):
    """Request a return for one or more fulfilled line items.

    `items` is a list of {"fulfillment_line_item_id": str, "quantity": int}
    (from get_returnable_items). Only starts a return request — it does not
    itself refund money. Callers must have explicit customer confirmation
    before calling this.
    """
    return_line_items = [
        {
            "fulfillmentLineItemId": item["fulfillment_line_item_id"],
            "quantity": item["quantity"],
            "returnReason": (reason or "other").upper(),
            "returnReasonNote": note,
        }
        for item in items
    ]

    result = _graphql(
        """
        mutation RequestReturn($input: ReturnRequestInput!) {
          returnRequest(input: $input) {
            return { id status }
            userErrors { field message }
          }
        }
        """,
        {"input": {"orderId": _to_gid("Order", order_id), "returnLineItems": return_line_items}},
    )["returnRequest"]

    errors = result["userErrors"]
    if errors:
        raise RuntimeError(f"Return request failed: {errors}")

    return {
        "order_id": order_id,
        "return_id": result["return"]["id"],
        "status": result["return"]["status"],
    }
