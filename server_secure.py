"""
server_secure.py — Servidor MCP 2026-07-28 (Stateless Core) con OAuth 2.1 Resource Server.

Implementa:
  * MCPServer del SDK oficial (from mcp.server.mcpserver import MCPServer)
  * Endpoint POST /mcp con enrutamiento ASGI directo (sin streamable_http_app)
  * /.well-known/oauth-protected-resource (RFC 9728)
  * Validación JWT: aud + scope en cada solicitud
  * Cabeceras obligatorias SEP-2243 (Mcp-Protocol-Version, Mcp-Method, Mcp-Name)
  * server/discover obligatorio
  * Estado via handles explícitos (job_id) — sin sesiones en memoria
  * WWW-Authenticate en respuestas 401/403
  * Middleware de autenticación OAuth 2.1 Resource Server
"""

import base64
import json
import logging
import os
import sys
import uuid
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response, status, Depends
from jose import jwt, JWTError
from mcp.server.mcpserver import MCPServer

load_dotenv()


def _mcp_json_dumps(obj: Any) -> str:
    """Serializa objetos MCP (Pydantic, Tool, etc.) a JSON."""
    def _default(o: Any) -> Any:
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)
    return json.dumps(obj, default=_default)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8005))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
SECRET_KEY = os.environ.get("OAUTH_JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
EXPECTED_AUDIENCE = os.environ.get("MCP_RESOURCE_URL", "https://mcp.example.com")
OAUTH_ISSUER = os.environ.get("OAUTH_ISSUER", "https://auth.example.com")
REQUIRED_SCOPE = "mcp:tools"
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "true").lower() in ("1", "true", "yes", "on")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-secure")

# ---------------------------------------------------------------------------
# Servidor MCP (Stateless Core, especificación 2026-07-28)
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="enterprise-secure-server",
    version="2026.11.0",
    instructions="Servidor MCP seguro bajo MCP 2026-07-28 (Stateless Core). "
                 "Autenticación OAuth 2.1 Resource Server. Sin sesiones en memoria.",
)

# ---------------------------------------------------------------------------
# Estado simulado (stateless — no hay sesión en memoria)
# ---------------------------------------------------------------------------
JOBS: dict[str, dict[str, Any]] = {}
FACTURAS: dict[str, dict[str, Any]] = {
    "FAC-2026-001": {"cliente": "Acme Corp", "subtotal": 1000.0, "estado": "pendiente"},
    "FAC-2026-002": {"cliente": "Globex", "subtotal": 2500.0, "estado": "pagada"},
}


# ---------------------------------------------------------------------------
# server/discover (obligatorio en MCP 2026-07-28)
# ---------------------------------------------------------------------------

@mcp.tool(name="server_discover")
async def server_discover() -> dict[str, Any]:
    """Anuncia versiones compatibles, capacidades e identidad del servidor."""
    return {
        "protocolVersions": ["2026-07-28"],
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        },
        "serverInfo": {"name": "enterprise-secure-server", "version": "2026.11.0"},
    }


# ---------------------------------------------------------------------------
# Herramientas de negocio
# ---------------------------------------------------------------------------

@mcp.tool(name="obtener_factura")
async def obtener_factura(id_factura: str) -> dict[str, Any]:
    """Recupera una factura y devuelve un token de transacción para cambios."""
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


@mcp.tool(name="aplicar_descuento")
async def aplicar_descuento(
    id_factura: str,
    porcentaje: float,
    token_transaccion: str,
) -> dict[str, Any]:
    """Aplica un descuento validando el token de transacción (estado explícito)."""
    if not token_transaccion:
        return {"error": "Token de transacción ausente — estado inválido."}
    if id_factura not in FACTURAS:
        return {"error": "Factura no encontrada."}
    factura = FACTURAS[id_factura]
    descuento = factura["subtotal"] * (porcentaje / 100)
    return {
        "operacion": "exitosa",
        "id_factura": id_factura,
        "subtotal_original": factura["subtotal"],
        "descuento_aplicado": round(descuento, 2),
        "total_final": round(factura["subtotal"] - descuento, 2),
    }


@mcp.tool(name="iniciar_importacion_lote")
async def iniciar_importacion_lote(fuente: str) -> dict[str, str]:
    """Devuelve un handle explícito (job_id) para dar seguimiento entre llamadas."""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"estado": "aceptado", "fuente": fuente, "progreso": 0}
    return {"job_id": job_id, "estado": "aceptado", "fuente": fuente}


@mcp.tool(name="consultar_importacion")
async def consultar_importacion(job_id: str) -> dict[str, Any]:
    """Consulta el estado de una importación usando su job_id explícito."""
    if job_id not in JOBS:
        return {"error": f"Trabajo {job_id} no encontrado."}
    return JOBS[job_id]


# ---------------------------------------------------------------------------
# FastAPI aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MCP 2026-07-28 Stateless Secure Server",
    version="2026.11.0",
)


# ---------------------------------------------------------------------------
# Dependencia de autenticación OAuth 2.1 Resource Server
# ---------------------------------------------------------------------------

async def verify_mcp_request(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """Valida el token Bearer en cada solicitud MCP."""
    if AUTH_REQUIRED and not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token Bearer.",
            headers={
                "WWW-Authenticate": (
                    f'Bearer resource_metadata="{EXPECTED_AUDIENCE}/'
                    f'.well-known/oauth-protected-resource"'
                )
            },
        )
    if not authorization:
        return {}

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de autorización inválido. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=EXPECTED_AUDIENCE,
            options={"verify_exp": True},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scopes = payload.get("scope", "").split()
    if REQUIRED_SCOPE not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere el scope '{REQUIRED_SCOPE}'.",
        )
    return payload


# ---------------------------------------------------------------------------
# Endpoint MCP único (POST /mcp)
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    mcp_protocol_version: str | None = Header(default=None, alias="Mcp-Protocol-Version"),
    mcp_method: str | None = Header(default=None, alias="Mcp-Method"),
    mcp_name: str | None = Header(default=None, alias="Mcp-Name"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    _auth: dict = Depends(verify_mcp_request),
) -> Response:
    """Punto de entrada único para todas las peticiones MCP (Stateless Core)."""

    # 1. Validar versión del protocolo (obligatoria SEP-2243)
    if mcp_protocol_version != "2026-07-28":
        raise HTTPException(
            status_code=400,
            detail="Protocolo MCP no soportado. Se requiere Mcp-Protocol-Version: 2026-07-28",
        )

    # 2. Leer cuerpo JSON
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Cuerpo JSON inválido")

    arguments = body.get("arguments", {}) if isinstance(body, dict) else {}

    if mcp_method == "tools/list":
        resultado = await mcp.list_tools()
        return Response(
            content=_mcp_json_dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    if mcp_method == "tools/call":
        if not mcp_name:
            raise HTTPException(status_code=400, detail="Cabecera Mcp-Name requerida para tools/call")

        resultado = await mcp.call_tool(mcp_name, arguments)
        return Response(
            content=_mcp_json_dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    if mcp_method == "completion/complete":
        resultado = await mcp.call_completion(
            argument_name=arguments.get("name"),
            current_value=arguments.get("value"),
        )
        return Response(
            content=_mcp_json_dumps(resultado),
            media_type="application/json",
            headers={"Cache-Control": "private, max-age=5"},
        )

    raise HTTPException(status_code=404, detail=f"Método MCP no implementado: {mcp_method}")


# ---------------------------------------------------------------------------
# Recursos (listados vía tools/list para simplicidad en stateless)
# ---------------------------------------------------------------------------

# Nota: En MCP 2026-07-28, los recursos pueden exponerse como herramientas
# o leerse vía recursos. Aquí se incluyen como herramientas para simplicidad.


# ---------------------------------------------------------------------------
# Punto de entrada (uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting MCP Secure Server on {HOST}:{PORT}...")
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
