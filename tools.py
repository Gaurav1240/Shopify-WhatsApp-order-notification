"""Tool schemas (Anthropic tool-use format) and dispatcher shared by every agent."""

import appointments
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
        "name": "list_abandoned_checkouts",
        "description": "List checkouts customers started but never completed, with their cart items and a recovery link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_old": {
                    "type": "number",
                    "description": "Only checkouts at least this many hours old. Defaults to 1.",
                }
            },
        },
    },
    {
        "name": "find_abandoned_checkout_by_phone",
        "description": "Find a customer's abandoned checkout(s) by phone number, e.g. to answer 'did I leave something in my cart?'.",
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
    {
        "name": "cancel_order",
        "description": (
            "Cancel a Shopify order. Irreversible — only call this after the "
            "customer has explicitly confirmed, in this conversation, that "
            "they want the order cancelled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The Shopify order ID."},
                "reason": {
                    "type": "string",
                    "enum": ["customer", "fraud", "inventory", "declined", "other"],
                    "description": "Why the order is being cancelled.",
                },
            },
            "required": ["order_id", "reason"],
        },
    },
    {
        "name": "refund_order",
        "description": (
            "Issue a refund against a Shopify order's original payment. "
            "Irreversible — only call this after the customer has explicitly "
            "confirmed, in this conversation, that they want a refund."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The Shopify order ID."},
                "amount": {
                    "type": "string",
                    "description": "Amount to refund. Omit to refund the full order total.",
                },
                "reason": {"type": "string", "description": "Internal note on why the refund was issued."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_returnable_items",
        "description": "List an order's fulfilled line items that are eligible to return, with the IDs request_return needs.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "The Shopify order ID."}},
            "required": ["order_id"],
        },
    },
    {
        "name": "request_return",
        "description": (
            "Request a return for one or more items on an order (from get_returnable_items). "
            "Does not refund money by itself. Irreversible-ish — only call this after the "
            "customer has explicitly confirmed, in this conversation, which item(s) and why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The Shopify order ID."},
                "items": {
                    "type": "array",
                    "description": "Items to return, from get_returnable_items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fulfillment_line_item_id": {"type": "string"},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["fulfillment_line_item_id", "quantity"],
                    },
                },
                "reason": {
                    "type": "string",
                    "description": "Short return reason category, e.g. 'wrong_item', 'defective', 'unwanted'.",
                },
                "note": {"type": "string", "description": "The customer's own explanation, in more detail."},
            },
            "required": ["order_id", "items"],
        },
    },
    {
        "name": "save_customer_feedback",
        "description": (
            "Save a customer's feedback — about their delivery experience, or why they're "
            "returning/exchanging something — onto their Shopify customer record, visible to "
            "store staff in Shopify admin (not just in this WhatsApp conversation)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Customer's phone number, to find their Shopify customer record."},
                "feedback_type": {
                    "type": "string",
                    "enum": ["delivery", "return"],
                    "description": "'delivery' for delivery-experience feedback, 'return' for why they're returning something.",
                },
                "comment": {"type": "string", "description": "The customer's own words."},
                "rating": {"type": "integer", "description": "Optional 1-5 satisfaction rating, if they gave one."},
                "order_id": {"type": "string", "description": "The related order ID, if known."},
            },
            "required": ["phone", "feedback_type", "comment"],
        },
    },
    {
        "name": "list_appointment_slots",
        "description": "List available appointment time slots for booking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_type": {
                    "type": "string",
                    "enum": ["return_pickup", "delivery", "service"],
                    "description": (
                        "'return_pickup' for a courier to collect a return, 'delivery' to schedule "
                        "an order's delivery, 'service' for an in-store visit (fitting, consultation, repair, etc.)."
                    ),
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to search. Defaults to the store's configured window.",
                },
            },
            "required": ["appointment_type"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment slot (from list_appointment_slots) for a customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_type": {"type": "string", "enum": ["return_pickup", "delivery", "service"]},
                "slot_id": {"type": "string", "description": "A slot_id from list_appointment_slots."},
                "phone": {"type": "string", "description": "Customer's phone number."},
                "order_id": {
                    "type": "string",
                    "description": "Required for 'return_pickup' and 'delivery' — the related order.",
                },
                "service_name": {
                    "type": "string",
                    "description": "For 'service' appointments — what it's for, e.g. 'fitting', 'consultation', 'repair'.",
                },
                "notes": {"type": "string", "description": "Any extra detail the customer gave."},
            },
            "required": ["appointment_type", "slot_id", "phone"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel a previously booked appointment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "string",
                    "description": "The appointment's id, from book_appointment or find_appointments_by_phone.",
                }
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "find_appointments_by_phone",
        "description": "List a customer's upcoming booked appointments by phone number.",
        "input_schema": {
            "type": "object",
            "properties": {"phone": {"type": "string", "description": "Phone number, with or without punctuation."}},
            "required": ["phone"],
        },
    },
]

def _save_customer_feedback(tool_input):
    customer_id = shopify_client.find_customer_id_by_phone(tool_input["phone"])
    if not customer_id:
        return {"error": "No Shopify customer record found for this phone number"}

    feedback = {"comment": tool_input["comment"]}
    if tool_input.get("rating") is not None:
        feedback["rating"] = tool_input["rating"]
    if tool_input.get("order_id"):
        feedback["order_id"] = tool_input["order_id"]

    return shopify_client.save_customer_feedback(customer_id, tool_input["feedback_type"], feedback)


_HANDLERS = {
    "get_order": lambda i: shopify_client.get_order(i["order_id"]),
    "get_order_status": lambda i: shopify_client.get_order_status(i["order_id"]),
    "list_recent_orders": lambda i: shopify_client.list_recent_orders(days_back=i.get("days_back", 7)),
    "find_orders_by_phone": lambda i: shopify_client.find_orders_by_phone(i["phone"]),
    "list_abandoned_checkouts": lambda i: shopify_client.list_abandoned_checkouts(hours_old=i.get("hours_old", 1)),
    "find_abandoned_checkout_by_phone": lambda i: shopify_client.find_abandoned_checkout_by_phone(i["phone"]),
    "send_whatsapp_message": lambda i: whatsapp_client.send_whatsapp_message(i["to"], i["body"]),
    "cancel_order": lambda i: shopify_client.cancel_order(i["order_id"], reason=i.get("reason")),
    "refund_order": lambda i: shopify_client.refund_order(
        i["order_id"], amount=i.get("amount"), reason=i.get("reason")
    ),
    "get_returnable_items": lambda i: shopify_client.get_returnable_items(i["order_id"]),
    "request_return": lambda i: shopify_client.request_return(
        i["order_id"], i["items"], reason=i.get("reason"), note=i.get("note")
    ),
    "save_customer_feedback": _save_customer_feedback,
    "list_appointment_slots": lambda i: appointments.list_slots(i["appointment_type"], days_ahead=i.get("days_ahead")),
    "book_appointment": lambda i: appointments.book(
        i["appointment_type"],
        i["slot_id"],
        i["phone"],
        order_id=i.get("order_id"),
        service_name=i.get("service_name"),
        notes=i.get("notes"),
    ),
    "cancel_appointment": lambda i: appointments.cancel(i["appointment_id"]),
    "find_appointments_by_phone": lambda i: appointments.find_by_phone(i["phone"]),
}


def run_tool(name, tool_input):
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(tool_input)
    except Exception as exc:  # surfaced back to the model as a tool error, not a crash
        return {"error": str(exc)}
