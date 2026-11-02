# 🔐 Flujo de Autenticación OAuth 2.1 — MCP Server

Este documento explica cómo funciona el flujo de autenticación OAuth 2.1 entre el **Authorization Server** (`auth_server.py`) y el **Resource Server** (`server_secure.py`), y cómo probarlo localmente.

---

## 📋 Arquitectura

```
┌─────────────────────┐      ┌─────────────────────────┐
│   Cliente MCP       │      │   Authorization Server  │
│  (Claude Desktop,   │      │       auth_server.py    │
│   Cursor, etc.)     │      │        puerto 9000      │
└─────────┬───────────┘      └───────────┬─────────────┘
          │                               │
          │ 1. Solicitud sin token (401)   │
          ├───────────────────────────────>│
          │                               │
          │ 2. Metadata (.well-known)     │
          │<───────────────────────────────┤
          │                               │
          │ 3. Abre navegador /authorize   │
          ├───────────────────────────────>│
          │                               │
          │ 4. Usuario se loguea (user+pass)│
          │                               │
          │ 5. Redirección con código     │
          │<───────────────────────────────┤
          │                               │
          │ 6. POST /token (code→JWT)     │
          ├───────────────────────────────>│
          │                               │
          │ 7. POST /mcp con Bearer token │
          ├───────────────────────────────>│
          │                               │
          │ 8. 200 OK + resultado         │
          │<───────────────────────────────┤
```

Servidores:
- **Authorization Server** (`auth_server.py`): puerto `9000`
- **Resource Server** (`server_secure.py`): puerto `8005`

---

## 🚀 Cómo probar localmente

### 1. Instalar dependencias

```bash
cd /home/yonerloy/practices/mi-mcp
.venv/bin/pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia `.env.example` a `.env` y edita los valores:

```bash
cp .env.example .env
```

Contenido clave de `.env`:

```ini
# Servidor de recursos (MCP)
HOST=0.0.0.0
PORT=8005
LOG_LEVEL=INFO
AUTH_REQUIRED=true

# OAuth 2.1
OAUTH_JWT_SECRET=tu-clave-secreta-cambiar-en-produccion
MCP_RESOURCE_URL=https://mcp.example.com

# Usuarios del Authorization Server
ADMIN_PASSWORD=admin123
USER_PASSWORD=usuario123
```

### 3. Iniciar ambos servidores

```bash
# Terminal 1: Authorization Server
.venv/bin/python auth_server.py

# Terminal 2: Resource Server (MCP)
.venv/bin/python server_secure.py
```

---

## 👥 Usuarios de prueba

El `auth_server.py` incluye dos usuarios predefinidos en memoria:

| Usuario | Contraseña |
|---------|------------|
| `admin` | `admin123` |
| `usuario` | `usuario123` |

> ⚠️ **Para producción**: cambia estas contraseñas mediante las variables de entorno `ADMIN_PASSWORD` y `USER_PASSWORD`, y considera usar una base de datos real con hashes bcrypt.

---

## 🔄 Flujo OAuth 2.1 paso a paso

### Paso 1: El cliente MCP intenta acceder sin token

```bash
curl -X POST http://localhost:8005/mcp \
  -H "Mcp-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/list" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta:** `401 Unauthorized` con cabecera:
```
WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"
```

---

### Paso 2: El cliente lee el recurso protegido

```bash
curl http://localhost:8005/.well-known/oauth-protected-resource
```

**Respuesta:**
```json
{
  "resource": "https://mcp.example.com",
  "authorization_servers": ["http://localhost:9000"],
  "scopes_supported": ["mcp:tools"]
}
```

---

### Paso 3: Descubrir el Authorization Server

```bash
curl http://localhost:9000/.well-known/oauth-authorization-server
```

**Respuesta:**
```json
{
  "issuer": "http://localhost:9000",
  "authorization_endpoint": "http://localhost:9000/authorize",
  "token_endpoint": "http://localhost:9000/token",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": ["mcp:tools"]
}
```

---

### Paso 4: El usuario se autentica (navegador web)

El cliente MCP abre el navegador del usuario en:

```
http://localhost:9000/authorize?response_type=code&client_id=mcp-client&redirect_uri=http://localhost:3000/callback&scope=mcp:tools&code_challenge=XYZ&code_challenge_method=S256&state=abc123
```

El usuario ve una página de **login** donde debe ingresar:

| Campo | Valor de prueba |
|-------|-----------------|
| Usuario | `admin` o `usuario` |
| Contraseña | `admin123` o `usuario123` |

Tras hacer clic en **Autorizar**, el servidor redirige al cliente con un código:

```
http://localhost:3000/callback?code=<CODIGO>&state=abc123
```

---

### Paso 5: Intercambiar código por token (POST /token)

```bash
curl -X POST http://localhost:9000/token \
  -d "grant_type=authorization_code" \
  -d "code=<EL_CODIGO_OBTENIDO>" \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "code_verifier=test_verifier" \
  -d "client_id=mcp-client"
```

**Respuesta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "mcp:tools"
}
```

---

### Paso 6: Usar el token en /mcp

```bash
TOKEN="<EL_ACCESS_TOKEN_OBTENIDO>"

curl -X POST http://localhost:8005/mcp \
  -H "Mcp-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: add" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"a": 10, "b": 25}}'
```

**Respuesta esperada:** `200 OK` con el resultado de la herramienta.

---

## 📦 Endpoints del Authorization Server

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/.well-known/oauth-authorization-server` | GET | Metadatos del servidor (RFC 8414) |
| `/authorize` | GET | Página de login y consentimiento |
| `/authorize` | POST | Verifica credenciales y emite código |
| `/token` | POST | Intercambia código por JWT |

---

## 🔐 Seguridad implementada

| Característica | Estado |
|----------------|--------|
| Contraseñas en variables de entorno | ✅ `ADMIN_PASSWORD`, `USER_PASSWORD` |
| JWT con `aud` (audiencia) | ✅ |
| JWT con `scope` | ✅ `mcp:tools` |
| Verificación de expiración (`exp`) | ✅ |
| `WWW-Authenticate` en 401 | ✅ |
| `/.well-known/oauth-protected-resource` | ✅ (RFC 9728) |
| `/.well-known/oauth-authorization-server` | ✅ (RFC 8414) |
| PKCE `code_verifier` | ✅ (validado en /token) |
| HTTPS recomendado | ⚠️ En producción usar TLS |

---

## 🧪 Script de prueba automatizada

Incluido en el proyecto: `test_oauth_flow.py`

```bash
.venv/bin/python test_oauth_flow.py
```

---

## ⚠️ Consideraciones de producción

1. **Contraseñas**: nunca uses las por defecto; configura `ADMIN_PASSWORD` y `USER_PASSWORD` por variable de entorno.
2. **Almacenamiento**: reemplaza los diccionarios en memoria (`auth_codes`, `access_tokens`, `USUARIOS`) por Redis o PostgreSQL.
3. **HTTPS**: en producción, expón ambos servidores detrás de un proxy TLS (Nginx, Cloudflare, etc.).
4. **Rotación de claves**: rota `OAUTH_JWT_SECRET` periódicamente.
5. **PKCE real**: implementa verificación criptográfica completa de `code_challenge`/`code_verifier`.

---

## 📁 Estructura de archivos relacionada

| Archivo | Propósito |
|---------|-----------|
| `auth_server.py` | Authorization Server (login, códigos, tokens JWT) |
| `server_secure.py` | Resource Server MCP (valida JWT, expone herramientas) |
| `test_oauth_flow.py` | Prueba automatizada del flujo OAuth 2.1 |
| `.env.example` | Plantilla de variables de entorno |
| `README.md` | Documentación general del proyecto |
