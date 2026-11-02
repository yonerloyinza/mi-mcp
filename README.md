# Demo MCP Server — MCP 2026-07-28 (Stateless Core)

Servidor MCP (Model Context Protocol) bajo la especificación **2026-07-28** con arquitectura **Stateless Core** (sin estado).

## 📋 Resumen de especificaciones aplicadas

Esta implementación sigue el estándar MCP 2026-07-28 gobernado por la **Agentic AI Foundation** (Linux Foundation), soportado nativamente por AWS, Cloudflare, Google y OpenAI.

| Característica | Estado en este proyecto |
|---|---|
| **Stateless Core** | ✅ Implementado — cero persistencia de sesión en memoria |
| **Streamable HTTP** | ✅ Transporte único (HTTP+SSE removido) |
| **Cabeceras obligatorias SEP-2243** | ✅ `Mcp-Protocol-Version`, `Mcp-Method`, `Mcp-Name` |
| **Estado via tokens** | ✅ `token_transaccion` viaja en argumentos y respuestas |
| **Blobs binarios (Base64)** | ✅ `type: "blob"` con `mimeType` para imágenes/PDFs |
| **Cache-Control** | ✅ `public` para catálogos, `no-store` para datos sensibles |
| **Roots** | ❌ No implementado (deprecado) |
| **Sampling** | ❌ No implementado (deprecado) |
| **Logging (setLevel/message)** | ❌ Removido (deprecado) |

## 🏗️ Arquitectura

```
Cliente MCP (Kilo, VS Code, Inspector, Orquestador IA)
        │
        │ HTTP POST /mcp  (cabeceras Mcp-*)
        │
┌─────► demo://welcome          [recurso estático]
│  ├─► demo://greeting/{name}   [recurso plantilla]
│  ├─► demo://adjunto/{id}      [recurso blob imagen]
│  ├─► add(a, b)                [herramienta]
│  ├─► obtener_factura(id)      [herramienta + token estado]
│  ├─► aplicar_descuento(tok)   [herramienta + valida token]
│  ├─► guardar_evidencia_multimedia(blob) [herramienta + imagen Base64]
│  ├─► draft_greeting()         [prompt]
│  └─► complete()               [autocompletado]
```

**Punto clave:** el servidor **no guarda sesiones en memoria**. Si un balanceador de carga redirige una petición a otro contenedor, el `token_transaccion` viaja de vuelta en cada llamada y valida el estado.

## 📦 Archivos del proyecto

| Archivo | Propósito |
|---|---|
| `server.py` | Servidor MCP principal (Streamable HTTP) con todas las capacidades |
| `server_fastapi.py` | Servidor sobre FastAPI con cabeceras obligatorias SEP-2243 |
| `server_multimedia.py` | Ejemplo dedicado a imágenes y blobs Base64 |
| `server_db.py` | Ejemplo con SQLite (base de datos stateless + tokens) |
| `test_client.py` | Tests end-to-end contra `http://127.0.0.1:8001/mcp` |
| `requirements.txt` | Dependencias |
| `.env.example` | Template de variables de entorno |
| `.vscode/mcp.json` | Configuración MCP para VS Code |
| `.kilo/kilo.jsonc` | Configuración MCP para Kilo CLI |
| `LICENSE` | MIT |

## ⚙️ Instalación

```bash
# Clonar
git clone https://github.com/yonerloyinza/mi-mcp.git
cd mi-mcp

# Entorno virtual
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# Dependencias
pip install -r requirements.txt

# Configurar entorno
cp .env.example .env
# Editar .env (ajustar PORT, HOST, LOG_LEVEL, AUTH_REQUIRED, MCP_TOKEN)
```

## 🌐 Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `HOST` | `127.0.0.1` | Dirección de escucha (bind) del servidor |
| `PORT` | `8001` | Puerto HTTP del servidor MCP |
| `LOG_LEVEL` | `INFO` | Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `AUTH_REQUIRED` | `false` | Activa/desactiva autenticación Bearer en HTTP |
| `MCP_TOKEN` | *(requerido si AUTH_REQUIRED=true)* | Token Bearer para proteger solicitudes HTTP |
| `DB_PATH` | `./mcp_demo.db` | Ruta al archivo SQLite (server_db.py) |

> **Nota:** `AUTH_REQUIRED=true` obliga a enviar `Authorization: Bearer <MCP_TOKEN>` en cada petición HTTP. No se aplica a STDIO.

## 🚀 Uso rápido

### Servidor principal (server.py)

```bash
# Terminal 1 — iniciar servidor
.venv/bin/python server.py

# Terminal 2 — ejecutar tests
.venv/bin/python test_client.py
```

### Servidor FastAPI (server_fastapi.py)

```bash
.venv/bin/python server_fastapi.py
# Endpoint: POST http://127.0.0.1:8002/mcp
# Cabeceras obligatorias:
#   Mcp-Protocol-Version: 2026-07-28
#   Mcp-Method: tools/call
#   Mcp-Name: add
#   Authorization: Bearer <MCP_TOKEN>  (si AUTH_REQUIRED=true)
```

### Servidor multimedia (server_multimedia.py)

```bash
.venv/bin/python server_multimedia.py
# Puerto 8003 — manejo de imágenes y documentos como blobs Base64
```

### Servidor de base de datos (server_db.py)

```bash
.venv/bin/python server_db.py
# Puerto 8004 — SQLite con facturas y adjuntos BLOB
```

## 🛠️ Ejemplos de uso

### 1. Suma de dos números (herramienta)

```http
POST /mcp HTTP/1.1
Mcp-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: add
Content-Type: application/json

{"arguments": {"a": 15, "b": 27}}
```

Respuesta: `{"result": 42}`

### 2. Flujo de factura con token (estado sin sesión)

```http
# Paso 1: obtener factura + token
POST /mcp ... Mcp-Name: obtener_factura
{"arguments": {"id_factura": "FAC-2026-001"}}

# Respuesta incluye: "token_transaccion": "abc123..."

# Paso 2: aplicar descuento con el token
POST /mcp ... Mcp-Name: aplicar_descuento
{"arguments": {"id_factura": "FAC-2026-001", "porcentaje": 15, "token_transaccion": "abc123..."}}
```

### 3. Subir imagen (Base64 blob)

```http
POST /mcp ... Mcp-Name: guardar_evidencia_multimedia
{"arguments": {
  "id_paciente": "PAC-9948",
  "descripcion": "Radiografía de tórax",
  "mime_type": "image/png",
  "archivo_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}}
```

### 4. Autocompletado (completion/complete)

```http
POST /mcp ... Mcp-Method: completion/complete
{"ref": {"type": "ref/prompt", "name": "draft_greeting"}, "argument": {"name": "style", "value": "f"}}
```

Respuesta: `{"values": [{"value": "friendly", "label": "friendly"}, ...], "hasMore": false}`

## 🧪 Testing

```bash
.venv/bin/python test_client.py
```

Valida: inicialización, tools, resources, prompts, completions.

> **Nota:** Los tests no incluyen validación de capacidades deprecadas (Roots, Sampling, Logging/setLevel).

## 📚 Características MCP obsoletas (no implementadas)

| Característica | Estado | Por qué |
|---|---|---|
| HTTP + SSE | Deprecado | Reemplazado por **Streamable HTTP** (más directo, seguro, escalable) |
| Roots (`roots/list`, `notifications/roots/list_changed`) | Deprecado | Complejidad innecesaria, sin control de acceso estricto |
| Sampling (`sampling/createMessage`) | Deprecado | Mezcla inferencia del modelo dentro del protocolo |
| Logging (`logging/setLevel`, `notifications/message`) | Deprecado | El logging debe gestionarse con sistemas de observabilidad estándar (OpenTelemetry, stdout/stderr) |

Este servidor usa exclusivamente **Streamable HTTP** como transporte y **no implementa** Roots, Sampling ni Logging a nivel de protocolo.

## 🔌 Integración con clientes MCP

### VS Code

El archivo `.vscode/mcp.json` registra el servidor. Si usas la extensión Kilo Code, configura la cabecera `Authorization: Bearer <MCP_TOKEN>` solo cuando la autenticación esté habilitada.

### Kilo CLI

El archivo `.kilo/kilo.jsonc` configura el MCP. En la TUI, usa `/mcps` para activar/desactivar.

### MCP Inspector

```bash
# Modo CLI (directo)
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8001/mcp --method tools/list

# Modo interactivo (navegador)
npx @modelcontextprotocol/inspector
# Luego conectar a: http://127.0.0.1:8001/mcp
```

## 🔐 Seguridad

- **Autenticación Bearer:** `AUTH_REQUIRED=true` + `MCP_TOKEN` en `.env`.
- **Cache-Control:** `no-store` en respuestas de herramientas (datos sensibles no cachean en proxies).
- **Cache-Control:** `public, max-age=300` en catálogos de herramientas (permitido cachear).
- **Cache-Control:** `private` en datos de pacientes/adjuntos (no cachear en CDNs públicos).
- **HTTPS:** Si expones el servidor a otra máquina, usa HTTPS/TLS delante (proxy inverso).

## 📄 Licencia

MIT — ver archivo `LICENSE`.
