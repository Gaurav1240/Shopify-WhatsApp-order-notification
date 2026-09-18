import shopify_client


class FakeHTTPResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def _post_returning(payload):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeHTTPResponse(payload)

    return fake_post


def _post_dispatching(by_marker):
    """by_marker: {substring-of-query: response payload}. Picks the first
    substring found in the outgoing query, so tests can stub multi-round-trip
    functions (e.g. refund_order does a query then a mutation)."""

    def fake_post(url, headers=None, json=None, timeout=None):
        for marker, payload in by_marker.items():
            if marker in json["query"]:
                return FakeHTTPResponse(payload)
        raise AssertionError(f"No stub matched query: {json['query']}")

    return fake_post


ORDER_NODE = {
    "id": "gid://shopify/Order/1001",
    "name": "#1001",
    "email": "a@example.com",
    "displayFinancialStatus": "PAID",
    "displayFulfillmentStatus": "FULFILLED",
    "createdAt": "2026-01-01T00:00:00Z",
    "totalPriceSet": {"shopMoney": {"amount": "45.00", "currencyCode": "USD"}},
    "shippingAddress": {"phone": "+1 (555) 123-4567"},
    "customer": {"phone": None},
    "lineItems": {"edges": [{"node": {"title": "Mug", "quantity": 2}}]},
}


def test_get_order_extracts_phone_and_line_items(monkeypatch):
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": ORDER_NODE}}))}))

    result = shopify_client.get_order(1001)

    assert result["id"] == 1001
    assert result["phone"] == "+1 (555) 123-4567"
    assert result["financial_status"] == "PAID"
    assert result["line_items"] == [{"title": "Mug", "quantity": 2}]


def test_get_order_falls_back_to_customer_phone(monkeypatch):
    node = dict(ORDER_NODE, shippingAddress=None, customer={"phone": "5551234567"})
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": node}}))}))

    result = shopify_client.get_order(1001)

    assert result["phone"] == "5551234567"


def test_get_order_raises_when_not_found(monkeypatch):
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": None}}))}))

    try:
        shopify_client.get_order(9999)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_graphql_raises_on_errors_payload(monkeypatch):
    monkeypatch.setattr(
        shopify_client,
        "requests",
        type("R", (), {"post": staticmethod(_post_returning({"errors": [{"message": "bad token"}]}))}),
    )

    try:
        shopify_client.get_order(1001)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_get_order_status(monkeypatch):
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": ORDER_NODE}}))}))

    assert shopify_client.get_order_status(1001) == {
        "id": 1001,
        "financial_status": "PAID",
        "fulfillment_status": "FULFILLED",
    }


def test_list_recent_orders_maps_nodes(monkeypatch):
    payload = {"data": {"orders": {"edges": [{"node": ORDER_NODE}]}}}
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning(payload))}))

    results = shopify_client.list_recent_orders(days_back=7)

    assert len(results) == 1
    assert results[0]["id"] == 1001


def test_find_orders_by_phone_matches_normalized_numbers(monkeypatch):
    orders = [
        {"id": 1, "phone": "(555) 123-4567"},
        {"id": 2, "phone": "555-000-0000"},
    ]
    monkeypatch.setattr(shopify_client, "list_recent_orders", lambda **k: orders)

    assert shopify_client.find_orders_by_phone("5551234567") == [orders[0]]


def test_find_orders_by_phone_ignores_mismatched_country_code(monkeypatch):
    orders = [{"id": 1, "phone": "555-123-4567"}]
    monkeypatch.setattr(shopify_client, "list_recent_orders", lambda **k: orders)

    # Meta's webhook "from" field arrives with a country code; the order's
    # phone on file may not have one. They should still match on the last
    # 10 digits.
    assert shopify_client.find_orders_by_phone("+15551234567") == [orders[0]]


def test_find_orders_by_phone_empty_phone_returns_nothing():
    assert shopify_client.find_orders_by_phone("") == []


def test_cancel_order_calls_mutation_then_returns_refreshed_order(monkeypatch):
    monkeypatch.setattr(
        shopify_client,
        "requests",
        type(
            "R",
            (),
            {
                "post": staticmethod(
                    _post_dispatching(
                        {
                            "CancelOrder": {
                                "data": {"orderCancel": {"job": {"id": "gid://shopify/Job/1", "done": False}, "orderCancelUserErrors": []}}
                            },
                            "GetOrder": {"data": {"order": dict(ORDER_NODE, displayFinancialStatus="VOIDED")}},
                        }
                    )
                )
            },
        ),
    )

    result = shopify_client.cancel_order(1001, reason="customer")

    assert result["financial_status"] == "VOIDED"


def test_cancel_order_raises_on_user_errors(monkeypatch):
    monkeypatch.setattr(
        shopify_client,
        "requests",
        type(
            "R",
            (),
            {
                "post": staticmethod(
                    _post_returning(
                        {"data": {"orderCancel": {"job": None, "orderCancelUserErrors": [{"field": "orderId", "message": "already cancelled"}]}}}
                    )
                )
            },
        ),
    )

    try:
        shopify_client.cancel_order(1001)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


REFUND_ORDER_QUERY_RESPONSE = {
    "data": {
        "order": {
            "id": "gid://shopify/Order/1001",
            "totalPriceSet": {"shopMoney": {"amount": "45.00", "currencyCode": "USD"}},
            "transactions": [{"id": "gid://shopify/OrderTransaction/9", "kind": "SALE", "status": "SUCCESS"}],
        }
    }
}


def test_refund_order_uses_captured_transaction_as_parent(monkeypatch):
    created = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        if "OrderForRefund" in json["query"]:
            return FakeHTTPResponse(REFUND_ORDER_QUERY_RESPONSE)
        created.update(json["variables"]["input"])
        return FakeHTTPResponse(
            {
                "data": {
                    "refundCreate": {
                        "refund": {"id": "gid://shopify/Refund/555", "totalRefundedSet": {"shopMoney": {"amount": "45.00", "currencyCode": "USD"}}},
                        "userErrors": [],
                    }
                }
            }
        )

    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(fake_post)}))

    result = shopify_client.refund_order(1001, reason="damaged")

    assert created["transactions"][0]["parentId"] == "gid://shopify/OrderTransaction/9"
    assert created["transactions"][0]["amount"] == "45.00"
    assert result == {
        "order_id": 1001,
        "refund_id": "gid://shopify/Refund/555",
        "amount": "45.00",
        "reason": "damaged",
    }


def test_refund_order_uses_explicit_amount(monkeypatch):
    created = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        if "OrderForRefund" in json["query"]:
            return FakeHTTPResponse(REFUND_ORDER_QUERY_RESPONSE)
        created.update(json["variables"]["input"])
        return FakeHTTPResponse(
            {"data": {"refundCreate": {"refund": {"id": "gid://shopify/Refund/1", "totalRefundedSet": {}}, "userErrors": []}}}
        )

    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(fake_post)}))

    shopify_client.refund_order(1001, amount="10.00")

    assert created["transactions"][0]["amount"] == "10.00"


def test_refund_order_raises_without_refundable_transaction(monkeypatch):
    payload = {
        "data": {
            "order": {
                "id": "gid://shopify/Order/1001",
                "totalPriceSet": {"shopMoney": {"amount": "45.00", "currencyCode": "USD"}},
                "transactions": [],
            }
        }
    }
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning(payload))}))

    try:
        shopify_client.refund_order(1001)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_refund_order_raises_when_mutation_has_user_errors(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        if "OrderForRefund" in json["query"]:
            return FakeHTTPResponse(REFUND_ORDER_QUERY_RESPONSE)
        return FakeHTTPResponse(
            {"data": {"refundCreate": {"refund": None, "userErrors": [{"field": "amount", "message": "too high"}]}}}
        )

    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(fake_post)}))

    try:
        shopify_client.refund_order(1001)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_list_abandoned_checkouts_maps_nodes(monkeypatch):
    payload = {
        "data": {
            "abandonedCheckouts": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/AbandonedCheckout/5001",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "abandonedCheckoutUrl": "https://store.myshopify.com/carts/abc123",
                            "totalPriceSet": {"shopMoney": {"amount": "30.00", "currencyCode": "USD"}},
                            "customer": {"phone": "+1 (555) 123-4567", "email": "a@example.com"},
                            "lineItems": {"edges": [{"node": {"title": "Mug", "quantity": 2}}]},
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning(payload))}))

    results = shopify_client.list_abandoned_checkouts()

    assert results[0]["id"] == 5001
    assert results[0]["phone"] == "+1 (555) 123-4567"
    assert results[0]["abandoned_checkout_url"] == "https://store.myshopify.com/carts/abc123"
    assert results[0]["line_items"][0]["title"] == "Mug"


def test_find_abandoned_checkout_by_phone_matches(monkeypatch):
    checkouts = [
        {"id": 1, "phone": "555-123-4567"},
        {"id": 2, "phone": "555-000-0000"},
    ]
    monkeypatch.setattr(shopify_client, "list_abandoned_checkouts", lambda **k: checkouts)

    assert shopify_client.find_abandoned_checkout_by_phone("+15551234567") == [checkouts[0]]


def test_find_abandoned_checkout_by_phone_empty_phone_returns_nothing():
    assert shopify_client.find_abandoned_checkout_by_phone("") == []


def test_get_returnable_items_maps_fulfillment_line_items(monkeypatch):
    payload = {
        "data": {
            "order": {
                "id": "gid://shopify/Order/1001",
                "fulfillments": [
                    {
                        "fulfillmentLineItems": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/FulfillmentLineItem/1",
                                        "quantity": 1,
                                        "lineItem": {"title": "Mug"},
                                    }
                                }
                            ]
                        }
                    }
                ],
            }
        }
    }
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning(payload))}))

    results = shopify_client.get_returnable_items(1001)

    assert results == [{"fulfillment_line_item_id": "gid://shopify/FulfillmentLineItem/1", "title": "Mug", "quantity": 1}]


def test_get_returnable_items_raises_when_order_not_found(monkeypatch):
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": None}}))}))

    try:
        shopify_client.get_returnable_items(9999)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_request_return_builds_input_and_returns_confirmation(monkeypatch):
    created = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        created.update(json["variables"]["input"])
        return FakeHTTPResponse(
            {"data": {"returnRequest": {"return": {"id": "gid://shopify/Return/1", "status": "OPEN"}, "userErrors": []}}}
        )

    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(fake_post)}))

    items = [{"fulfillment_line_item_id": "gid://shopify/FulfillmentLineItem/1", "quantity": 1}]
    result = shopify_client.request_return(1001, items, reason="wrong_item", note="ordered the wrong size")

    assert created["returnLineItems"][0]["fulfillmentLineItemId"] == "gid://shopify/FulfillmentLineItem/1"
    assert created["returnLineItems"][0]["returnReason"] == "WRONG_ITEM"
    assert created["returnLineItems"][0]["returnReasonNote"] == "ordered the wrong size"
    assert result == {"order_id": 1001, "return_id": "gid://shopify/Return/1", "status": "OPEN"}


def test_request_return_raises_on_user_errors(monkeypatch):
    monkeypatch.setattr(
        shopify_client,
        "requests",
        type(
            "R",
            (),
            {
                "post": staticmethod(
                    _post_returning({"data": {"returnRequest": {"return": None, "userErrors": [{"field": "items", "message": "not eligible"}]}}})
                )
            },
        ),
    )

    try:
        shopify_client.request_return(1001, [{"fulfillment_line_item_id": "gid://x/1", "quantity": 1}])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_get_order_extracts_customer_id(monkeypatch):
    node = dict(ORDER_NODE, customer={"id": "gid://shopify/Customer/777", "phone": None})
    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(_post_returning({"data": {"order": node}}))}))

    result = shopify_client.get_order(1001)

    assert result["customer_id"] == "gid://shopify/Customer/777"


def test_find_customer_id_by_phone_returns_first_match(monkeypatch):
    orders = [
        {"id": 1, "phone": "555-123-4567", "customer_id": None},
        {"id": 2, "phone": "555-123-4567", "customer_id": "gid://shopify/Customer/777"},
    ]
    monkeypatch.setattr(shopify_client, "find_orders_by_phone", lambda phone, days_back=90: orders)

    assert shopify_client.find_customer_id_by_phone("+15551234567") == "gid://shopify/Customer/777"


def test_find_customer_id_by_phone_returns_none_when_no_match(monkeypatch):
    monkeypatch.setattr(shopify_client, "find_orders_by_phone", lambda phone, days_back=90: [])

    assert shopify_client.find_customer_id_by_phone("+15551234567") is None


def test_set_customer_metafield_builds_input_and_returns_confirmation(monkeypatch):
    created = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        created.update(json["variables"]["metafields"][0])
        return FakeHTTPResponse(
            {
                "data": {
                    "metafieldsSet": {
                        "metafields": [{"id": "gid://shopify/Metafield/1", "namespace": "whatsapp_agent", "key": "delivery_feedback"}],
                        "userErrors": [],
                    }
                }
            }
        )

    monkeypatch.setattr(shopify_client, "requests", type("R", (), {"post": staticmethod(fake_post)}))

    result = shopify_client.set_customer_metafield(777, "whatsapp_agent", "delivery_feedback", '{"rating": 5}')

    assert created["ownerId"] == "gid://shopify/Customer/777"
    assert created["namespace"] == "whatsapp_agent"
    assert created["key"] == "delivery_feedback"
    assert created["type"] == "json"
    assert result == {"metafield_id": "gid://shopify/Metafield/1", "namespace": "whatsapp_agent", "key": "delivery_feedback"}


def test_set_customer_metafield_raises_on_user_errors(monkeypatch):
    monkeypatch.setattr(
        shopify_client,
        "requests",
        type(
            "R",
            (),
            {
                "post": staticmethod(
                    _post_returning({"data": {"metafieldsSet": {"metafields": [], "userErrors": [{"field": "value", "message": "invalid json"}]}}})
                )
            },
        ),
    )

    try:
        shopify_client.set_customer_metafield(777, "whatsapp_agent", "delivery_feedback", "not json")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_save_customer_feedback_writes_json_with_timestamp(monkeypatch):
    captured = {}

    def fake_set_metafield(customer_id, namespace, key, value, value_type="json"):
        captured.update({"customer_id": customer_id, "namespace": namespace, "key": key, "value": value})
        return {"metafield_id": "gid://shopify/Metafield/1"}

    monkeypatch.setattr(shopify_client, "set_customer_metafield", fake_set_metafield)

    shopify_client.save_customer_feedback(777, "delivery", {"rating": 5, "comment": "fast!"})

    assert captured["customer_id"] == 777
    assert captured["namespace"] == "whatsapp_agent"
    assert captured["key"] == "delivery_feedback"

    import json

    stored = json.loads(captured["value"])
    assert stored["rating"] == 5
    assert stored["comment"] == "fast!"
    assert "recorded_at" in stored
