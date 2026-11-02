"""
server_multimedia.py — Servidor MCP con manejo de imágenes y archivos (blobs Base64).

Demuestra:
- Contenido binario (imágenes, PDF) viaja como blob con mimeType en Base64.
- Archivos grandes (>5MB) se recomienda servir vía URI de descarga temporal.
- Cache-Control: no-store para datos sensibles (no cachear en proxies/CDN).
"""

import base64
import logging
import os
import sys
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from mcp.server import MCPServer

load_dotenv()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8003))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-multimedia")

mcp = MCPServer(
    name="mcp-multimedia-server",
    version="2026.11.0",
    instructions="Servidor de contenido multimedia bajo MCP 2026-07-28. "
                 "Imágenes y documentos se almacenan como blobs Base64 con mimeType.",
    log_level=LOG_LEVEL,
)

# Almacén de adjuntos en memoria (stateless — reinicia al reiniciar el servidor)
ADJUNTOS: Dict[str, Dict[str, Any]] = {}

MAX_BLOB_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB — recomendación: usar URI externa para archivos mayores


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------

@mcp.tool(
    name="subir_imagen",
    description="Sube una imagen/documento (Base64) y devuelve un ID de adjunto.",
)
async def subir_imagen(
    id_paciente: str,
    descripcion: str,
    archivo_base64: str,
    mime_type: str,
) -> Dict[str, Any]:
    """Store a multimedia file (image/PDF) as a Base64 blob."""
    try:
        if archivo_base64.startswith("data:"):
            archivo_base64 = archivo_base64.split("base64,", 1)[1]

        datos_binarios = base64.b64decode(archivo_base64)

        if len(datos_binarios) > MAX_BLOB_SIZE_BYTES:
            return {
                "error": (
                    f"El archivo supera los 5 MB ({len(datos_binarios)} bytes). "
                    "Para archivos grandes usa un URI de descarga externa."
                )
            }

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
            "cache_policy": {"cacheScope": "private", "ttlMs": 60000},
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Fallo al subir la imagen: {str(exc)}"}


@mcp.tool(
    name="obtener_imagen",
    description="Recupera una imagen/documento almacenado como blob Base64.",
)
async def obtener_imagen(adjunto_id: str) -> Dict[str, Any]:
    """Retrieve a stored multimedia attachment as a Base64 blob."""
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
        "_meta": {
            "cachePolicy": {
                "cacheScope": "private",
                "ttlMs": 60000,
            }
        },
    }


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------

@mcp.resource(uri="demo://adjunto/{adjunto_id}", name="adjunto", description="Adjunto multimedia.")
def adjunto_resource(adjunto_id: str) -> Dict[str, Any]:
    """Retrieve a multimedia attachment as a resource blob."""
    return {
        "adjunto_id": adjunto_id,
        "data": base64.b64encode(ADJUNTOS[adjunto_id]["bytes"]).decode("utf-8"),
        "mime_type": ADJUNTOS[adjunto_id]["mime_type"],
        "content_type": "blob",
    } if adjunto_id in ADJUNTOS else {"error": f"Adjunto {adjunto_id} no encontrado"}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(f"Starting MCP Multimedia Server on {HOST}:{PORT}...")
    try:
        mcp.run(transport="streamable-http", host=HOST, port=PORT)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Server error: {exc}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
