#!/usr/bin/env bash
# Onboarding de kg-educacion: registra la cuenta, crea una API key y configura
# Claude, Codex y el entorno local sin imprimir la key ni aceptar contraseñas
# en argumentos de proceso.
#
# Uso: kg-onboard.sh <invite_code> <email> <username>
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "❌ La contraseña no se acepta como argumento; el script la solicita de forma segura." >&2
  exit 2
fi

API="${KG_API_BASE:-https://api.southlab.ai}"
INVITE="${1:?falta el código de invitación}"
EMAIL="${2:-}"
USERNAME="${3:?falta el username}"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

# Falla antes de registrar o crear una key si la configuración existente no se
# puede preservar como objeto JSON.
if [ -L "$CLAUDE_SETTINGS" ]; then
  echo "❌ $CLAUDE_SETTINGS es un enlace simbólico; no se registró ni modificó nada." >&2
  exit 2
fi
if [ -f "$CLAUDE_SETTINGS" ]; then
  python3 - "$CLAUDE_SETTINGS" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"❌ {path} contiene JSON inválido; no se modificó: {exc}")
if not isinstance(value, dict):
    raise SystemExit(f"❌ {path} debe contener un objeto JSON; no se modificó")
if "env" in value and not isinstance(value["env"], dict):
    raise SystemExit(f"❌ {path}: env debe ser un objeto; no se modificó")
PY
fi

# Los rc contienen la API key. Se rechazan symlinks antes de cualquier llamada
# de red y la escritura posterior usa un temporal aleatorio en el mismo
# directorio, con permisos sólo para el usuario.
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ -L "$rc" ]; then
    echo "❌ $rc es un enlace simbólico; no se registró ni modificó nada." >&2
    exit 2
  fi
done

printf 'Contraseña: ' >&2
IFS= read -r -s PASSWORD || true
if [ -t 0 ]; then
  printf '\n' >&2
fi
if [ -z "$PASSWORD" ]; then
  echo "❌ La contraseña no puede estar vacía." >&2
  exit 2
fi

json_payload() {
  python3 -c '
import json
import sys

keys = sys.argv[1:]
values = sys.stdin.read().splitlines()
if len(values) != len(keys):
    raise SystemExit("invalid payload input")
print(json.dumps(dict(zip(keys, values)), ensure_ascii=False, separators=(",", ":")))
' "$@"
}

REGISTER_PAYLOAD=$(
  printf '%s\n%s\n%s\n%s\n' "$USERNAME" "$PASSWORD" "$EMAIL" "$INVITE" |
    json_payload username password email invite_code
)
REG=$(
  printf '%s' "$REGISTER_PAYLOAD" |
    curl -fsS -w '\n%{http_code}' -X POST "$API/account/register" \
      -H 'Content-Type: application/json' --data-binary @- 2>/dev/null
) || true
HTTP=$(printf '%s' "$REG" | tail -1)
BODY=$(printf '%s' "$REG" | sed '$d')
if [ "$HTTP" != "200" ]; then
  case "$HTTP" in
    403) echo "❌ Código de invitación inválido o ya usado. Pide uno nuevo a hola@southlab.ai." >&2 ;;
    422) echo "❌ Datos inválidos: $BODY" >&2 ;;
    *) echo "❌ No se pudo registrar (HTTP $HTTP): $BODY" >&2 ;;
  esac
  exit 1
fi

LABEL=$(hostname 2>/dev/null || printf 'plugin')
KEY_PAYLOAD=$(
  printf '%s\n%s\n%s\n' "$USERNAME" "$PASSWORD" "$LABEL" |
    json_payload username password label
)
KEYJSON=$(
  printf '%s' "$KEY_PAYLOAD" |
    curl -fsS -X POST "$API/account/keys" \
      -H 'Content-Type: application/json' --data-binary @-
)
KEY=$(printf '%s' "$KEYJSON" | python3 -c '
import json
import sys

value = json.load(sys.stdin).get("api_key")
if not isinstance(value, str) or not value:
    raise SystemExit("la respuesta no contiene api_key")
print(value, end="")
')

# Claude: merge atómico; un settings inválido nunca se reemplaza.
mkdir -p "$(dirname "$CLAUDE_SETTINGS")"
printf '%s' "$KEY" | python3 -c '
import json
import os
import pathlib
import stat
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
key = sys.stdin.read()
value = {}
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
if path.exists():
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit(f"❌ {path} no es un archivo regular")
        with os.fdopen(descriptor, encoding="utf-8") as source:
            descriptor = -1
            value = json.load(source)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
value.setdefault("env", {})["KG_API_KEY"] = key
temporary_fd, temporary_name = tempfile.mkstemp(
    prefix=f".{path.name}.kg-", dir=path.parent
)
try:
    os.fchmod(temporary_fd, 0o600)
    with os.fdopen(temporary_fd, "w", encoding="utf-8") as target:
        temporary_fd = -1
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary_name, path)
finally:
    if temporary_fd >= 0:
        os.close(temporary_fd)
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
' "$CLAUDE_SETTINGS"

# Shell: conserva el resto del archivo y reemplaza sólo la exportación propia.
# Python abre sin seguir symlinks, crea un temporal impredecible con O_EXCL,
# fuerza 0600 y reemplaza atómicamente.
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ ! -f "$rc" ]; then
    [ "$rc" = "$HOME/.zshrc" ] || continue
  fi
  printf '%s' "$KEY" | python3 -c '
import os
import pathlib
import stat
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
key = sys.stdin.read()
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
content = ""
if path.exists():
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit(f"❌ {path} no es un archivo regular")
        with os.fdopen(descriptor, encoding="utf-8") as source:
            descriptor = -1
            content = source.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)

lines = [
    line for line in content.splitlines()
    if not line.startswith("export KG_API_KEY=")
]
lines.append(f"export KG_API_KEY={key}")
rendered = "\n".join(lines) + "\n"

temporary_fd, temporary_name = tempfile.mkstemp(
    prefix=f".{path.name}.kg-", dir=path.parent
)
try:
    os.fchmod(temporary_fd, 0o600)
    with os.fdopen(temporary_fd, "w", encoding="utf-8") as target:
        temporary_fd = -1
        target.write(rendered)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary_name, path)
finally:
    if temporary_fd >= 0:
        os.close(temporary_fd)
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
' "$rc"
done

CODEX_MSG="codex CLI no encontrado; registra el MCP con bearer_token_env_var=KG_API_KEY"
if command -v codex >/dev/null 2>&1; then
  export KG_API_KEY="$KEY"
  EXISTING_CODEX=$(codex mcp get kg-educacion --json 2>/dev/null || true)
  CODEX_STATE=$(
    printf '%s' "$EXISTING_CODEX" | python3 -c '
import json
import sys

expected_url = sys.argv[1]
raw = sys.stdin.read()
if not raw:
    print("missing")
    raise SystemExit
try:
    value = json.loads(raw)
except json.JSONDecodeError:
    print("invalid")
    raise SystemExit
transport = value.get("transport", {})
if (
    value.get("enabled") is True
    and transport.get("type") == "streamable_http"
    and transport.get("url") == expected_url
    and transport.get("bearer_token_env_var") == "KG_API_KEY"
    and "http_headers" in transport
    and transport.get("http_headers") in (None, {})
    and "env_http_headers" in transport
    and transport.get("env_http_headers") in (None, {})
):
    print("current")
else:
    print("stale")
' "$API/mcp"
  )
  if [ "$CODEX_STATE" = "current" ]; then
    CODEX_MSG="registro MCP verificado (URL y bearer_token_env_var correctos)"
  elif [ "$CODEX_STATE" = "invalid" ]; then
    echo "❌ Codex devolvió un registro kg-educacion ilegible; no se modificó." >&2
    exit 1
  else
    if [ "$CODEX_STATE" = "stale" ]; then
      codex mcp remove kg-educacion >/dev/null 2>&1 || {
        echo "❌ No se pudo retirar el registro Codex obsoleto." >&2
        exit 1
      }
    fi
    if codex mcp add kg-educacion --url "$API/mcp" \
    --bearer-token-env-var KG_API_KEY >/dev/null 2>&1; then
      CODEX_MSG="registro MCP creado/verificado con URL y bearer_token_env_var correctos"
    else
      echo "❌ No se pudo crear el registro Codex correcto; ejecuta codex mcp add." >&2
      exit 1
    fi
  fi
fi

LAUNCHCTL_MSG="no aplica (no es macOS)"
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] &&
  command -v launchctl >/dev/null 2>&1; then
  if launchctl setenv KG_API_KEY "$KEY" 2>/dev/null; then
    LAUNCHCTL_MSG="expuesta a apps GUI durante esta sesión"
  fi
fi

echo "✅ Cuenta creada y API key configurada localmente."
echo "   usuario: $USERNAME"
echo "   API key: guardada; no se imprime."
echo "   Claude Code: settings local + shell."
echo "   Codex:       $CODEX_MSG."
echo "   macOS GUI:   $LAUNCHCTL_MSG."
echo "👉 Reinicia Claude Code o Codex y prueba una consulta curricular."
