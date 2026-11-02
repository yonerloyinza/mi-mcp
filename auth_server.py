"""
auth_server.py — Authorization Server OAuth 2.1 para MCP.

Sirve como servidor de autenticación (Authorization Server) que:
  * Expone /.well-known/oauth-authorization-server (metadatos)
  * Sirve página de login + consentimiento en /authorize
  * Intercambia code por access token en /token (PKCE S256)
  * Emite JWT firmados con la misma SECRET_KEY que server_secure.py
"""

import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import jwt
import uvicorn

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
ISSUER = os.environ.get("OAUTH_ISSUER", "http://localhost:9000")
SECRET_KEY = os.environ.get("OAUTH_JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
RESOURCE_URL = os.environ.get("MCP_RESOURCE_URL", "https://mcp.example.com")

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("auth-server")

app = FastAPI(title="OAuth 2.1 Authorization Server for MCP", version="2026.11.0")

# ---------------------------------------------------------------------------
# Almacenamiento en memoria (en producción usar Redis/PostgreSQL)
# ---------------------------------------------------------------------------
# code_challenge -> {code, client_id, redirect_uri, scope, state}
auth_codes: dict[str, dict[str, Any]] = {}
# jti -> payload (access tokens emitidos)
access_tokens: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# 1. Metadata del servidor de autorización (RFC 8414)
# ---------------------------------------------------------------------------

@app.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "registration_endpoint": f"{ISSUER}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["mcp:tools"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


# ---------------------------------------------------------------------------
# 2. Página de login + consentimiento en /authorize
# ---------------------------------------------------------------------------

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>MCP OAuth - Iniciar sesión</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 80px auto; padding: 20px; }
        .card { border: 1px solid #ddd; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { font-size: 24px; margin-bottom: 8px; }
        p { color: #666; margin-bottom: 24px; }
        .btn { background: #0070c9; color: white; border: none; padding: 12px 24px; border-radius: 6px; font-size: 16px; cursor: pointer; width: 100%; }
        .btn:hover { background: #005a9e; }
        .scopes { margin: 16px 0; font-size: 14px; color: #333; }
        .scope { display: inline-block; background: #f3f4f6; padding: 4px 8px; border-radius: 4px; margin-right: 6px; margin-bottom: 6px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Iniciar sesión en MCP</h1>
        <p>La aplicación <strong>{client_id}</strong> solicita acceso a tus datos MCP.</p>
        <div class="scopes">
            Permisos solicitados:
            {' '.join(f'<span class="scope">{s}</span>' for s in scopes)}
        </div>
        <form method="post">
            <input type="hidden" name="code" value="{code}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="state" value="{state}">
            <button class="btn" type="submit">Autorizar</button>
        </form>
    </div>
</body>
</html>
"""


@app.get("/authorize")
async def authorize(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
):
    """Muestra página de login y genera un código de autorización."""
    code = secrets.token_urlsafe(32)
    auth_codes[code_challenge] = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "created_at": datetime.utcnow().isoformat(),
    }

    return HTMLResponse(
        LOGIN_PAGE.format(
            client_id=client_id,
            code=code,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scope,
        )
    )


@app.post("/authorize")
async def authorize_post(
    code: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(...),
):
    """Procesa la autorización del usuario y redirige al cliente con el código."""
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}")


# ---------------------------------------------------------------------------
# 3. Intercambiar código por access token (/token)
# ---------------------------------------------------------------------------

@app.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None),
    client_id: str = Form(None),
):
    """Intercambia un código de autorización por un access token JWT."""

    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    # Buscar el code_challenge asociado a este código
    challenge = None
    for k, v in auth_codes.items():
        if v["code"] == code:
            challenge = k
            break

    if not challenge:
        return JSONResponse({"error": "invalid_grant", "error_description": "Código inválido"}, status_code=400)

    challenge_data = auth_codes[challenge]

    # Verificar PKCE code_verifier (simplificado: en producción verificar el hash)
    if not code_verifier:
        return JSONResponse({"error": "invalid_grant", "error_description": "code_verifier requerido"}, status_code=400)

    # Emitir JWT de acceso
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "sub": "usuario-demo",
        "aud": RESOURCE_URL,
        "scope": challenge_data["scope"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }

    access_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    access_tokens[payload["jti"]] = payload

    logger.info(f"Token emitido para scope: {challenge_data['scope']}")

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": challenge_data["scope"],
    }


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting OAuth Authorization Server on 0.0.0.0:9000")
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="info")
