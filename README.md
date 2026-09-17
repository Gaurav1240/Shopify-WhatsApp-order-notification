# Shopify-WhatsApp order notification (agentic)

An agentic Shopify-to-WhatsApp integration: instead of a fixed message
template and hardcoded rules, a Claude agent with tools decides what to say
and when. Three agents share the same tool set (`tools.py`):

- **Notification agent** — triggered by the Shopify order-creation webhook.
  Drafts a personalized WhatsApp confirmation and sends it.
- **Support agent** — triggered by inbound WhatsApp messages. Looks up the
  sender's orders and answers questions conversationally.
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
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
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

## Wiring it up to Shopify and Twilio

1. In your Shopify admin, go to **Settings > Notifications > Webhooks** and
   create a webhook for the "Order creation" event, in JSON format, pointing
   at `https://<your-host>/order_webhook`.
2. In the Twilio console, set the WhatsApp sandbox/number's "when a message
   comes in" webhook to `https://<your-host>/whatsapp_webhook`.

## Project layout

- `shopify_client.py` — Shopify API access (order lookups, recent orders,
  phone matching).
- `whatsapp_client.py` — sends WhatsApp messages via Twilio.
- `tools.py` — the tool schemas and dispatcher every agent shares.
- `agent.py` — the tool-use loop (Claude decides which tools to call).
- `flask_app.py` — the two webhook endpoints.
- `monitor.py` / `state_store.py` — the autonomous status-change monitor and
  its small on-disk state.
