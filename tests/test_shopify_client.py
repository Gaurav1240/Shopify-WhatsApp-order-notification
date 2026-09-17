import shopify_client


class FakeLineItem:
    def __init__(self, title, quantity):
        self.title = title
        self.quantity = quantity


class FakeAddress:
    def __init__(self, phone):
        self.phone = phone


class FakeCustomer:
    def __init__(self, phone):
        self.phone = phone


class FakeTransaction:
    def __init__(self, id, kind, status):
        self.id = id
        self.kind = kind
        self.status = status


class FakeOrder:
    def __init__(
        self,
        id=1001,
        name="#1001",
        email="a@example.com",
        total_price="45.00",
        financial_status="paid",
        fulfillment_status=None,
        created_at="2026-01-01T00:00:00Z",
        line_items=None,
        shipping_address=None,
        customer=None,
        transactions_list=None,
    ):
        self.id = id
        self.name = name
        self.email = email
        self.total_price = total_price
        self.financial_status = financial_status
        self.fulfillment_status = fulfillment_status
        self.created_at = created_at
        self.line_items = line_items or []
        self.shipping_address = shipping_address
        self.customer = customer
        self._transactions = transactions_list or []
        self.cancelled_with = None

    def cancel(self, reason=None):
        self.cancelled_with = reason
        self.financial_status = "voided"

    def transactions(self):
        return self._transactions


def _patch_find(monkeypatch, order):
    monkeypatch.setattr(shopify_client.shopify.Order, "find", staticmethod(lambda *a, **k: order))


def test_get_order_extracts_phone_from_shipping_address(monkeypatch):
    order = FakeOrder(line_items=[FakeLineItem("Mug", 2)], shipping_address=FakeAddress("+1 (555) 123-4567"))
    _patch_find(monkeypatch, order)

    result = shopify_client.get_order(1001)

    assert result["id"] == 1001
    assert result["phone"] == "+1 (555) 123-4567"
    assert result["line_items"] == [{"title": "Mug", "quantity": 2}]


def test_get_order_falls_back_to_customer_phone(monkeypatch):
    order = FakeOrder(shipping_address=None, customer=FakeCustomer("5551234567"))
    _patch_find(monkeypatch, order)

    result = shopify_client.get_order(1001)

    assert result["phone"] == "5551234567"


def test_get_order_status(monkeypatch):
    order = FakeOrder(financial_status="paid", fulfillment_status="fulfilled")
    _patch_find(monkeypatch, order)

    assert shopify_client.get_order_status(1001) == {
        "id": 1001,
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
    }


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


def test_cancel_order_calls_cancel_and_returns_refreshed_order(monkeypatch):
    order = FakeOrder()
    _patch_find(monkeypatch, order)

    result = shopify_client.cancel_order(1001, reason="customer")

    assert order.cancelled_with == "customer"
    assert result["financial_status"] == "voided"


def test_refund_order_uses_captured_transaction_as_parent(monkeypatch):
    parent_txn = FakeTransaction(id=9, kind="sale", status="success")
    order = FakeOrder(total_price="45.00", transactions_list=[parent_txn])
    _patch_find(monkeypatch, order)

    created = {}

    class FakeRefundTransaction:
        def __init__(self, attrs):
            created.update(attrs)
            self.id = 555

        def save(self):
            return True

    monkeypatch.setattr(shopify_client.shopify, "Transaction", FakeRefundTransaction)

    result = shopify_client.refund_order(1001, reason="damaged")

    assert created["kind"] == "refund"
    assert created["parent_id"] == 9
    assert created["amount"] == "45.00"
    assert result == {
        "order_id": 1001,
        "refund_transaction_id": 555,
        "amount": "45.00",
        "reason": "damaged",
    }


def test_refund_order_uses_explicit_amount(monkeypatch):
    parent_txn = FakeTransaction(id=9, kind="capture", status="success")
    order = FakeOrder(total_price="45.00", transactions_list=[parent_txn])
    _patch_find(monkeypatch, order)

    created = {}

    class FakeRefundTransaction:
        def __init__(self, attrs):
            created.update(attrs)
            self.id = 555

        def save(self):
            return True

    monkeypatch.setattr(shopify_client.shopify, "Transaction", FakeRefundTransaction)

    shopify_client.refund_order(1001, amount="10.00")

    assert created["amount"] == "10.00"


def test_refund_order_raises_without_refundable_transaction(monkeypatch):
    order = FakeOrder(transactions_list=[])
    _patch_find(monkeypatch, order)

    try:
        shopify_client.refund_order(1001)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_refund_order_raises_when_save_fails(monkeypatch):
    parent_txn = FakeTransaction(id=9, kind="capture", status="success")
    order = FakeOrder(transactions_list=[parent_txn])
    _patch_find(monkeypatch, order)

    class _Errors:
        @staticmethod
        def full_messages():
            return ["card declined"]

    class FailingTransaction:
        def __init__(self, attrs):
            self.errors = _Errors()

        def save(self):
            return False

    monkeypatch.setattr(shopify_client.shopify, "Transaction", FailingTransaction)

    try:
        shopify_client.refund_order(1001)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
