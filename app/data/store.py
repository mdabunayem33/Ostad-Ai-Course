"""In-memory mock backend for customers, orders, and tickets.

This stands in for real CRM / order / ticketing systems. The tool layer calls
these functions; swapping to a real database or HTTP API later means changing
only this module, not the tools or the agent.
"""

from __future__ import annotations

import asyncio
from itertools import count
from typing import Any

# Simulated per-lookup backend latency (network/DB round-trip). The async
# lookup functions honor this so parallel execution is observably faster than
# sequential execution. Real integrations replace these with actual I/O.
SIMULATED_LATENCY_SECONDS = 0.5

# --- Seed data --------------------------------------------------------------

CUSTOMERS: dict[str, dict[str, Any]] = {
    "CUST-001": {
        "customer_id": "CUST-001",
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "plan": "Enterprise",
    },
    "CUST-002": {
        "customer_id": "CUST-002",
        "name": "Bob Smith",
        "email": "bob@example.com",
        "plan": "Pro",
    },
}

ORDERS: dict[str, dict[str, Any]] = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "customer_id": "CUST-001",
        "item": "Widget Pro annual license",
        "status": "delivered",
        "total_usd": 499.00,
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "customer_id": "CUST-002",
        "item": "Gadget monthly subscription",
        "status": "processing",
        "total_usd": 29.00,
    },
}

# --- Ticket store -----------------------------------------------------------

_TICKETS: dict[str, dict[str, Any]] = {}
_ticket_seq = count(4001)


def find_customer(
    customer_id: str | None = None, email: str | None = None
) -> dict[str, Any] | None:
    """Look up a customer by ID (preferred) or email. Returns None if absent."""
    if customer_id and customer_id in CUSTOMERS:
        return CUSTOMERS[customer_id]
    if email:
        target = email.strip().lower()
        for customer in CUSTOMERS.values():
            if customer["email"].lower() == target:
                return customer
    return None


def find_order(order_id: str) -> dict[str, Any] | None:
    """Look up an order by ID. Returns None if absent."""
    return ORDERS.get(order_id)


async def afind_customer(
    customer_id: str | None = None, email: str | None = None
) -> dict[str, Any] | None:
    """Async customer lookup simulating a backend round-trip."""
    await asyncio.sleep(SIMULATED_LATENCY_SECONDS)
    return find_customer(customer_id=customer_id, email=email)


async def afind_order(order_id: str) -> dict[str, Any] | None:
    """Async order lookup simulating a backend round-trip."""
    await asyncio.sleep(SIMULATED_LATENCY_SECONDS)
    return find_order(order_id)


def create_ticket(
    subject: str,
    urgency: str,
    assigned_team: str,
    description: str,
    customer_id: str | None = None,
) -> dict[str, Any]:
    """Create and persist a ticket, returning the stored record."""
    ticket_id = f"TKT-{next(_ticket_seq)}"
    ticket = {
        "ticket_id": ticket_id,
        "subject": subject,
        "urgency": urgency,
        "assigned_team": assigned_team,
        "description": description,
        "customer_id": customer_id,
        "status": "open",
    }
    _TICKETS[ticket_id] = ticket
    return ticket
