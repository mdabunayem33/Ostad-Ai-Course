"""The three support tools Claude can call.

- lookup_customer : find a customer by ID or email
- lookup_order    : fetch an order by ID
- create_ticket   : open a support ticket (constrained to domain enums)

Each returns a JSON string so Claude receives structured, parseable results.
"""

from __future__ import annotations

import json
from typing import Any

from app.data import store
from app.domain.models import Team, Urgency
from app.tools.base import Tool, ToolError


def _enum_values(enum_cls: type) -> list[str]:
    return [member.value for member in enum_cls]


class LookupCustomerTool(Tool):
    name = "lookup_customer"
    description = (
        "Look up a customer account by customer_id or email. "
        "Provide at least one of them. Returns the customer's profile."
    )

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID, e.g. CUST-001.",
                },
                "email": {
                    "type": "string",
                    "description": "Customer email address.",
                },
            },
        }

    def run(self, tool_input: dict[str, Any]) -> str:
        customer_id = tool_input.get("customer_id")
        email = tool_input.get("email")
        if not customer_id and not email:
            raise ToolError("Provide a customer_id or an email to look up a customer.")

        customer = store.find_customer(customer_id=customer_id, email=email)
        if customer is None:
            raise ToolError(
                f"No customer found for customer_id={customer_id!r} email={email!r}."
            )
        return json.dumps(customer)

    async def arun(self, tool_input: dict[str, Any]) -> str:
        customer_id = tool_input.get("customer_id")
        email = tool_input.get("email")
        if not customer_id and not email:
            raise ToolError("Provide a customer_id or an email to look up a customer.")

        customer = await store.afind_customer(customer_id=customer_id, email=email)
        if customer is None:
            raise ToolError(
                f"No customer found for customer_id={customer_id!r} email={email!r}."
            )
        return json.dumps(customer)


class LookupOrderTool(Tool):
    name = "lookup_order"
    description = "Look up an order by its order_id. Returns the order details."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order ID, e.g. ORD-1001.",
                },
            },
            "required": ["order_id"],
        }

    def run(self, tool_input: dict[str, Any]) -> str:
        order_id = tool_input.get("order_id")
        if not order_id:
            raise ToolError("order_id is required.")
        order = store.find_order(order_id)
        if order is None:
            raise ToolError(f"No order found for order_id={order_id!r}.")
        return json.dumps(order)

    async def arun(self, tool_input: dict[str, Any]) -> str:
        order_id = tool_input.get("order_id")
        if not order_id:
            raise ToolError("order_id is required.")
        order = await store.afind_order(order_id)
        if order is None:
            raise ToolError(f"No order found for order_id={order_id!r}.")
        return json.dumps(order)


class CreateTicketTool(Tool):
    name = "create_ticket"
    description = (
        "Create a support ticket once you understand the customer's issue. "
        "Set urgency and assigned_team appropriately. Include the customer_id "
        "when known."
    )

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Short summary of the issue.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the customer's problem.",
                },
                "urgency": {
                    "type": "string",
                    "enum": _enum_values(Urgency),
                    "description": "Ticket urgency.",
                },
                "assigned_team": {
                    "type": "string",
                    "enum": _enum_values(Team),
                    "description": "Team that should own the ticket.",
                },
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID, if known.",
                },
            },
            "required": ["subject", "description", "urgency", "assigned_team"],
        }

    def run(self, tool_input: dict[str, Any]) -> str:
        ticket = store.create_ticket(
            subject=tool_input["subject"],
            description=tool_input["description"],
            urgency=tool_input["urgency"],
            assigned_team=tool_input["assigned_team"],
            customer_id=tool_input.get("customer_id"),
        )
        return json.dumps(ticket)
