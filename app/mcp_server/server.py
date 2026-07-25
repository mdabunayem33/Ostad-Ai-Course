"""Custom MCP server exposing `check_customer_subscription` over HTTP.

Built with FastMCP and the streamable-HTTP transport, this is a standalone
microservice: it depends only on the data layer and the MCP SDK, not on the
Anthropic client or API key. Any MCP client can connect to it at
`http://<host>:<port>/mcp`.

Run standalone:
    venv/Scripts/python.exe -m app.mcp_server.server
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.data import store

logger = logging.getLogger("customer-subscription-mcp")

SERVER_NAME = "customer-subscription-mcp"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8050


def check_subscription_logic(customer_id: str) -> dict[str, Any]:
    """Core tool logic: return a customer's subscription, or a not-found result.

    Kept separate from the MCP registration so it can be unit-tested directly.
    """
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return {
            "customer_id": customer_id,
            "found": False,
            "message": "customer_id is required.",
        }

    subscription = store.find_subscription(customer_id)
    if subscription is None:
        return {
            "customer_id": customer_id,
            "found": False,
            "message": "No subscription on file for this customer.",
        }

    result = dict(subscription)
    result["found"] = True
    return result


def build_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> FastMCP:
    """Construct the FastMCP server with the subscription tool registered."""
    mcp = FastMCP(SERVER_NAME, host=host, port=port)

    @mcp.tool()
    def check_customer_subscription(customer_id: str) -> dict[str, Any]:
        """Check a customer's subscription status by customer_id (e.g. 'CUST-001').

        Returns the plan, status, seat count, renewal date, and MRR when the
        customer is found; otherwise returns found=false with a message.
        """
        logger.info("check_customer_subscription(customer_id=%s)", customer_id)
        return check_subscription_logic(customer_id)

    return mcp


def main() -> None:
    """Run the server over streamable HTTP (blocking)."""
    logging.basicConfig(level=logging.INFO)
    server = build_server()
    logger.info(
        "Serving %s at http://%s:%d/mcp", SERVER_NAME, DEFAULT_HOST, DEFAULT_PORT
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
