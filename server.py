import logging
import os
import sys

from dotenv import load_dotenv

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
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(name)

port = int(os.environ.get("PORT", 8080))
host = os.environ.get("HOST", "0.0.0.0")

mcp = MCPServer(name, version="1.0.0")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    logger.info(f"Tool called: add({a}, {b})")
    return a + b


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
    logger.info(f"Starting MCP Server on port {port}...")
    try:
        mcp.run(transport="streamable-http", host=host, port=port)
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
