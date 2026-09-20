import discounts


def test_get_or_create_reuses_existing_active_code(monkeypatch):
    existing = {"code": "SAVE10-ABCDEF", "percent": 10}
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda checkout_id: existing)

    called = []
    monkeypatch.setattr(
        discounts.shopify_client, "create_discount_code", lambda *a, **k: called.append((a, k))
    )

    result = discounts.get_or_create("checkout-1", "+15551234567", 40)

    assert result == existing
    assert called == []


def test_get_or_create_creates_new_code_within_policy(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda checkout_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/1")
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 0)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 20,
            "tiers": [{"min_cart_value": 0, "discount_percent": 10}],
            "long_abandoned_hours": 48,
            "long_abandoned_bonus_percent": 5,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )

    created_calls = []
    monkeypatch.setattr(
        discounts.shopify_client,
        "create_discount_code",
        lambda code, percent, expires_at: created_calls.append((code, percent, expires_at)),
    )

    recorded = {}
    monkeypatch.setattr(
        discounts.discount_store,
        "record_code",
        lambda **kwargs: recorded.update(kwargs) or {**kwargs, "id": "recorded"},
    )

    result = discounts.get_or_create("checkout-1", "+15551234567", 40)

    assert len(created_calls) == 1
    assert created_calls[0][1] == 10
    assert recorded["checkout_id"] == "checkout-1"
    assert recorded["customer_key"] == "gid://shopify/Customer/1"
    assert recorded["percent"] == 10
    assert result["id"] == "recorded"


def test_get_or_create_falls_back_to_phone_when_no_customer_found(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda checkout_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: None)
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 0)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 20,
            "tiers": [{"min_cart_value": 0, "discount_percent": 10}],
            "long_abandoned_hours": 48,
            "long_abandoned_bonus_percent": 5,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )
    monkeypatch.setattr(discounts.shopify_client, "create_discount_code", lambda *a, **k: None)

    recorded = {}
    monkeypatch.setattr(
        discounts.discount_store, "record_code", lambda **kwargs: recorded.update(kwargs) or kwargs
    )

    discounts.get_or_create("checkout-1", "+15551234567", 40)

    assert recorded["customer_key"] == "+15551234567"


def test_get_or_create_for_order_reuses_existing_active_code(monkeypatch):
    existing = {"code": "SAVE10-ABCDEF", "percent": 10}
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda order_id: existing)

    called = []
    monkeypatch.setattr(discounts.shopify_client, "create_discount_code", lambda *a, **k: called.append((a, k)))

    result = discounts.get_or_create_for_order("1001", "+15551234567")

    assert result == existing
    assert called == []


def test_get_or_create_for_order_uses_flat_policy_percent(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda order_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/1")
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 0)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 20,
            "order_issue_compensation_percent": 10,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )

    created_calls = []
    monkeypatch.setattr(
        discounts.shopify_client,
        "create_discount_code",
        lambda code, percent, expires_at: created_calls.append((code, percent, expires_at)),
    )

    recorded = {}
    monkeypatch.setattr(
        discounts.discount_store,
        "record_code",
        lambda **kwargs: recorded.update(kwargs) or {**kwargs, "id": "recorded"},
    )

    result = discounts.get_or_create_for_order("1001", "+15551234567", reason="order cancelled")

    assert created_calls[0][1] == 10
    assert recorded["checkout_id"] == "1001"
    assert recorded["customer_key"] == "gid://shopify/Customer/1"
    assert result["id"] == "recorded"


def test_get_or_create_for_order_caps_percent_at_max_discount(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda order_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: None)
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 0)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 5,
            "order_issue_compensation_percent": 10,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )

    created_calls = []
    monkeypatch.setattr(
        discounts.shopify_client,
        "create_discount_code",
        lambda code, percent, expires_at: created_calls.append(percent),
    )
    monkeypatch.setattr(discounts.discount_store, "record_code", lambda **kwargs: kwargs)

    discounts.get_or_create_for_order("1001", "+15551234567")

    assert created_calls == [5]


def test_get_or_create_for_order_returns_ineligible_when_customer_over_limit(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda order_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/1")
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 2)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 20,
            "order_issue_compensation_percent": 10,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )
    called = []
    monkeypatch.setattr(discounts.shopify_client, "create_discount_code", lambda *a, **k: called.append((a, k)))

    result = discounts.get_or_create_for_order("1001", "+15551234567")

    assert result == {"eligible": False, "reason": "Customer has reached the maximum discount codes allowed in this window"}
    assert called == []


def test_get_or_create_returns_ineligible_when_customer_over_limit(monkeypatch):
    monkeypatch.setattr(discounts.discount_store, "find_active_code", lambda checkout_id: None)
    monkeypatch.setattr(discounts.shopify_client, "find_customer_id_by_phone", lambda phone: "gid://shopify/Customer/1")
    monkeypatch.setattr(discounts.discount_store, "count_recent_codes", lambda key, days: 2)
    monkeypatch.setattr(
        discounts.discount_policy,
        "load_policy",
        lambda: {
            "max_discount_percent": 20,
            "tiers": [{"min_cart_value": 0, "discount_percent": 10}],
            "long_abandoned_hours": 48,
            "long_abandoned_bonus_percent": 5,
            "code_expiry_hours": 72,
            "max_codes_per_customer": 2,
            "max_codes_window_days": 30,
        },
    )

    called = []
    monkeypatch.setattr(discounts.shopify_client, "create_discount_code", lambda *a, **k: called.append((a, k)))

    result = discounts.get_or_create("checkout-1", "+15551234567", 40)

    assert result == {"eligible": False, "reason": "Customer has reached the maximum discount codes allowed in this window"}
    assert called == []
