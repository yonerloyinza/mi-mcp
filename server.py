import argparse
import hmac
import logging
import os
import sys

from dotenv import load_dotenv
import uvicorn
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

load_dotenv()

from mcp_types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
)
from mcp.server.mcpserver import MCPServer

name = "demo-mcp-server"
greeting_resource_template = "demo://greeting/{name}"
greeting_names = ["Ana", "Luis", "Maya"]
greeting_styles = ["friendly", "formal", "funny"]

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(name)

transport = os.environ.get("TRANSPORT", "streamable-http").lower()
port = int(os.environ.get("PORT", 8080))
host = os.environ.get("HOST", "127.0.0.1")


class BearerTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected_authorization = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            authorization_headers = [
                value for name, value in scope.get("headers", []) if name.lower() == b"authorization"
            ]
            if len(authorization_headers) != 1 or not hmac.compare_digest(
                authorization_headers[0], self.expected_authorization
            ):
                response = JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


mcp = MCPServer(name, version="1.0.0")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    logger.info(f"Tool called: add({a}, {b})")
    return a + b


def parse_bool(value: str, setting: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{setting} must be true or false.")


@mcp.resource(
    "demo://welcome",
    name="welcome",
    description="A short welcome message from the demo server.",
)
def welcome_resource() -> str:
    return "Welcome to the demo MCP server."


@mcp.resource(
    greeting_resource_template,
    name="greeting",
    description="Create a greeting for the supplied name.",
)
def greeting_resource(name: str) -> str:
    return f"Hello, {name}!"


@mcp.prompt(
    name="draft_greeting",
    description="Create a prompt for writing a greeting in the requested style.",
)
def draft_greeting(name: str, style: str) -> str:
    return f"Write a {style} greeting for {name}."


@mcp.completion()
async def complete_demo_arguments(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    context: CompletionContext | None,
) -> Completion | None:
    if isinstance(ref, PromptReference) and ref.name == "draft_greeting":
        choices = {
            "name": greeting_names,
            "style": greeting_styles,
        }.get(argument.name, [])
    elif isinstance(ref, ResourceTemplateReference) and ref.uri == greeting_resource_template:
        choices = greeting_names if argument.name == "name" else []
    else:
        return None

    partial = argument.value.casefold()
    return Completion(values=[choice for choice in choices if choice.casefold().startswith(partial)])


@mcp.tool()
async def send_demo_log() -> str:
    """Write an informational log message to stderr."""
    logger.info("The demo log capability is working.")
    return "Logged an informational message to stderr."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the demo MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=transport,
        help="MCP transport (defaults to TRANSPORT or streamable-http).",
    )
    try:
        auth_required = parse_bool(os.environ.get("AUTH_REQUIRED", "true"), "AUTH_REQUIRED")
    except ValueError as error:
        parser.error(str(error))
    parser.add_argument(
        "--require-auth",
        action=argparse.BooleanOptionalAction,
        default=auth_required,
        help="Require a Bearer token for HTTP (defaults to AUTH_REQUIRED).",
    )
    args = parser.parse_args()
    transport = args.transport

    logger.info(f"Starting MCP Server with {transport} transport...")
    try:
        if transport == "stdio":
            mcp.run(transport="stdio")
        elif transport == "streamable-http":
            app = mcp.streamable_http_app(host=host)
            if args.require_auth:
                token = os.environ.get("MCP_TOKEN")
                if not token:
                    raise ValueError("MCP_TOKEN must be set when HTTP authentication is enabled.")
                app = BearerTokenMiddleware(app, token)
            else:
                logger.warning("HTTP Bearer authentication is disabled.")

            uvicorn.run(
                app,
                host=host,
                port=port,
                log_level=logging.getLevelName(logging.getLogger().getEffectiveLevel()).lower(),
            )
        else:
            raise ValueError(f"Unsupported transport: {transport}")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
