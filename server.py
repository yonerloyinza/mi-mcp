"""
demo-mcp-server — Servidor MCP bajo la especificación 2026-07-28 (Stateless Core).

Arquitectura:
- CERO persistencia de sesión en memoria (enforce_stateless).
- Cada petición HTTP POST es autodescriptiva (cabeceras Mcp-Protocol-Version, Mcp-Method, Mcp-Name).
- El estado entre llamadas viaja explícitamente en argumentos y respuestas (tokens transaccionales).
- Contenido binario (imágenes, PDFs) viaja como blobs Base64 con mimeType.
- Declaración estática de capacidades (server/discover).
"""

import argparse
import base64
import logging
import os
import sys
import uuid
from typing import Any, Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel

from mcp.server import MCPServer
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
    TextContent,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8001))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
MCP_TOKEN = os.environ.get("MCP_TOKEN")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "false").lower() in ("1", "true", "yes", "on")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("demo-mcp-server")

# ---------------------------------------------------------------------------
# Base de datos simulada (stateless — no hay sesión en memoria)
# ---------------------------------------------------------------------------
FACTURAS: Dict[str, Dict[str, Any]] = {
    "FAC-2026-001": {
        "cliente": "Acme Corp",
        "subtotal": 1000.0,
        "estado": "pendiente",
        "moneda": "USD",
    },
    "FAC-2026-002": {
        "cliente": "Globex",
        "subtotal": 2500.0,
        "estado": "pagada",
        "moneda": "EUR",
    },
}

ADJUNTOS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Inicialización del servidor MCP (Stateless Core)
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="demo-mcp-server",
    version="2026.11.0",
    instructions="Servidor demo MCP bajo la especificación 2026-07-28 (Stateless Core). "
                 "No guarda sesiones en memoria. El estado viaja explícitamente en tokens.",
    log_level=LOG_LEVEL,
)

# ---------------------------------------------------------------------------
# HERRAMIENTAS (Tools)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="add",
    description="Suma dos números enteros.",
)
def add(a: int, b: int) -> Dict[str, Any]:
    """Suma dos números."""
    return {"result": a + b}


@mcp.tool(
    name="obtener_factura",
    description="Recupera una factura y devuelve un 'token_transaccion' obligatorio para aplicar cambios.",
)
async def obtener_factura(id_factura: str) -> Dict[str, Any]:
    """Retrieve an invoice and return a transaction token for stateful follow-up."""
    if id_factura not in FACTURAS:
        return {"error": f"Factura {id_factura} no encontrada"}

    factura = FACTURAS[id_factura]
    token_transaccion = str(uuid.uuid4())

    # PRINCIPIO STATELESS 2026: el token encapsula el estado para la siguiente petición
    return {
        "id_factura": id_factura,
        "detalles": factura,
        "token_transaccion": token_transaccion,
        "instrucciones_mcp": (
            "Para aplicar un descuento, pasa este 'token_transaccion' exacto a "
            "la herramienta 'aplicar_descuento'."
        ),
    }


@mcp.tool(
    name="aplicar_descuento",
    description="Aplica un porcentaje de descuento validando el token de transacción.",
)
async def aplicar_descuento(
    id_factura: str,
    porcentaje: float,
    token_transaccion: str,
) -> Dict[str, Any]:
    """Apply a discount validating the transaction token (stateless state)."""
    if not token_transaccion:
        return {"error": "Token de transacción ausente — estado inválido."}

    if id_factura not in FACTURAS:
        return {"error": "Factura no encontrada."}

    factura = FACTURAS[id_factura]
    descuento = factura["subtotal"] * (porcentaje / 100)
    nuevo_total = factura["subtotal"] - descuento

    return {
        "operacion": "exitosa",
        "id_factura": id_factura,
        "subtotal_original": factura["subtotal"],
        "descuento_aplicado": round(descuento, 2),
        "total_final": round(nuevo_total, 2),
        "moneda": factura["moneda"],
    }


@mcp.tool(
    name="guardar_evidencia_multimedia",
    description="Guarda una imagen/documento (Base64) asociado a un paciente o caso.",
)
async def guardar_evidencia_multimedia(
    id_paciente: str,
    descripcion: str,
    archivo_base64: str,
    mime_type: str,
) -> Dict[str, Any]:
    """Store multimedia evidence (Base64 blob) associated with a patient/case."""
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
        return {"error": f"Fallo al guardar la imagen: {str(exc)}"}


@mcp.tool(
    name="enviar_log_demo",
    description="Escribe un mensaje de log al servidor (stdout/stderr). No notifica al cliente.",
)
async def enviar_log_demo(mensaje: str) -> str:
    """Write an informational log message to the server log."""
    logger.info(f"[send_demo_log] {mensaje}")
    return f"Logged: {mensaje}"


# ---------------------------------------------------------------------------
# RECURSOS (Resources)
# ---------------------------------------------------------------------------

@mcp.resource(
    uri="demo://welcome",
    name="welcome",
    description="Mensaje de bienvenida estático.",
)
def welcome_resource() -> str:
    return "Welcome to the demo MCP server (Stateless Core 2026-07-28)."


@mcp.resource(
    uri="demo://greeting/{name}",
    name="greeting",
    description="Saludo personalizado para {name}.",
)
def greeting_resource(name: str) -> str:
    return f"Hello, {name}!"


@mcp.resource(
    uri="demo://adjunto/{adjunto_id}",
    name="adjunto",
    description="Recupera un adjunto multimedia almacenado (imagen o PDF).",
)
def adjunto_resource(adjunto_id: str) -> Dict[str, Any]:
    """Retrieve a multimedia attachment as a blob with mimeType."""
    if adjunto_id not in ADJUNTOS:
        return {"error": f"Adjunto {adjunto_id} no encontrado"}

    adjunto = ADJUNTOS[adjunto_id]
    base64_data = base64.b64encode(adjunto["bytes"]).decode("utf-8")

    return {
        "adjunto_id": adjunto_id,
        "id_paciente": adjunto["id_paciente"],
        "descripcion": adjunto["descripcion"],
        "mime_type": adjunto["mime_type"],
        "size_bytes": adjunto["size"],
        "data": base64_data,
        "content_type": "blob",
    }


# ---------------------------------------------------------------------------
# PROMPTS (Prompts)
# ---------------------------------------------------------------------------

@mcp.prompt(
    name="draft_greeting",
    description="Crea un prompt para escribir un saludo en el estilo solicitado.",
)
def draft_greeting(name: str, style: str) -> str:
    return f"Write a {style} greeting for {name}."


# ---------------------------------------------------------------------------
# COMPLETIONS (Autocompletado)
# ---------------------------------------------------------------------------

@mcp.completion()
async def complete_demo_arguments(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    context: CompletionContext | None,
) -> Completion | None:
    """Autocompletado para argumentos de prompts y plantillas de recurso."""
    choices: List[str] = []

    if isinstance(ref, PromptReference) and ref.name == "draft_greeting":
        if argument.name == "name":
            choices = ["Ana", "Luis", "Maya"]
        elif argument.name == "style":
            choices = ["friendly", "formal", "funny"]
    elif isinstance(ref, ResourceTemplateReference) and ref.uri == "demo://greeting/{name}":
        if argument.name == "name":
            choices = ["Ana", "Luis", "Maya"]

    partial = argument.value.casefold()
    filtered = [c for c in choices if c.casefold().startswith(partial)]

    return Completion(
        values=[{"value": c, "label": c} for c in filtered],
        hasMore=False,
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(f"Starting MCP Server (Stateless Core) on {HOST}:{PORT}...")
    try:
        mcp.run(transport="streamable-http", host=HOST, port=PORT)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Server error: {exc}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
