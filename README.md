# Demo MCP Server

A Python MCP (Model Context Protocol) server that demonstrates core capabilities: tools, resources, prompts, and completions.

## Características

| Capability | Detalle |
|---|---|
| **Tools** | `add(a, b)`, `send_demo_log` |
| **Resources** | `demo://welcome`, `demo://greeting/{name}` (parametrizado) |
| **Prompts** | `draft_greeting(name, style)` |
| **Completions** | Autocompletado para nombres y estilos de saludo |

## Arquitectura

El servidor usa el transporte **Streamable HTTP** (`mcp.run(transport="streamable-http")`), lo que permite conexiones concurrentes sin el overhead de STDIO.

```
Cliente MCP (Kilo, VS Code, Inspector)
        │
        │ HTTP/SSE
        │
├─► demo://welcome          [resource estático]
├─► demo://greeting/{name}  [resource template]
├─► add(a, b)               [tool]
├─► send_demo_log()         [tool + logging]
├─► draft_greeting()        [prompt]
├─► complete()              [completions]
```

## Instalación

### Prerequisitos

- Python 3.10+
- pip

### Setup

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/mi-mcp.git
cd mi-mcp

# Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar el puerto (opcional)
cp .env.example .env
# Editar .env si necesitas un puerto diferente
```

### Configuración

| Archivo | Propósito |
|---|---|
| `.env` | Variables: `HOST`, `PORT`, `LOG_LEVEL` |
| `.vscode/mcp.json` | Configuración MCP para VS Code |
| `.kilo/kilo.jsonc` | Configuración MCP para Kilo CLI |

| Variable | Default | Uso |
|---|---|---|
| `PORT` | `8080` | Puerto del servidor HTTP |
| `HOST` | `0.0.0.0` | Dirección de escucha (server bind) |
| `LOG_LEVEL` | `INFO` | Nivel de logging (debug, info, warning, error, critical) |

## Uso Rápido

```bash
# 1. Iniciar el servidor
.venv/bin/python server.py

# 2. En otra terminal, ejecutar tests
.venv/bin/python test_client.py
```

## Ejemplos de Uso

### Tools

```
User: ¿Cuál es la suma de 15 y 27?
MCP: add(a=15, b=27) → 42
```

```
User: Envíame un log al cliente
MCP: send_demo_log() → "Sent an informational log message to the client."
```

### Resources

| URI | Descripción |
|---|---|
| `demo://welcome` | Mensaje de bienvenida estático |
| `demo://greeting/{name}` | Saludo personalizado para `{name}` |

```
User: Lee el recurso demo://greeting/Ana
MCP: "Hello, Ana!"
```

### Prompts

| Prompt | Argumentos |
|---|---|
| `draft_greeting` | `name`, `style` (friendly, formal, funny) |

```
User: Crea un prompt de saludo formal para Maya
MCP: "Write a formal greeting for Maya."
```

### Completions

Autocompletado para argumentos de prompts y recursos:

- **`draft_greeting`**: `name` (Ana, Luis, Maya), `style` (friendly, formal, funny)
- **`demo://greeting/{name}`**: `name` (Ana, Luis, Maya)

### Logging

El servidor usa logging estándar de Python. El nivel se configura vía `LOG_LEVEL` en `.env`:

```bash
# .env
LOG_LEVEL=debug    # debug, info, warning, error, critical
```

El capability deprecado `logging/setLevel` (que permitía cambiar el nivel en caliente desde el cliente) fue **removido** en versión 2.0+ por deprecación de MCP (SEP-2577).

## Testing

```bash
# Tests end-to-end (requiere el servidor corriendo)
.venv/bin/python test_client.py
```

Verifica:
- ✅ Inicialización del protocolo (2025-11-25)
- ✅ Tools (list + call)
- ✅ Resources (list, templates, read)
- ✅ Prompts (list + get)
- ✅ Completions (prompt + resource template)

## Integración con Clientes MCP

### VS Code

El archivo `.vscode/mcp.json` registra el servidor. Si usas la extensión Kilo Code, abre VS Code en este directorio y el MCP aparecerá en la lista de servidores.

### Kilo CLI

El archivo `.kilo/kilo.jsonc` configura el MCP. En la TUI, usa `/mcps` para activar/desactivar.

### MCP Inspector

> ⚠️ El Inspector MCP (`npx @modelcontextprotocol/inspector`) puede solicitar autenticación vía naveador. Si falla, usa la URL directa:

```bash
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8001/mcp --method tools/list
```

Para modo interactivo (navegador):
```bash
npx @modelcontextprotocol/inspector
# Luego conectar a: http://127.0.0.1:8001/mcp
```

## Estructura del Proyecto

```
mi-mcp/
├── server.py              # Servidor MCP principal
├── test_client.py         # Tests end-to-end
├── requirements.txt       # Dependencias
├── .env.example           # Template de variables de entorno
├── .env                   # Configuración local (no versionada)
├── README.md              # Este archivo
├── LICENSE                # MIT
├── .vscode/
│   └── mcp.json           # Configuración MCP para VS Code
└── .kilo/
    └── kilo.jsonc         # Configuración MCP para Kilo CLI
```

## Protocolos y Versiones

| Componente | Versión |
|---|---|
| MCP SDK | mcp==2.3.0 |
| Protocol Version | 2025-11-25 |
| Transporte | Streamable HTTP |
| Python | 3.10+ |
