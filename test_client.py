"""
End-to-end MCP smoke test (Updated Specification).
Run the server first, then execute:
    ./.venv/bin/python test_client.py
Set MCP_SERVER_URL to test a server at a different Streamable HTTP endpoint.
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PromptReference, ResourceTemplateReference

load_dotenv()

_host = os.environ.get("MCP_HOST", "127.0.0.1")
_port = os.environ.get("PORT", "8080")
DEFAULT_SERVER_URL = f"http://{_host}:{_port}/mcp"

EXPECTED_CAPABILITIES = {"tools", "resources", "prompts"}

def report_success(feature: str) -> None:
    print(f"PASS: {feature}")

async def run_checks(server_url: str) -> bool:
    async with streamable_http_client(server_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            
            # Validar capabilities básicas expuestas por el servidor
            capabilities = initialized.capabilities.model_dump(exclude_none=True) if initialized.capabilities else {}
            missing_capabilities = EXPECTED_CAPABILITIES - capabilities.keys()
            
            if missing_capabilities:
                print(
                    f"FAIL: Server is missing capabilities: {', '.join(sorted(missing_capabilities))}",
                    file=sys.stderr,
                )
                print(
                    f"Connected to {initialized.server_info.name!r}, version {initialized.server_info.version or '(not set)'}.",
                    file=sys.stderr,
                )
                return False

            assert initialized.server_info.name == "demo-mcp-server"
            assert initialized.server_info.version == "1.0.0"
            report_success(
                f"initialize ({initialized.protocol_version}; {initialized.server_info.name} {initialized.server_info.version})"
            )

            # --- 1. TOOLS ---
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "add" in tool_names, f"Unexpected tools: {sorted(tool_names)}"
            
            add_result = await session.call_tool("add", {"a": 2, "b": 3})
            assert not add_result.is_error, f"add returned an error: {add_result}"
            
            # El contenido en MCP regresa en una lista (.content)
            assert add_result.content[0].text == "5" or "5" in add_result.content[0].text, f"Unexpected tool output: {add_result.content}"
            report_success("tools/list and tools/call (add)")

            # --- 2. RESOURCES ---
            resources = await session.list_resources()
            resource_uris = {str(resource.uri) for resource in resources.resources}
            assert "demo://welcome" in resource_uris, f"Unexpected resources: {sorted(resource_uris)}"
            
            welcome = await session.read_resource("demo://welcome")
            assert welcome.contents[0].text == "Welcome to the demo MCP server."
            
            templates = await session.list_resource_templates()
            template_uris = {template.uri_template for template in templates.resource_templates}
            assert "demo://greeting/{name}" in template_uris, f"Unexpected resource templates: {sorted(template_uris)}"
            
            greeting = await session.read_resource("demo://greeting/Ana")
            assert greeting.contents[0].text == "Hello, Ana!"
            report_success("resources/list, resources/templates/list, and resources/read")

            # --- 3. PROMPTS ---
            prompts = await session.list_prompts()
            prompt_names = {prompt.name for prompt in prompts.prompts}
            assert "draft_greeting" in prompt_names, f"Unexpected prompts: {sorted(prompt_names)}"
            
            prompt = await session.get_prompt("draft_greeting", {"name": "Maya", "style": "formal"})
            assert prompt.messages[0].content.text == "Write a formal greeting for Maya."
            report_success("prompts/list and prompts/get")

            # --- 4. COMPLETIONS ---
            prompt_completion = await session.complete(
                ref=PromptReference(type="ref/prompt", name="draft_greeting"),
                argument={"name": "style", "value": "f"},
            )
            assert prompt_completion.completion.values == ["friendly", "formal", "funny"], f"Unexpected prompt completions: {prompt_completion.completion.values}"
            
            resource_completion = await session.complete(
                ref=ResourceTemplateReference(type="ref/resource", uri="demo://greeting/{name}"),
                argument={"name": "name", "value": "a"},
            )
            assert resource_completion.completion.values == ["Ana"], f"Unexpected resource completions: {resource_completion.completion.values}"
            report_success("completion/complete (prompt and resource template)")

            return True

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run modern end-to-end checks against the demo MCP server.")
    parser.add_argument(
        "--url",
        default=os.environ.get("MCP_SERVER_URL", DEFAULT_SERVER_URL),
        help=f"Streamable HTTP MCP endpoint (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override the port (reconstructs URL from HOST env + this port)",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if args.port is not None:
        host = os.environ.get("HOST", "127.0.0.1")
        args.url = f"http://{host}:{args.port}/mcp"
    print(f"Testing MCP server at {args.url}", flush=True)
    if not asyncio.run(run_checks(args.url)):
        raise SystemExit(1)
    print("All modern MCP feature checks passed.")

if __name__ == "__main__":
    main()
