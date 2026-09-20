import json

import discount_policy


def test_load_policy_returns_defaults_when_file_missing():
    policy = discount_policy.load_policy()

    assert policy == discount_policy._DEFAULT_POLICY


def test_load_policy_merges_file_over_defaults():
    with open(discount_policy.DISCOUNT_POLICY_PATH, "w") as f:
        json.dump({"max_discount_percent": 10}, f)

    policy = discount_policy.load_policy()

    assert policy["max_discount_percent"] == 10
    assert policy["tiers"] == discount_policy._DEFAULT_POLICY["tiers"]


def test_compute_discount_percent_uses_highest_qualifying_tier():
    assert discount_policy.compute_discount_percent(200) == 15
    assert discount_policy.compute_discount_percent(75) == 10
    assert discount_policy.compute_discount_percent(10) == 5


def test_compute_discount_percent_adds_long_abandoned_bonus():
    assert discount_policy.compute_discount_percent(10, hours_since_abandoned=48) == 10


def test_compute_discount_percent_caps_at_max_discount_percent():
    policy = {
        "max_discount_percent": 12,
        "tiers": [{"min_cart_value": 0, "discount_percent": 15}],
        "long_abandoned_hours": 48,
        "long_abandoned_bonus_percent": 5,
    }

    assert discount_policy.compute_discount_percent(100, policy=policy) == 12


def test_compute_discount_percent_below_all_tiers_is_zero():
    policy = {
        "max_discount_percent": 20,
        "tiers": [{"min_cart_value": 50, "discount_percent": 10}],
        "long_abandoned_hours": 48,
        "long_abandoned_bonus_percent": 5,
    }

    assert discount_policy.compute_discount_percent(10, policy=policy) == 0
