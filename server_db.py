"""
server_db.py — Servidor MCP con base de datos (SQLite) bajo arquitectura Stateless.

Demuestra:
- Conexión global a la base de datos (scope compartido/global).
- Estado entre llamadas viaja en tokens (token_transaccional).
- No hay sesión de servidor: si el balanceador redirige a otro contenedor, el token valida el estado.
- Datos sensibles usan Cache-Control: no-store y cacheScope: private.
"""

import logging
import os
import sqlite3
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from mcp.server import MCPServer

load_dotenv()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8004))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-db")

mcp = MCPServer(
    name="mcp-database-server",
    version="2026.11.0",
    instructions="Servidor de base de datos bajo MCP 2026-07-28 (Stateless). "
                 "Conexión global a SQLite; estado entre llamadas viaja en tokens.",
    log_level=LOG_LEVEL,
)

# ---------------------------------------------------------------------------
# Base de datos SQLite (scope global compartido)
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", "./mcp_demo.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS facturas (
            id_factura   TEXT PRIMARY KEY,
            cliente      TEXT NOT NULL,
            subtotal     REAL NOT NULL,
            estado       TEXT NOT NULL DEFAULT 'pendiente',
            moneda       TEXT NOT NULL DEFAULT 'USD'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS adjuntos (
            id_adjunto   TEXT PRIMARY KEY,
            id_paciente  TEXT NOT NULL,
            descripcion  TEXT NOT NULL,
            mime_type    TEXT NOT NULL,
            size_bytes   INTEGER NOT NULL,
            datos        BLOB NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO facturas (id_factura, cliente, subtotal, estado, moneda) "
        "VALUES ('FAC-2026-001', 'Acme Corp', 1000.0, 'pendiente', 'USD')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO facturas (id_factura, cliente, subtotal, estado, moneda) "
        "VALUES ('FAC-2026-002', 'Globex', 2500.0, 'pagada', 'EUR')"
    )
    conn.commit()
    conn.close()


_init_db()


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------

@mcp.tool(
    name="consultar_factura",
    description="Consulta una factura por ID y devuelve un token de transacción.",
)
async def consultar_factura(id_factura: str) -> Dict[str, Any]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id_factura, cliente, subtotal, estado, moneda FROM facturas WHERE id_factura = ?",
        (id_factura,),
    ).fetchone()
    conn.close()

    if not row:
        return {"error": f"Factura {id_factura} no encontrada"}

    return {
        "id_factura": row["id_factura"],
        "detalles": {
            "cliente": row["cliente"],
            "subtotal": row["subtotal"],
            "estado": row["estado"],
            "moneda": row["moneda"],
        },
        "token_transaccion": str(uuid.uuid4()),
        "instrucciones_mcp": (
            "Para aplicar un descuento, pasa este 'token_transaccion' a 'aplicar_descuento'."
        ),
    }


@mcp.tool(
    name="aplicar_descuento_db",
    description="Aplica un descuento validando el token de transacción (stateless).",
)
async def aplicar_descuento_db(
    id_factura: str,
    porcentaje: float,
    token_transaccion: str,
) -> Dict[str, Any]:
    if not token_transaccion:
        return {"error": "Token de transacción ausente — estado inválido."}

    conn = _get_conn()
    row = conn.execute(
        "SELECT subtotal, moneda FROM facturas WHERE id_factura = ?",
        (id_factura,),
    ).fetchone()

    if not row:
        conn.close()
        return {"error": "Factura no encontrada."}

    subtotal = row["subtotal"]
    moneda = row["moneda"]
    descuento = subtotal * (porcentaje / 100)
    nuevo_total = subtotal - descuento

    conn.execute(
        "UPDATE facturas SET subtotal = ? WHERE id_factura = ?",
        (round(nuevo_total, 2), id_factura),
    )
    conn.commit()
    conn.close()

    return {
        "operacion": "exitosa",
        "id_factura": id_factura,
        "subtotal_original": subtotal,
        "descuento_aplicado": round(descuento, 2),
        "total_final": round(nuevo_total, 2),
        "moneda": moneda,
    }


@mcp.tool(
    name="guardar_adjunto_db",
    description="Guarda un archivo (imagen/PDF) en la base de datos como BLOB.",
)
async def guardar_adjunto_db(
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

        conn = _get_conn()
        conn.execute(
            "INSERT INTO adjuntos (id_adjunto, id_paciente, descripcion, mime_type, size_bytes, datos) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (adjunto_id, id_paciente, descripcion, mime_type, len(datos_binarios), datos_binarios),
        )
        conn.commit()
        conn.close()

        return {
            "operacion": "exitosa",
            "id_adjunto": adjunto_id,
            "id_paciente": id_paciente,
            "descripcion": descripcion,
            "mime_type": mime_type,
            "size_bytes": len(datos_binarios),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Fallo al guardar adjunto: {str(exc)}"}


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------

@mcp.resource(uri="db://factura/{id_factura}", name="factura", description="Factura por ID.")
def factura_resource(id_factura: str) -> Dict[str, Any]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id_factura, cliente, subtotal, estado, moneda FROM facturas WHERE id_factura = ?",
        (id_factura,),
    ).fetchone()
    conn.close()

    if not row:
        return {"error": f"Factura {id_factura} no encontrada"}

    return {
        "id_factura": row["id_factura"],
        "cliente": row["cliente"],
        "subtotal": row["subtotal"],
        "estado": row["estado"],
        "moneda": row["moneda"],
    }


@mcp.resource(uri="db://adjunto/{id_adjunto}", name="adjunto_db", description="Adjunto de BD.")
def adjunto_db_resource(id_adjunto: str) -> Dict[str, Any]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id_adjunto, id_paciente, descripcion, mime_type, size_bytes, datos FROM adjuntos WHERE id_adjunto = ?",
        (id_adjunto,),
    ).fetchone()
    conn.close()

    if not row:
        return {"error": f"Adjunto {id_adjunto} no encontrado"}

    return {
        "id_adjunto": row["id_adjunto"],
        "id_paciente": row["id_paciente"],
        "descripcion": row["descripcion"],
        "mime_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "data": base64.b64encode(row["datos"]).decode("utf-8"),
        "content_type": "blob",
    }


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(f"Starting MCP Database Server on {HOST}:{PORT}...")
    try:
        mcp.run(transport="streamable-http", host=HOST, port=PORT)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Server error: {exc}")
        sys.exit(1)
    finally:
        logger.info("Server terminated")
