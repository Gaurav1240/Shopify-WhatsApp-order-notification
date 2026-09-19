from datetime import datetime, timedelta

import discount_store


def test_find_active_code_returns_none_when_no_record():
    assert discount_store.find_active_code("checkout-1") is None


def test_record_and_find_active_code():
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    discount_store.record_code("checkout-1", "cust-1", "SAVE5-ABCDEF", 5, expires_at)

    record = discount_store.find_active_code("checkout-1")

    assert record["code"] == "SAVE5-ABCDEF"
    assert record["percent"] == 5


def test_find_active_code_ignores_expired_records():
    expired_at = (datetime.now() - timedelta(hours=1)).isoformat()
    discount_store.record_code("checkout-1", "cust-1", "SAVE5-ABCDEF", 5, expired_at)

    assert discount_store.find_active_code("checkout-1") is None


def test_count_recent_codes_counts_within_window():
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    discount_store.record_code("checkout-1", "cust-1", "SAVE5-AAAAAA", 5, expires_at)
    discount_store.record_code("checkout-2", "cust-1", "SAVE5-BBBBBB", 5, expires_at)
    discount_store.record_code("checkout-3", "cust-2", "SAVE5-CCCCCC", 5, expires_at)

    assert discount_store.count_recent_codes("cust-1", days=30) == 2
    assert discount_store.count_recent_codes("cust-2", days=30) == 1
    assert discount_store.count_recent_codes("cust-3", days=30) == 0


def test_count_recent_codes_ignores_records_outside_window(monkeypatch):
    codes = [
        {
            "checkout_id": "checkout-1",
            "customer_key": "cust-1",
            "code": "SAVE5-AAAAAA",
            "percent": 5,
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "created_at": (datetime.now() - timedelta(days=60)).isoformat(),
        }
    ]
    monkeypatch.setattr(discount_store, "_load", lambda: codes)

    assert discount_store.count_recent_codes("cust-1", days=30) == 0
