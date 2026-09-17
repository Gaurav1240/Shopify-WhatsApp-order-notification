"""Hermetic stand-ins for the third-party SDKs so tests never hit the network.

Each fake is installed into sys.modules only if the real package isn't
already importable there, and individual tests monkeypatch the specific
methods/classes they care about (e.g. shopify.Order.find).
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _install_fake_shopify():
    if "shopify" in sys.modules:
        return
    shopify = types.ModuleType("shopify")

    class Session:
        @staticmethod
        def setup(**kwargs):
            pass

    class ShopifyResource:
        @staticmethod
        def set_site(site):
            pass

    class Order:
        @staticmethod
        def find(*args, **kwargs):
            raise NotImplementedError("patch shopify.Order.find in the test")

    class Transaction:
        def __init__(self, attrs=None):
            self.attrs = attrs or {}

        def save(self):
            raise NotImplementedError("patch shopify.Transaction in the test")

    shopify.Session = Session
    shopify.ShopifyResource = ShopifyResource
    shopify.Order = Order
    shopify.Transaction = Transaction
    sys.modules["shopify"] = shopify


def _install_fake_twilio():
    if "twilio" in sys.modules:
        return
    twilio = types.ModuleType("twilio")
    twilio_rest = types.ModuleType("twilio.rest")

    class Client:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("patch twilio.rest.Client in the test")

    twilio_rest.Client = Client
    twilio.rest = twilio_rest

    twiml = types.ModuleType("twilio.twiml")
    messaging_response = types.ModuleType("twilio.twiml.messaging_response")

    class MessagingResponse:
        def __init__(self):
            self._messages = []

        def message(self, body):
            self._messages.append(body)

        def __str__(self):
            bodies = "".join(f"<Message>{b}</Message>" for b in self._messages)
            return f"<Response>{bodies}</Response>"

    messaging_response.MessagingResponse = MessagingResponse
    twiml.messaging_response = messaging_response

    sys.modules["twilio"] = twilio
    sys.modules["twilio.rest"] = twilio_rest
    sys.modules["twilio.twiml"] = twiml
    sys.modules["twilio.twiml.messaging_response"] = messaging_response


def _install_fake_anthropic():
    if "anthropic" in sys.modules:
        return
    anthropic = types.ModuleType("anthropic")

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


_install_fake_shopify()
_install_fake_twilio()
_install_fake_anthropic()
_install_fake_dotenv()


@pytest.fixture(autouse=True)
def _isolated_state_files(tmp_path, monkeypatch):
    """Every test gets its own on-disk state/history files, in a temp dir.

    state_store/conversation_store read their path env vars once at import
    time, so patching the env var alone wouldn't affect already-imported
    modules — patch the module attribute directly instead.
    """
    import conversation_store
    import state_store

    monkeypatch.setattr(state_store, "STATE_PATH", str(tmp_path / "monitor_state.json"))
    monkeypatch.setattr(conversation_store, "HISTORY_PATH", str(tmp_path / "conversation_history.json"))


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    """Dummy credentials so _configure()/client construction never KeyErrors in tests."""
    monkeypatch.setenv("SHOPIFY_API_KEY", "test_key")
    monkeypatch.setenv("SHOPIFY_API_PASSWORD", "test_password")
    monkeypatch.setenv("SHOPIFY_STORE_NAME", "test-store.myshopify.com")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "+14155238886")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
