# Shopify-WhatsApp order notification (agentic)

An agentic Shopify-to-WhatsApp integration: instead of a fixed message
template and hardcoded rules, a Claude agent with tools decides what to say
and when. Three agents share the same tool set (`tools.py`):

- **Notification agent** — triggered by the Shopify order-creation webhook.
  Drafts a personalized WhatsApp confirmation and sends it.
- **Support agent** — triggered by inbound WhatsApp messages. Looks up the
  sender's orders and answers questions conversationally, remembering prior
  messages from the same phone number (`conversation_store.py`) so it can
  handle multi-turn flows. It can cancel an order, issue a refund, or
  request a return/exchange — all only after the customer has explicitly
  confirmed in the conversation; it's instructed to always ask first and
  never act on the same turn it was asked. For returns specifically, when
  `STOREFRONT_MCP_URL` is configured it first checks the store's actual
  return policy (window, excluded items, who pays shipping) via Shopify's
  Storefront MCP rather than guessing, before deciding what's eligible. It
  also captures customer feedback — delivery-experience comments, and why
  a customer is returning something — and writes it onto that customer's
  Shopify record as a metafield (see below), so store staff can see it in
  Shopify admin without needing WhatsApp access.
- **Monitoring agent** (`monitor.py`) — polls Shopify on an interval, notices
  order-status changes nobody told it about (shipped, cancelled, refunded,
  ...), and decides on its own whether the customer should hear about it.
  When an order becomes fulfilled/delivered, it tacks on a casual ask for
  delivery feedback — whatever the customer replies with is picked up and
  saved by the support agent, same as above.
- **Cart-recovery agent** (`abandoned_cart.py`) — polls Shopify's abandoned-
  checkouts list for carts that were started but never completed. For each
  one it hasn't already messaged, it drafts and sends a friendly WhatsApp
  nudge naming what's in the cart and including the checkout's recovery
  link. `cart_state_store.py` remembers which checkouts were already
  messaged so nobody gets nudged twice. The support agent can also look up
  a customer's abandoned checkout by phone if they ask about it.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # then fill in your real credentials
```

Required environment variables (see `.env.example`):

- `SHOPIFY_STORE_NAME`, `SHOPIFY_ACCESS_TOKEN` (an Admin API access token —
  see below)
- `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`
  (from Meta's WhatsApp Business Platform — see below)
- `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`)
- `STOREFRONT_MCP_URL` (optional — enables real return-policy lookups)

## Running

Start the webhook server:

```
python flask_app.py
```

Optionally start the autonomous monitor and/or the cart-recovery poller in
separate processes:

```
python monitor.py
python abandoned_cart.py
```

## Testing

```
pip install -r requirements-dev.txt
pytest
```

Shopify is called directly over HTTP (`requests`), so tests monkeypatch
`requests.post` with canned GraphQL responses rather than stubbing an SDK.
Anthropic and Meta's Graph API calls are stubbed the same way, so the suite
runs offline with no real credentials.

## Wiring it up to Shopify and Meta's WhatsApp Business Platform

This talks to Shopify's **GraphQL Admin API** directly (no SDK) and to
Meta's WhatsApp Business **Cloud API** directly (not Twilio).

### Shopify

1. In your Shopify admin, go to **Settings > Apps and sales channels >
   Develop apps**, create a custom app, and configure Admin API scopes:
   `read_orders`, `write_orders`, `read_returns`, `write_returns`, and
   `write_customers` (needed to save feedback as a customer metafield).
   Install the app and copy its **Admin API access token** into
   `SHOPIFY_ACCESS_TOKEN`; set `SHOPIFY_STORE_NAME` to
   `your-store.myshopify.com`.
2. Set `SHOPIFY_API_VERSION` to Shopify's current quarterly API version
   (check `shopify.dev/docs/api/admin-graphql` — the one in `.env.example`
   may be out of date by the time you set this up).
3. Go to **Settings > Notifications > Webhooks** and create a webhook for
   the "Order creation" event, in JSON format, pointing at
   `https://<your-host>/order_webhook`.
4. Optional — for return-policy lookups: set `STOREFRONT_MCP_URL` to your
   store's Storefront MCP endpoint (typically
   `https://your-store.myshopify.com/api/mcp`; it needs no auth).

> **Note on the GraphQL queries/mutations in `shopify_client.py`:** they're
> written from Shopify's published Admin GraphQL docs, but this project was
> built in a sandboxed environment with no network access to Shopify's API
> or schema explorer, so the exact field/enum names for `orderCancel`,
> `refundCreate`, `abandonedCheckouts`, `returnRequest`, and
> `metafieldsSet` are **not** verified against a live store. Smoke-test each
> flow against a Shopify dev store before relying on it in production —
> check current field names in Shopify's GraphiQL app if a call fails.
> `metafieldsSet` is the most stable/long-standing of these, so it's the
> least likely to have drifted.

### Meta WhatsApp

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

## Where customer feedback shows up in Shopify admin

The support agent writes feedback onto the customer's own record using
Shopify's [metafields](https://help.shopify.com/en/manual/custom-data) —
custom fields you can attach to any resource. It writes two possible keys,
both under the `whatsapp_agent` namespace, each holding the *most recent*
feedback of that type as JSON (not a running history):

- `whatsapp_agent.delivery_feedback` — `{comment, rating?, order_id?, recorded_at}`
- `whatsapp_agent.return_feedback` — `{comment, order_id?, recorded_at}`

To see it: open the customer in Shopify admin (**Customers > [name]**),
scroll to **Metafields**, and add "WhatsApp Agent" definitions for these
two keys (Settings > Custom data > Customers > Add definition) if you want
them to render as labeled fields rather than raw JSON.

## Project layout

- `shopify_client.py` — Shopify GraphQL Admin API access (order lookups,
  recent orders, phone matching, cancellations, refunds, abandoned
  checkouts, returns, customer feedback metafields) via raw `requests`
  calls, no SDK.
- `whatsapp_client.py` — sends WhatsApp messages via Meta's WhatsApp Business
  Cloud API (Graph API).
- `tools.py` — the tool schemas and dispatcher every agent shares.
- `agent.py` — the tool-use loop (Claude decides which tools to call),
  including an optional connection to a remote MCP server (`mcp_server_url`)
  for the support agent's Storefront MCP policy lookups.
- `flask_app.py` — the two webhook endpoints.
- `conversation_store.py` — per-phone-number chat history for the support
  agent's multi-turn flows.
- `monitor.py` / `state_store.py` — the autonomous status-change monitor and
  its small on-disk state.
- `abandoned_cart.py` / `cart_state_store.py` — the cart-recovery poller and
  its small on-disk "already messaged" set.
- `tests/` — unit tests covering the tools, agent loop, webhooks, monitor,
  cart recovery, and returns, with the Shopify GraphQL calls, WhatsApp/Meta
  calls, and Anthropic client all stubbed out.

## Possible enhancement: Shopify's Storefront Catalog

The cart-recovery message and returns policy lookup are the two places
Storefront MCP data would help most; product *catalog* search
(`search_catalog`, `get_product`) isn't wired in yet. It could enrich the
cart-recovery message with live price/stock/images, or let the support
agent answer general product questions ("do you have this in blue?") — not
built since neither of the two flows implemented here strictly needs it.
