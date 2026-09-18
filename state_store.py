"""Tiny JSON-file persistence for the order-monitoring agent's last-seen statuses."""

import json
import os

STATE_PATH = os.environ.get("MONITOR_STATE_PATH", "monitor_state.json")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)
