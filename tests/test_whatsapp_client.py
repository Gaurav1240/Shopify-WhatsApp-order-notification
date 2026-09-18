import whatsapp_client


class FakeHTTPResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def test_send_whatsapp_message_posts_to_graph_api(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeHTTPResponse({"messages": [{"id": "wamid.123"}]})

    monkeypatch.setattr(whatsapp_client.requests, "post", fake_post)

    result = whatsapp_client.send_whatsapp_message("+15551234567", "hello!")

    assert captured["url"] == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert captured["headers"] == {"Authorization": "Bearer test_whatsapp_token"}
    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "to": "15551234567",
        "type": "text",
        "text": {"body": "hello!"},
    }
    assert result == {"id": "wamid.123", "to": "+15551234567", "body": "hello!"}


def test_send_whatsapp_message_strips_whatsapp_prefix(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["to"] = json["to"]
        return FakeHTTPResponse({"messages": [{"id": "wamid.1"}]})

    monkeypatch.setattr(whatsapp_client.requests, "post", fake_post)

    whatsapp_client.send_whatsapp_message("whatsapp:+15551234567", "hi")

    assert captured["to"] == "15551234567"


def test_send_whatsapp_message_raises_on_http_error(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeHTTPResponse({"error": "bad request"}, status_code=400)

    monkeypatch.setattr(whatsapp_client.requests, "post", fake_post)

    try:
        whatsapp_client.send_whatsapp_message("+15551234567", "hi")
        assert False, "expected an exception"
    except RuntimeError:
        pass


def test_uses_custom_api_version(monkeypatch):
    monkeypatch.setattr(whatsapp_client, "GRAPH_API_VERSION", "v99.0")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        return FakeHTTPResponse({"messages": [{"id": "wamid.1"}]})

    monkeypatch.setattr(whatsapp_client.requests, "post", fake_post)

    whatsapp_client.send_whatsapp_message("+1555", "hi")

    assert captured["url"] == "https://graph.facebook.com/v99.0/1234567890/messages"
