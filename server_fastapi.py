"""
server_fastapi.py — Servidor MCP sobre FastAPI bajo MCP 2026-07-28 (Stateless Core).

Cada petición HTTP POST es autodescriptiva y se rutea por cabeceras Layer-7:
  Mcp-Protocol-Version: 2026-07-28
  Mcp-Method:           tools/call | tools/list | completion/complete | ...
  Mcp-Name:             nombre de la herramienta (obligatorio para tools/call)

Sin handshake de initialize, sin identificadores de sesión fijos.
"""

import base64
import json
import logging
import os
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from mcp.server import MCPServer

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8002))
MCP_TOKEN = os.environ.get("MCP_TOKEN")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "false").lower() in ("1", "true", "yes", "on")

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-fastapi")

app = FastAPI(title="MCP Stateless FastAPI Server", version="2026.11.0")

# ---------------------------------------------------------------------------
# Servidor MCP (Stateless Core)
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="fastapi-mcp-server",
    version="2026.11.0",
    instructions="Servidor MCP sobre FastAPI bajo la especificación 2026-07-28. Stateless.",
    log_level="INFO",
)


# ---------------------------------------------------------------------------
# Estado simulado (stateless — no hay sesión)
# ---------------------------------------------------------------------------
FACTURAS: Dict[str, Dict[str, Any]] = {
    "FAC-2026-001": {"cliente": "Acme Corp", "subtotal": 1000.0, "estado": "pendiente"},
    "FAC-2026-002": {"cliente": "Globex", "subtotal": 2500.0, "estado": "pagada"},
}
ADJUNTOS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helpers de autenticación Bearer
# ---------------------------------------------------------------------------

def _check_auth(authorization: str | None) -> None:
    if not AUTH_REQUIRED:
        return
    if not MCP_TOKEN:
        raise HTTPException(status_code=500, detail="MCP_TOKEN no configurado en el servidor")
    expected = f"Bearer {MCP_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Endpoint único MCP (POST /mcp)
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    mcp_protocol_version: str | None = Header(default=None, alias="Mcp-Protocol-Version"),
    mcp_method: str | None = Header(default=None, alias="Mcp-Method"),
    mcp_name: str | None = Header(default=None, alias="Mcp-Name"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    """Punto de entrada único para todas las peticiones MCP."""

    # 1. Validar versión del protocolo (obligatoria SEP-2243)
    if mcp_protocol_version != "2026-07-28":
        raise HTTPException(
            status_code=400,
            detail="Protocolo MCP no soportado. Se requiere Mcp-Protocol-Version: 2026-07-28",
        )

    # 2. Autenticación Bearer (opcional según AUTH_REQUIRED)
    _check_auth(authorization)

    # 3. Leer cuerpo JSON
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo JSON inválido")

    arguments = body.get("arguments", {}) if isinstance(body, dict) else {}

    # 4. Ruteo por cabecera Mcp-Method
    if mcp_method == "tools/list":
        resultado = await mcp.list_tools()
        return Response(
            content=json.dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    if mcp_method == "tools/call":
        if not mcp_name:
            raise HTTPException(status_code=400, detail="Cabecera Mcp-Name requerida para tools/call")

        resultado = await mcp.call_tool(mcp_name, arguments)
        return Response(
            content=json.dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    if mcp_method == "completion/complete":
        resultado = await mcp.call_completion(
            argument_name=arguments.get("name"),
            current_value=arguments.get("value"),
        )
        return Response(
            content=json.dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "private, max-age=5"},
        )

    raise HTTPException(status_code=404, detail=f"Método MCP no implementado: {mcp_method}")


# ---------------------------------------------------------------------------
# Herramientas (definidas después del servidor para usar decoradores)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="add",
    description="Suma dos números enteros.",
)
def add(a: int, b: int) -> Dict[str, Any]:
    return {"result": a + b}


@mcp.tool(
    name="obtener_factura",
    description="Recupera una factura y devuelve un token de transacción.",
)
async def obtener_factura(id_factura: str) -> Dict[str, Any]:
    if id_factura not in FACTURAS:
        return {"error": f"Factura {id_factura} no encontrada"}
    factura = FACTURAS[id_factura]
    return {
        "id_factura": id_factura,
        "detalles": factura,
        "token_transaccion": str(uuid.uuid4()),
        "instrucciones_mcp": (
            "Pasa este 'token_transaccion' a 'aplicar_descuento' para aplicar cambios."
        ),
    }


@mcp.tool(
    name="aplicar_descuento",
    description="Aplica un descuento validando el token de transacción.",
)
async def aplicar_descuento(
    id_factura: str,
    porcentaje: float,
    token_transaccion: str,
) -> Dict[str, Any]:
    if not token_transaccion:
        return {"error": "Token de transacción ausente"}
    if id_factura not in FACTURAS:
        return {"error": "Factura no encontrada"}
    factura = FACTURAS[id_factura]
    descuento = factura["subtotal"] * (porcentaje / 100)
    return {
        "operacion": "exitosa",
        "id_factura": id_factura,
        "subtotal_original": factura["subtotal"],
        "descuento_aplicado": round(descuento, 2),
        "total_final": round(factura["subtotal"] - descuento, 2),
    }


@mcp.tool(
    name="guardar_evidencia_multimedia",
    description="Guarda una imagen/documento (Base64) asociado a un paciente.",
)
async def guardar_evidencia_multimedia(
    id_paciente: str,
    descripcion: str,
    archivo_base64: str,
    mime_type: str,
) -> Dict[str, Any]:
    try:
        if archivo_base64.startswith("data:"):
            archivo_base64 = archivo_base64.split("base64,", 1)[1]
        datos_binarios = base64.b64decode(archivo_base64)
        adjunto_id = str(uuid.uuid4())
        ADJUNTOS[adjunto_id] = {
            "id_paciente": id_paciente,
            "descripcion": descripcion,
            "bytes": datos_binarios,
            "mime_type": mime_type,
            "size": len(datos_binarios),
        }
        return {
            "operacion": "exitosa",
            "id_adjunto": adjunto_id,
            "id_paciente": id_paciente,
            "descripcion": descripcion,
            "mime_type": mime_type,
            "size_bytes": len(datos_binarios),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Fallo al guardar: {str(exc)}"}


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------

@mcp.resource(uri="demo://welcome", name="welcome", description="Mensaje de bienvenida.")
def welcome_resource() -> str:
    return "Welcome to the MCP FastAPI server (Stateless Core 2026-07-28)."


@mcp.resource(uri="demo://greeting/{name}", name="greeting", description="Saludo para {name}.")
def greeting_resource(name: str) -> str:
    return f"Hello, {name}!"


@mcp.resource(uri="demo://adjunto/{adjunto_id}", name="adjunto", description="Adjunto multimedia.")
def adjunto_resource(adjunto_id: str) -> Dict[str, Any]:
    if adjunto_id not in ADJUNTOS:
        return {"error": f"Adjunto {adjunto_id} no encontrado"}
    adj = ADJUNTOS[adjunto_id]
    return {
        "adjunto_id": adjunto_id,
        "mime_type": adj["mime_type"],
        "size_bytes": adj["size"],
        "data": base64.b64encode(adj["bytes"]).decode("utf-8"),
        "content_type": "blob",
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt(name="draft_greeting", description="Prompt para redactar un saludo.")
def draft_greeting(name: str, style: str) -> str:
    return f"Write a {style} greeting for {name}."


# ---------------------------------------------------------------------------
# Completions (autocompletado)
# ---------------------------------------------------------------------------

@mcp.completion()
async def complete_demo_arguments(
    ref: Any,
    argument: Any,
    context: Any = None,
) -> Dict[str, Any]:
    """Autocompletado para argumentos."""
    choices: list[str] = []
    ref_name = getattr(ref, "name", None) if hasattr(ref, "name") else None
    ref_uri = getattr(ref, "uri", None) if hasattr(ref, "uri") else None
    arg_name = getattr(argument, "name", None) if hasattr(argument, "name") else None
    arg_value = getattr(argument, "value", None) if hasattr(argument, "value") else ""

    if ref_name == "draft_greeting":
        if arg_name == "name":
            choices = ["Ana", "Luis", "Maya"]
        elif arg_name == "style":
            choices = ["friendly", "formal", "funny"]
    elif ref_uri == "demo://greeting/{name}":
        if arg_name == "name":
            choices = ["Ana", "Luis", "Maya"]

    partial = str(arg_value).casefold()
    filtered = [c for c in choices if c.casefold().startswith(partial)]
    return {
        "values": [{"value": c, "label": c} for c in filtered],
        "hasMore": False,
    }


# ---------------------------------------------------------------------------
# Punto de entrada (uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting FastAPI MCP Server on {HOST}:{PORT}...")
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
