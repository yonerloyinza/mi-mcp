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

El servidor admite **Streamable HTTP** y **STDIO**. HTTP es el transporte predeterminado; puedes elegirlo por instancia con `--transport` o mediante la variable `TRANSPORT`. Así puedes tener ambos transportes activos a la vez: inicia HTTP como servidor persistente y deja que el Inspector inicie su propio proceso STDIO. Los logs se escriben en `stderr`, dejando `stdout` disponible para los mensajes del protocolo STDIO.

```
Cliente MCP (Kilo, VS Code, Inspector)
        │
        │ Streamable HTTP o STDIO
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
| `.env` | Valores predeterminados: `TRANSPORT`, `HOST`, `PORT`, `LOG_LEVEL` |
| `.mcp-inspector.json` | Configura HTTP y STDIO para MCP Inspector |
| `.vscode/mcp.json` | Configuración MCP para VS Code |
| `.kilo/kilo.jsonc` | Configuración MCP para Kilo CLI |

| Variable | Default | Uso |
|---|---|---|
| `TRANSPORT` | `streamable-http` | Transporte MCP: `streamable-http` o `stdio` |
| `PORT` | `8080` | Puerto del servidor HTTP |
| `HOST` | `0.0.0.0` | Dirección de escucha (server bind) |
| `LOG_LEVEL` | `INFO` | Nivel de logging (debug, info, warning, error, critical) |

## Uso Rápido

### Streamable HTTP

```bash
# Iniciar el servidor HTTP (deja este proceso en ejecución)
.venv/bin/python server.py --transport streamable-http

# En otra terminal, ejecutar los tests HTTP
.venv/bin/python test_client.py
```

### STDIO

Para probar el transporte STDIO directamente:

```bash
.venv/bin/python server.py --transport stdio
```

En Windows PowerShell:

```powershell
$env:TRANSPORT = "stdio"
python server.py
```

Para usar **las dos variantes a la vez en MCP Inspector**, ejecuta el script desde cualquier directorio:

```bash
./run-inspector.sh
```

El script toma el puerto de la URL `demo-http` en [.mcp-inspector.json](./.mcp-inspector.json), inicia HTTP, espera a que esté disponible y luego ejecuta `npx @modelcontextprotocol/inspector --config .mcp-inspector.json`. Al cerrar el Inspector con `Ctrl+C`, también detiene el servidor HTTP. El archivo de configuración define ambos servidores: `demo-http` se conecta al proceso HTTP y `demo-stdio` inicia `server.py --transport stdio` como subproceso. El Inspector administra el ciclo de vida de ese proceso. Si no usas un entorno virtual `.venv`, asegúrate de que `python3` tenga instaladas las dependencias de [requirements.txt](./requirements.txt).

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
├── run-inspector.sh       # Inicia HTTP y MCP Inspector para probar ambos transportes
├── requirements.txt       # Dependencias
├── .env.example           # Template de variables de entorno
├── .env                   # Configuración local (no versionada)
├── .mcp-inspector.json    # Configuración de HTTP y STDIO para MCP Inspector
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
| Transporte | Streamable HTTP y STDIO |
| Python | 3.10+ |
