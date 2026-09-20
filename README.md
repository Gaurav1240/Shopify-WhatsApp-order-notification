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
  Shopify admin without needing WhatsApp access. It can also book
  appointments (return-pickup, delivery, or general store visits) — see
  "Appointment booking" below.
- **Monitoring agent** (`monitor.py`) — polls Shopify on an interval, notices
  order-status changes nobody told it about (shipped, cancelled, refunded,
  ...), and decides on its own whether the customer should hear about it.
  When an order becomes fulfilled/delivered, it tacks on a casual ask for
  delivery feedback — whatever the customer replies with is picked up and
  saved by the support agent, same as above. When the change is bad news the
  store caused (cancelled, payment failed), it can proactively offer a
  one-time compensation discount instead of just an apology — see
  "Abandoned-cart discount policy" below, which this reuses.
- **Cart-recovery agent** (`abandoned_cart.py`) — polls Shopify's abandoned-
  checkouts list for carts that were started but never completed. For each
  one it hasn't already messaged, it drafts and sends a friendly WhatsApp
  nudge naming what's in the cart and including the checkout's recovery
  link. `cart_state_store.py` remembers which checkouts were already
  messaged so nobody gets nudged twice. The support agent can also look up
  a customer's abandoned checkout by phone if they ask about it. It can
  also offer a personalized discount code — see "Abandoned-cart discount
  policy" below.

All of the above tools are also reachable directly by an external system —
see "MCP server (plugging into another agentic-commerce system)" below.

**One thread, not four silos.** Every proactive message any agent sends
(notify, monitor, cart-recovery) is logged by `notification_log.py`, keyed
by phone number. When that customer later messages in, the support agent is
told what's already been sent to them as context on their message — so "did
that already go out?" doesn't require them to explain what "that" is. This
is deliberately a separate, unbounded append-only log rather than being
folded into `conversation_store.py`'s turn history: that history round-trips
through the Anthropic Messages API, which requires strict user/assistant
role alternation, and a proactive message (or two in a row) has no paired
customer turn to alternate with.

**Tap, don't type.** Proactive messages can end in up to 3 quick-reply
buttons (`send_whatsapp_buttons`, e.g. "Track order" / "Need help?") instead
of asking the customer to type a reply — the notification and monitoring
agents both have this option, and use it especially for bad-news updates.

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
- Appointment booking uses sensible defaults (`APPOINTMENT_HOURS_START/END`,
  `APPOINTMENT_SLOT_MINUTES`, `APPOINTMENT_DAYS_AHEAD` — see below), nothing
  required to set

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

Optionally start the MCP server, to let another system call these tools
directly (see "MCP server" below):

```
python mcp_server.py
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
   `read_orders`, `write_orders`, `read_returns`, `write_returns`,
   `write_customers` (needed to save feedback as a customer metafield), and
   `write_discounts` (needed for abandoned-cart discount codes). Install
   the app and copy its **Admin API access token** into
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

## Appointment booking

Shopify has no built-in scheduling concept, so `appointment_store.py` is its
own small local calendar: a flat on-disk list of appointments plus a slot
generator (business hours × workdays × `APPOINTMENT_SLOT_MINUTES`
increments — defaults 9am-5pm, Mon-Fri, hourly, 7 days ahead) that filters
out whatever's already booked. `appointments.py` books/cancels against that
calendar and then mirrors the result onto Shopify — best-effort, logged not
raised on failure — so the local calendar always stays the source of truth
for "is this slot free."

Three appointment types, each mirrored to a different place in admin:

- `return_pickup` and `delivery` — tied to an order; written onto that
  **order's** metafields (`whatsapp_agent.return_pickup_appointment` /
  `whatsapp_agent.delivery_appointment`) since that's where staff fulfilling
  it will look.
- `service` — anything else (a fitting, consultation, repair...); written
  onto the **customer's** metafields
  (`whatsapp_agent.service_appointment`), same place as feedback.

Known simplifications: slots are naive local time (no explicit timezone),
and each appointment type has exactly one bookable slot per time (no
per-type capacity — e.g. no "3 fitting rooms available at once"). Fine for
a single small store; revisit if that stops being true.

## Abandoned-cart discount policy

The cart-recovery agent can offer a one-time discount code alongside its
recovery message, but it never picks the discount amount itself — it calls
`create_discount_code`, which computes a percentage from `discount_policy.json`
(cart-value tiers, a bonus for a long-abandoned cart, and a hard
`max_discount_percent` ceiling) and enforces a per-customer cap
(`max_codes_per_customer` within `max_codes_window_days`) so a customer can't
farm discounts by repeatedly abandoning their cart. Edit
`discount_policy.json` directly to tune it for your store — no code change
needed. The same checkout is never issued two different codes: if one is
still valid (`code_expiry_hours`), it's reused rather than a new one minted.
Issued codes are logged to `discount_codes.json` for audit and to enforce the
per-customer cap; `discountCodeBasicCreate` (Shopify's discount-code
mutation) carries the same not-verified-against-a-live-schema caveat as the
rest of `shopify_client.py`.

Known simplification: eligibility/amount is decided per-message from the
current cart value and abandonment age — there's no cross-checkout customer
history beyond the rate limit. If the agent decides the customer isn't
eligible for a discount (`create_discount_code` returns
`{"eligible": false}`), it's instructed to just send the plain recovery
message without mentioning one.

The monitoring agent uses the same policy/store, through a second entry
point (`create_order_compensation_code`) rather than a separate mechanism:
when a status change is bad news the store caused, it can offer a flat
`order_issue_compensation_percent` (still capped at `max_discount_percent`,
still rate-limited the same way) as an apology, keyed by order id instead of
checkout id so it doesn't collide with an unrelated abandoned-cart code for
the same customer.

## MCP server (plugging into another agentic-commerce system)

`mcp_server.py` exposes every tool in `tools.py` — order lookups, cancel,
refund, returns, discount codes, appointments — to an external MCP-compatible
client over **Streamable HTTP**, so another agent/system can call this
store's commerce actions directly instead of going through WhatsApp. It's a
thin wrapper: `tools.TOOL_SCHEMAS` becomes the MCP tool list, and every call
is dispatched through the same `tools.run_tool` the WhatsApp agents use.

**Setup:**

1. Set `MCP_BEARER_TOKEN` in `.env` to a long random secret (e.g. `openssl
   rand -hex 32`) — every request must send `Authorization: Bearer
   <that value>`. Without it set, the server refuses all requests (503)
   rather than opening up unauthenticated; this also fails closed if the app
   is mounted directly (`uvicorn mcp_server:app`) instead of run via
   `python mcp_server.py`.
2. `python mcp_server.py` — serves MCP at `http://<MCP_HOST>:<MCP_PORT>/mcp`
   (defaults `0.0.0.0:8000`).
3. Point the other system's MCP client at that URL with the bearer token.

**Guardrail note, read before connecting anything:** inside this project,
`cancel_order`/`refund_order`/`request_return` are only ever called by the
WhatsApp support agent after its system prompt has told it to wait for the
customer's explicit confirmation — that's an instruction to one specific
Claude agent, not something this server enforces. Any system holding
`MCP_BEARER_TOKEN` can call any tool here, including those three, with no
confirmation step of its own. Before plugging something in, confirm *it*
enforces its own confirmation gate for irreversible actions — this server
won't.

Built and smoke-tested with a live HTTP round trip (`initialize`,
`tools/list`, `tools/call`) against `mcp==2.2.0` / `uvicorn==0.53.0`, pinned
exactly in `requirements.txt` since the Streamable HTTP API is young enough
to plausibly change between versions — if you bump either, re-run that round
trip before trusting it.

## Project layout

- `shopify_client.py` — Shopify GraphQL Admin API access (order lookups,
  recent orders, phone matching, cancellations, refunds, abandoned
  checkouts, returns, order/customer metafields for feedback and
  appointments) via raw `requests` calls, no SDK.
- `whatsapp_client.py` — sends WhatsApp messages via Meta's WhatsApp Business
  Cloud API (Graph API), plain text (`send_whatsapp_message`) or with up to
  3 tappable quick-reply buttons (`send_whatsapp_buttons`).
- `tools.py` — the tool schemas and dispatcher every agent shares.
- `agent.py` — the tool-use loop (Claude decides which tools to call),
  including an optional connection to a remote MCP server (`mcp_server_url`)
  for the support agent's Storefront MCP policy lookups.
- `flask_app.py` — the two webhook endpoints.
- `conversation_store.py` — per-phone-number chat history for the support
  agent's multi-turn flows.
- `notification_log.py` — per-phone-number log of proactive messages any
  agent has sent, given to the support agent as context (not part of the
  strict turn history `conversation_store.py` round-trips through the
  Messages API).
- `monitor.py` / `state_store.py` — the autonomous status-change monitor and
  its small on-disk state.
- `abandoned_cart.py` / `cart_state_store.py` — the cart-recovery poller and
  its small on-disk "already messaged" set.
- `discounts.py` / `discount_policy.py` / `discount_store.py` — computes and
  issues discount codes (abandoned-cart recovery, and order-issue
  compensation) within a merchant-configured policy (`discount_policy.json`),
  tracking issued codes for reuse and rate-limiting (`discount_codes.json`).
- `appointments.py` / `appointment_store.py` — the appointment-booking
  orchestration (Shopify write-through) and the local slot calendar it
  books against.
- `mcp_server.py` — exposes `tools.py`'s tools to an external system over
  MCP (Streamable HTTP), bearer-token gated.
- `tests/` — unit tests covering the tools, agent loop, webhooks, monitor,
  cart recovery, returns, and appointments, with the Shopify GraphQL calls,
  WhatsApp/Meta calls, and Anthropic client all stubbed out.

## Possible enhancement: Shopify's Storefront Catalog

The cart-recovery message and returns policy lookup are the two places
Storefront MCP data would help most; product *catalog* search
(`search_catalog`, `get_product`) isn't wired in yet. It could enrich the
cart-recovery message with live price/stock/images, or let the support
agent answer general product questions ("do you have this in blue?") — not
built since neither of the two flows implemented here strictly needs it.
