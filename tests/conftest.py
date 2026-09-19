"""Hermetic stand-ins for the third-party SDKs so tests never hit the network.

Shopify is now called directly over HTTP (via `requests`), so it needs no
fake module — tests monkeypatch `requests.post` instead. Anthropic still
needs a stand-in since its client is constructed at import time.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _install_fake_anthropic():
    if "anthropic" in sys.modules:
        return
    anthropic = types.ModuleType("anthropic")

    class _BetaMessages:
        def create(self, *args, **kwargs):
            raise NotImplementedError("patch client.beta.messages.create in the test")

    class _Beta:
        def __init__(self):
            self.messages = _BetaMessages()

    class Anthropic:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("patch anthropic.Anthropic in the test")

    anthropic.Anthropic = Anthropic
    sys.modules["anthropic"] = anthropic


def _install_fake_dotenv():
    try:
        import dotenv  # noqa: F401

        return
    except ImportError:
        pass
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv


_install_fake_anthropic()
_install_fake_dotenv()


@pytest.fixture(autouse=True)
def _isolated_state_files(tmp_path, monkeypatch):
    """Every test gets its own on-disk state/history files, in a temp dir.

    state_store/conversation_store read their path env vars once at import
    time, so patching the env var alone wouldn't affect already-imported
    modules — patch the module attribute directly instead.
    """
    import appointment_store
    import cart_state_store
    import conversation_store
    import discount_policy
    import discount_store
    import state_store

    monkeypatch.setattr(state_store, "STATE_PATH", str(tmp_path / "monitor_state.json"))
    monkeypatch.setattr(conversation_store, "HISTORY_PATH", str(tmp_path / "conversation_history.json"))
    monkeypatch.setattr(cart_state_store, "NOTIFIED_PATH", str(tmp_path / "abandoned_cart_notified.json"))
    monkeypatch.setattr(appointment_store, "APPOINTMENTS_PATH", str(tmp_path / "appointments.json"))
    monkeypatch.setattr(discount_store, "DISCOUNT_CODES_PATH", str(tmp_path / "discount_codes.json"))
    # Points at a nonexistent path by default so tests get discount_policy's
    # built-in defaults, not whatever this repo's real discount_policy.json holds.
    monkeypatch.setattr(discount_policy, "DISCOUNT_POLICY_PATH", str(tmp_path / "discount_policy.json"))


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    """Dummy credentials so client construction never KeyErrors in tests."""
    monkeypatch.setenv("SHOPIFY_STORE_NAME", "test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "test_shopify_token")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_whatsapp_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test_verify_token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
