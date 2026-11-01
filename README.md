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
# Crear un token aleatorio (Linux/macOS)
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
# En Windows: .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
# Copiar el resultado en MCP_TOKEN dentro de .env
```

### Configuración

| Archivo | Propósito |
|---|---|
| `.env` | Valores predeterminados: `TRANSPORT`, `HOST`, `PORT`, `LOG_LEVEL`, `AUTH_REQUIRED`, `MCP_TOKEN` |
| `.mcp-inspector.json` | Configura HTTP y STDIO para MCP Inspector |
| `.vscode/mcp.json` | Configuración MCP para VS Code |
| `.kilo/kilo.jsonc` | Configuración MCP para Kilo CLI |

| Variable | Default | Uso |
|---|---|---|
| `TRANSPORT` | `streamable-http` | Transporte MCP: `streamable-http` o `stdio` |
| `PORT` | `8080` | Puerto del servidor HTTP |
| `HOST` | `127.0.0.1` | Dirección de escucha (server bind) |
| `LOG_LEVEL` | `INFO` | Nivel de logging (debug, info, warning, error, critical) |
| `AUTH_REQUIRED` | `true` | Activa o desactiva la autenticación Bearer en HTTP |
| `MCP_TOKEN` | *(requerido si `AUTH_REQUIRED=true`)* | Token Bearer aleatorio para proteger todas las solicitudes HTTP |

`AUTH_REQUIRED=true` es el valor predeterminado. Puedes poner `AUTH_REQUIRED=false` en `.env` o iniciar el servidor con `--no-require-auth` para probar HTTP sin token; `--require-auth` lo activa. Si está activada, HTTP no arranca sin `MCP_TOKEN`. Genera un token distinto por entorno, guárdalo solo en `.env` (excluido de Git) o en el gestor de secretos de tu despliegue, y no lo compartas en logs ni en archivos de configuración versionados.

Esta autenticación protege el transporte HTTP, donde el cliente envía `Authorization: Bearer ...`. No se aplica a STDIO: ahí el cliente inicia un proceso local y el control de acceso depende de quién puede ejecutarlo. La autenticación de la API externa que una herramienta pudiera consumir sería otra credencial, inyectada al proceso por `env` y utilizada por esa herramienta; este servidor de demostración no consume APIs externas ni usa un token en STDIO.

El servidor escucha solo en la máquina local por defecto. Si lo expones a otra máquina, usa HTTPS (por ejemplo, detrás de un proxy TLS) y configura `HOST` para la interfaz de red correspondiente.

### Variables de entorno heredadas

Las variables definidas en la terminal, en VS Code o en otro proceso se heredan al iniciar Python y tienen prioridad sobre los valores de `.env`: `load_dotenv()` no las reemplaza por defecto. Si cambias `MCP_TOKEN` o `AUTH_REQUIRED` en `.env`, detén y reinicia el servidor para que tome la configuración nueva.

Puedes comprobar si existen variables relevantes sin imprimir sus valores (Bash):

```bash
for var in MCP_TOKEN AUTH_REQUIRED HOST PORT; do
  if [[ -v $var ]]; then
    echo "$var: definida en el entorno"
  else
    echo "$var: no definida en el entorno"
  fi
done
```

Para iniciar el servidor con los valores de `.env`, elimina del entorno heredado las variables que pueden afectar a la autenticación y al puerto:

```bash
env -u MCP_TOKEN -u AUTH_REQUIRED -u HOST -u PORT \
  .venv/bin/python server.py --transport streamable-http
```

El servidor carga entonces esas opciones desde `.env`. Esto no cambia las variables de la terminal actual ni afecta a procesos ya iniciados. También puedes limpiar la terminal actual con `unset MCP_TOKEN AUTH_REQUIRED HOST PORT`; no uses `env | grep TOKEN` para diagnosticar, porque mostraría el secreto.

## Uso Rápido

### Streamable HTTP

```bash
# Iniciar el servidor HTTP (deja este proceso en ejecución)
.venv/bin/python server.py --transport streamable-http

# En otra terminal, ejecutar los tests HTTP
.venv/bin/python test_client.py
```

El cliente de prueba lee `AUTH_REQUIRED` y `MCP_TOKEN` de `.env`. Con autenticación habilitada, comprueba los rechazos HTTP 401 y continúa con el token válido; deshabilitada, verifica que HTTP funciona sin token. Puedes usar `--require-auth` o `--no-require-auth` para configurar el modo esperado por las pruebas.

### Pruebas manuales con curl

Con el servidor ejecutándose y `HOST=127.0.0.1`, `PORT=8001` en `.env`, desde la raíz del proyecto ejecuta:

```bash
./run-test.sh
```

El script lee `MCP_TOKEN` de `.env` y envía una solicitud MCP `initialize` a `http://127.0.0.1:8001/mcp`. Con autenticación habilitada, debe responder `HTTP 200 OK` (o `200`); el cuerpo contiene la respuesta JSON-RPC de inicialización. No guardes el token literal en el script ni lo pegues en la línea de comandos o en capturas.

También puedes probar sin token usando curl. Esta solicitud debe responder `401 Unauthorized` si `AUTH_REQUIRED=true`:

```bash
curl -i -X POST http://127.0.0.1:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"prueba-manual","version":"1.0"}}}'
```

Para probar `401` por token incorrecto, carga el valor desde `.env` sin imprimirlo y añade una cadena que lo invalide:

```bash
set -a
source .env
set +a
curl -i -X POST http://127.0.0.1:8001/mcp \
  -H "Authorization: Bearer ${MCP_TOKEN}-incorrecto" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"prueba-manual","version":"1.0"}}}'
unset MCP_TOKEN
```

Si recibes `401` usando `./run-test.sh`, comprueba que reiniciaste el servidor después de cambiar `.env` y que no inició con un `MCP_TOKEN` heredado diferente. No hace falta mostrar el token para verificarlo: usa el bucle de diagnóstico anterior y reinicia con `env -u MCP_TOKEN ...`. El token que se haya pegado en un chat, archivo compartido o captura debe considerarse expuesto y reemplazarse en `.env`.

Para probar HTTP sin autenticación sin editar `.env`:

```bash
AUTH_REQUIRED=false .venv/bin/python server.py --transport streamable-http
# En otra terminal:
AUTH_REQUIRED=false .venv/bin/python test_client.py
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

En STDIO no se envía un Bearer en los mensajes MCP. Si una herramienta necesita llamar a una API externa, el cliente puede inyectarle una variable de entorno al proceso hijo (por ejemplo, `API_BEARER_TOKEN`) y esa herramienta la usa en la cabecera de su petición saliente. `MCP_TOKEN` y `AUTH_REQUIRED` de este proyecto protegen/prueban el endpoint HTTP; no se usan como autenticación de STDIO ni como credenciales de una API externa. Actualmente el servidor demo no incluye llamadas a APIs externas.

Para usar **las dos variantes a la vez en MCP Inspector**, ejecuta el script desde cualquier directorio:

```bash
./run-inspector.sh
```

El script toma el puerto de la URL `demo-http` en [.mcp-inspector.json](./.mcp-inspector.json), inicia HTTP y genera una configuración temporal del Inspector. Si `AUTH_REQUIRED=true`, añade el token a las solicitudes; si está en `false`, no lo requiere. La configuración temporal se elimina al cerrar el script. Al cerrar el Inspector con `Ctrl+C`, también detiene el servidor HTTP. `demo-stdio` inicia `server.py --transport stdio` como subproceso. Si no usas un entorno virtual `.venv`, asegúrate de que `python3` tenga instaladas las dependencias de [requirements.txt](./requirements.txt).

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

## Características MCP obsoletas (no implementadas)

Las siguientes capacidades del protocolo MCP están **deprecadas** o fueron **removidas** de la especificación. Este servidor **no las usa**:

| Característica | Estado | Por qué |
|---|---|---|
| HTTP + SSE | Deprecado | Reemplazado por **Streamable HTTP** (más directo, seguro y escalable) |
| Roots (`roots/list`, `notifications/roots/list_changed`) | Deprecado | Complejidad innecesaria y sin control de acceso estricto |
| Sampling (`sampling/createMessage`) | Deprecado | Mezcla responsabilidades de inferencia del modelo dentro del protocolo |
| Logging (`logging/setLevel`, `notifications/message`) | Deprecado | El logging debe gestionarse con sistemas de observabilidad estándar (OpenTelemetry, stdout/stderr) |

Este servidor usa exclusivamente **Streamable HTTP** como transporte y no implementa Roots, Sampling ni Logging a nivel de protocolo.

## Integración con Clientes MCP

### VS Code

El archivo [.vscode/mcp.json](./.vscode/mcp.json) registra el servidor y solicita un token al conectarse. Si `AUTH_REQUIRED=false`, puedes quitar la cabecera `Authorization` del archivo o introducir cualquier valor. Si usas la extensión Kilo Code, configura la cabecera solo cuando la autenticación esté habilitada.

### Kilo CLI

El archivo `.kilo/kilo.jsonc` configura el MCP. En la TUI, usa `/mcps` para activar/desactivar.

### MCP Inspector

> ⚠️ El Inspector MCP (`npx @modelcontextprotocol/inspector`) puede solicitar autenticación vía naveador. Si falla, usa la URL directa:

```bash
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8001/mcp --method tools/list \
  --header "Authorization: Bearer $MCP_TOKEN"
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
├── run-test.sh            # Prueba manual curl (MCP initialize)
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
