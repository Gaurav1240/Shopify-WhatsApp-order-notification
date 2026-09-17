# Shopify-WhatsApp order notification (agentic)

An agentic Shopify-to-WhatsApp integration: instead of a fixed message
template and hardcoded rules, a Claude agent with tools decides what to say
and when. Three agents share the same tool set (`tools.py`):

- **Notification agent** — triggered by the Shopify order-creation webhook.
  Drafts a personalized WhatsApp confirmation and sends it.
- **Support agent** — triggered by inbound WhatsApp messages. Looks up the
  sender's orders and answers questions conversationally, remembering prior
  messages from the same phone number (`conversation_store.py`) so it can
  handle multi-turn flows. It can also cancel an order or issue a refund, but
  only after the customer has explicitly confirmed in the conversation — it's
  instructed to always ask first and never act on the same turn it was asked.
- **Monitoring agent** (`monitor.py`) — polls Shopify on an interval, notices
  order-status changes nobody told it about (shipped, cancelled, refunded,
  ...), and decides on its own whether the customer should hear about it.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # then fill in your real credentials
```

Required environment variables (see `.env.example`):

- `SHOPIFY_API_KEY`, `SHOPIFY_API_PASSWORD`, `SHOPIFY_STORE_NAME`
- `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`
  (from Meta's WhatsApp Business Platform — see below)
- `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`)

## Running

Start the webhook server:

```
python flask_app.py
```

Optionally start the autonomous monitor in a separate process:

```
python monitor.py
```

## Testing

```
pip install -r requirements-dev.txt
pytest
```

All third-party SDKs (Shopify, Meta's Graph API calls, Anthropic) are stubbed
out in `tests/conftest.py`, so the suite runs offline with no real
credentials.

## Wiring it up to Shopify and Meta's WhatsApp Business Platform

This uses Meta's WhatsApp Business **Cloud API** directly (not Twilio).

1. In [Meta for Developers](https://developers.facebook.com/apps), create an
   app with the WhatsApp product added, or use an existing WhatsApp Business
   Account. From the app's WhatsApp > API Setup page, note the **phone
   number ID** and generate a **System User access token** with the
   `whatsapp_business_messaging` permission (use a permanent token, not the
   default 24-hour test token, for anything beyond quick testing).
   - Meta also offers a **WhatsApp Business Tools MCP**
     (`developers.facebook.com/documentation/mcp/whatsapp-business-tools-mcp`)
     that lets an AI coding assistant walk you through this setup, create
     message templates, and send test messages conversationally. It's a
     separate, chat-driven developer tool (auth'd via Facebook Login for
     Business) — it's not something this app calls at runtime, so it's worth
     using once during setup but isn't a dependency here.
2. Set `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and a
   `WHATSAPP_VERIFY_TOKEN` of your choosing in `.env`.
3. In the app's WhatsApp > Configuration page, set the webhook callback URL
   to `https://<your-host>/whatsapp_webhook` and the verify token to the same
   `WHATSAPP_VERIFY_TOKEN` value — Meta will GET that URL once to confirm
   ownership. Then subscribe to the `messages` webhook field.
4. In your Shopify admin, go to **Settings > Notifications > Webhooks** and
   create a webhook for the "Order creation" event, in JSON format, pointing
   at `https://<your-host>/order_webhook`.

## Project layout

- `shopify_client.py` — Shopify API access (order lookups, recent orders,
  phone matching, cancellations, refunds).
- `whatsapp_client.py` — sends WhatsApp messages via Meta's WhatsApp Business
  Cloud API (Graph API).
- `tools.py` — the tool schemas and dispatcher every agent shares.
- `agent.py` — the tool-use loop (Claude decides which tools to call).
- `flask_app.py` — the two webhook endpoints.
- `conversation_store.py` — per-phone-number chat history for the support
  agent's multi-turn flows.
- `monitor.py` / `state_store.py` — the autonomous status-change monitor and
  its small on-disk state.
- `tests/` — unit tests covering the tools, agent loop, webhooks, and
  monitor, with the Shopify/WhatsApp/Anthropic SDKs stubbed out.
