"""Tool schemas (Anthropic tool-use format) and dispatcher shared by every agent."""

import shopify_client
import whatsapp_client

TOOL_SCHEMAS = [
    {
        "name": "get_order",
        "description": "Look up full details for a single Shopify order by its numeric order ID.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "The Shopify order ID."}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Get just the financial and fulfillment status for a single Shopify order.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "The Shopify order ID."}},
            "required": ["order_id"],
        },
    },
    {
        "name": "list_recent_orders",
        "description": "List Shopify orders created in the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {"type": "integer", "description": "How many days back to search. Defaults to 7."}
            },
        },
    },
    {
        "name": "find_orders_by_phone",
        "description": "Find Shopify orders placed with a given phone number, to identify who is messaging on WhatsApp.",
        "input_schema": {
            "type": "object",
            "properties": {"phone": {"type": "string", "description": "Phone number, with or without punctuation."}},
            "required": ["phone"],
        },
    },
    {
        "name": "send_whatsapp_message",
        "description": "Send a WhatsApp message to a customer's phone number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Destination phone number, e.g. +15551234567."},
                "body": {"type": "string", "description": "Message text to send."},
            },
            "required": ["to", "body"],
        },
    },
]

_HANDLERS = {
    "get_order": lambda i: shopify_client.get_order(i["order_id"]),
    "get_order_status": lambda i: shopify_client.get_order_status(i["order_id"]),
    "list_recent_orders": lambda i: shopify_client.list_recent_orders(days_back=i.get("days_back", 7)),
    "find_orders_by_phone": lambda i: shopify_client.find_orders_by_phone(i["phone"]),
    "send_whatsapp_message": lambda i: whatsapp_client.send_whatsapp_message(i["to"], i["body"]),
}


def run_tool(name, tool_input):
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(tool_input)
    except Exception as exc:  # surfaced back to the model as a tool error, not a crash
        return {"error": str(exc)}
