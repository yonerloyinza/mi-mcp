#!/usr/bin/env bash
set -euo pipefail

set -a
source .env
set +a
: "${MCP_TOKEN:?Define MCP_TOKEN en .env}"

curl -i -X POST http://127.0.0.1:8001/mcp \
  -H "Authorization: Bearer ${MCP_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"prueba-manual","version":"1.0"}}}'