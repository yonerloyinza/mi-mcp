#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v npx >/dev/null 2>&1; then
    echo "Error: npx is required. Install Node.js and npm first." >&2
    exit 1
fi

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="$(command -v python3 || true)"
    if [[ -z "$PYTHON" ]]; then
        echo "Error: Python 3 is required; create .venv or install python3." >&2
        exit 1
    fi
fi

if [[ ! -f "$PROJECT_DIR/.mcp-inspector.json" ]]; then
    echo "Error: .mcp-inspector.json was not found in $PROJECT_DIR." >&2
    exit 1
fi

if [[ -d "$PROJECT_DIR/.venv/bin" ]]; then
    export PATH="$PROJECT_DIR/.venv/bin:$PATH"
fi

if [[ -z "${AUTH_REQUIRED+x}" ]]; then
    AUTH_REQUIRED="$("$PYTHON" -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("AUTH_REQUIRED") or "true")')"
fi

case "${AUTH_REQUIRED,,}" in
    1|true|yes|on) AUTH_REQUIRED=true ;;
    0|false|no|off) AUTH_REQUIRED=false ;;
    *)
        echo "Error: AUTH_REQUIRED must be true or false." >&2
        exit 1
        ;;
esac
export AUTH_REQUIRED

if [[ "$AUTH_REQUIRED" == true ]]; then
    if [[ -z "${MCP_TOKEN:-}" ]]; then
        MCP_TOKEN="$("$PYTHON" -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("MCP_TOKEN") or "")')"
        export MCP_TOKEN
    fi

    if [[ -z "${MCP_TOKEN:-}" ]]; then
        echo "Error: set MCP_TOKEN in .env or the environment when AUTH_REQUIRED=true." >&2
        exit 1
    fi
fi

server_endpoint="$("$PYTHON" -c 'import json; from urllib.parse import urlsplit; config = json.load(open(".mcp-inspector.json", encoding="utf-8")); url = urlsplit(config["mcpServers"]["demo-http"]["url"]); print(url.hostname, url.port or (443 if url.scheme == "https" else 80))')"
read -r health_host server_port <<< "$server_endpoint"
if [[ -z "$health_host" || -z "$server_port" ]]; then
    echo "Error: could not determine the HTTP server address from .mcp-inspector.json." >&2
    exit 1
fi

if [[ "$health_host" == "0.0.0.0" || "$health_host" == "::" ]]; then
    health_host="127.0.0.1"
fi

inspector_config="$(mktemp "$PROJECT_DIR/.mcp-inspector.runtime.XXXXXX.json")"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        echo "Stopping HTTP server (PID $server_pid)..."
        kill "$server_pid"
        if wait "$server_pid"; then
            :
        else
            server_status=$?
            if [[ "$server_status" -ne 143 ]]; then
                echo "Warning: HTTP server exited with status $server_status." >&2
            fi
        fi
    fi
    rm -f -- "$inspector_config"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$PYTHON" - "$PROJECT_DIR/.mcp-inspector.json" "$inspector_config" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    config = json.load(config_file)

if os.environ["AUTH_REQUIRED"] == "true":
    config["mcpServers"]["demo-http"]["headers"] = {
        "Authorization": f"Bearer {os.environ['MCP_TOKEN']}"
    }

with open(sys.argv[2], "w", encoding="utf-8") as config_file:
    json.dump(config, config_file, indent=2)
    config_file.write("\n")
PY

PORT="$server_port" "$PYTHON" server.py --transport streamable-http &
server_pid=$!

echo "Waiting for HTTP server at http://$health_host:$server_port ..."
server_ready=false
for _ in {1..40}; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
        if wait "$server_pid"; then
            server_status=0
        else
            server_status=$?
        fi
        echo "Error: HTTP server exited before becoming ready (status $server_status)." >&2
        exit 1
    fi

    http_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --max-time 1 "http://$health_host:$server_port/" || true)"
    if [[ "$http_status" != "000" ]]; then
        server_ready=true
        break
    fi
    sleep 0.25
done

if [[ "$server_ready" != true ]]; then
    echo "Error: HTTP server did not become ready on port $server_port." >&2
    exit 1
fi

echo "HTTP server is ready. Starting MCP Inspector with HTTP and STDIO configured."
npx @modelcontextprotocol/inspector --config "$inspector_config"
