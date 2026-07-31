#!/usr/bin/env bash
# Configura la API key personal emitida por Horacio para Claude y Codex.
# El secreto se solicita sin eco y nunca se imprime.
set -euo pipefail

MCP_URL="${HORACIO_MCP_URL:-https://chatgpt.southlab.ai/mcp}"
KEY="${HORACIO_MCP_API_KEY:-}"

if [ "$#" -ne 0 ]; then
  echo "No pases la key como argumento. Usa HORACIO_MCP_API_KEY en este proceso o pégala cuando te la pida el script." >&2
  exit 1
fi

if [ -z "$KEY" ]; then
  if [ ! -r /dev/tty ]; then
    echo "No hay terminal interactiva. Define HORACIO_MCP_API_KEY solo para este proceso y vuelve a ejecutar." >&2
    exit 1
  fi
  printf 'Pega la API key creada en Horacio → Mi cuenta (no se mostrará): ' >/dev/tty
  IFS= read -r -s KEY </dev/tty
  printf '\n' >/dev/tty
fi

if [[ ! "$KEY" =~ ^hkg_live_[A-Za-z0-9_-]{43}$ ]]; then
  echo "La API key no tiene el formato personal de Horacio (hkg_live_…)." >&2
  exit 1
fi

if [ -L "$HOME/.claude/settings.json" ]; then
  echo "No se puede escribir en ~/.claude/settings.json porque es un enlace simbólico." >&2
  exit 1
fi
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ -L "$rc" ]; then
    echo "No se puede escribir en $rc porque es un enlace simbólico." >&2
    exit 1
  fi
done

# Claude Code: settings existente debe ser JSON válido; no se modifica silenciosamente si está corrupto.
HORACIO_MCP_API_KEY="$KEY" python3 <<'PY'
import json
import os
import pathlib
import sys

key = os.environ["HORACIO_MCP_API_KEY"]
path = pathlib.Path.home() / ".claude" / "settings.json"
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists() and path.read_text().strip():
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f"settings inválido en {path}; no se modificó: {exc}", file=sys.stderr)
        raise SystemExit(1)
else:
    data = {}
if not isinstance(data, dict):
    print(f"settings inválido en {path}: debe ser un objeto JSON", file=sys.stderr)
    raise SystemExit(1)
env = data.setdefault("env", {})
if not isinstance(env, dict):
    print(f"settings inválido en {path}: la sección env debe ser un objeto", file=sys.stderr)
    raise SystemExit(1)
env["HORACIO_MCP_API_KEY"] = key

tmp = pathlib.Path.home() / ".claude" / ".settings.json.tmp"
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
PY

# Shell: conserva una sola definición. Crea .zshrc si falta; ignora .bashrc si falta.
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ ! -f "$rc" ]; then
    [ "$rc" = "$HOME/.zshrc" ] || continue
    touch "$rc"
  fi

  tmp="${rc}.horacio-mcp.tmp"
  umask 077
  grep -v '^export HORACIO_MCP_API_KEY=' "$rc" > "$tmp" 2>/dev/null || true
  printf 'export HORACIO_MCP_API_KEY=%q\n' "$KEY" >> "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$rc"
done

is_valid_codex_registration() {
  if [ "$#" -ne 1 ]; then
    return 1
  fi
  MCP_EXPECTED_URL="$MCP_URL" PAYLOAD="$1" python3 <<'PY'
import json
import os
import sys

payload = os.environ["PAYLOAD"]
try:
    cfg = json.loads(payload)
except Exception:
    raise SystemExit(1)

transport = cfg.get("transport")
if not isinstance(transport, dict):
    raise SystemExit(1)

if cfg.get("enabled") is not True:
    raise SystemExit(1)
if transport.get("type") != "streamable_http":
    raise SystemExit(1)
if transport.get("url") != os.environ["MCP_EXPECTED_URL"]:
    raise SystemExit(1)
if transport.get("bearer_token_env_var") != "HORACIO_MCP_API_KEY":
    raise SystemExit(1)
if transport.get("http_headers") not in (None, {}):
    raise SystemExit(1)
if transport.get("env_http_headers") not in (None, {}):
    raise SystemExit(1)
PY
}

current_codex_config() {
  codex mcp get kg-educacion 2>/dev/null || true
}

CODEX_MSG="codex CLI no encontrado; registra el MCP manualmente"
if command -v codex >/dev/null 2>&1; then
  export HORACIO_MCP_API_KEY="$KEY"
  existing="$(current_codex_config)"
  if [ -n "$existing" ] && is_valid_codex_registration "$existing" >/dev/null; then
    CODEX_MSG="ya existe un registro correcto para kg-educacion"
  else
    if [ -n "$existing" ]; then
      codex mcp remove kg-educacion >/dev/null 2>&1 || true
    fi
    if codex mcp add kg-educacion --url "$MCP_URL" --bearer-token-env-var HORACIO_MCP_API_KEY >/dev/null 2>&1; then
      CODEX_MSG="registrado en Codex con bearer_token-env-var=HORACIO_MCP_API_KEY"
    else
      CODEX_MSG="no se pudo registrar; ejecuta codex mcp add kg-educacion --url $MCP_URL --bearer-token-env-var HORACIO_MCP_API_KEY"
    fi
  fi
fi

LAUNCHCTL_MSG="no aplica"
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
  if launchctl setenv HORACIO_MCP_API_KEY "$KEY" 2>/dev/null; then
    LAUNCHCTL_MSG="expuesta a las apps GUI de esta sesión"
  fi
fi

unset KEY HORACIO_MCP_API_KEY

echo "✅ API key personal de Horacio configurada."
echo "   MCP: $MCP_URL"
echo "   Claude: ~/.claude/settings.json"
echo "   Codex: $CODEX_MSG"
echo "   macOS GUI: $LAUNCHCTL_MSG"
echo "👉 Reinicia Claude o Codex y prueba consultar_curriculum."
