#!/usr/bin/env bash

# Configura la API key del KG de Horacio para Claude Code y Codex.
#
# La key debe tener permisos de cuenta de Horacio y puede incluirse en cualquiera
# de estos canales:
# - Argumento: bash kg-onboard.sh "<HORACIO_MCP_API_KEY>"
# - Variable de entorno: export HORACIO_MCP_API_KEY="..."
#
# La key se guarda en:
# - ~/.claude/settings.json -> env.HORACIO_MCP_API_KEY
# - ~/.zshrc y/o ~/.bashrc -> export HORACIO_MCP_API_KEY
# - Codex: `codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var HORACIO_MCP_API_KEY`
# - macOS GUI: launchctl setenv HORACIO_MCP_API_KEY

set -euo pipefail

API="${KG_API_BASE:-https://api.southlab.ai}"
KEY="${1:-${HORACIO_MCP_API_KEY:-}}"

if [ -z "$KEY" ]; then
  cat <<'EOF'
No se encontró una API key.

1) Crea tu key en: https://api.southlab.ai/mi-cuenta?vista=perfil
2) Copia la key (solo esta vez aparece completa)
3) Ejecuta:
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh" "<HORACIO_MCP_API_KEY>"

EOF
  exit 1
fi

if [[ ! "$KEY" =~ ^hkg_live_[A-Za-z0-9_-]{43}$ ]]; then
  echo "La key no parece válida (se esperaba hkg_live_<43 chars url-safe)." >&2
  exit 1
fi

persist_token() {
  local dest="$1"
  local tmp
  tmp="$(mktemp "${dest}.tmp.XXXXXX")"
  if [ -f "$dest" ]; then
    awk '
      $0 !~ /^export HORACIO_MCP_API_KEY=/ {
        print $0
      }
    ' "$dest" > "$tmp"
  else
    : > "$tmp"
  fi
  printf 'export HORACIO_MCP_API_KEY=%s\n' "$KEY" >> "$tmp"
  mv "$tmp" "$dest"
}

# 1) Claude Code
python3 - "$KEY" <<'PY'
import json
import pathlib
import sys

key = sys.argv[1]
path = pathlib.Path.home() / ".claude" / "settings.json"
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists() and path.read_text().strip():
    try:
        data = json.loads(path.read_text())
    except Exception:
        data = {}
else:
    data = {}
if not isinstance(data, dict):
    data = {}
data.setdefault("env", {})["HORACIO_MCP_API_KEY"] = key
path.write_text(json.dumps(data, indent=2) + "\n")
PY

# 2) Shells
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  [ -f "$rc" ] || continue
  persist_token "$rc"
done

# 3) Codex
CODEX_MSG="❌ No se pudo registrar automáticamente. Corre: codex mcp add kg-educacion --url $API/mcp --bearer-token-env-var HORACIO_MCP_API_KEY"
if command -v codex >/dev/null 2>&1; then
  export HORACIO_MCP_API_KEY="$KEY"
  codex mcp remove kg-educacion >/dev/null 2>&1 || true
  if codex mcp add kg-educacion --url "$API/mcp" --bearer-token-env-var HORACIO_MCP_API_KEY >/dev/null 2>&1; then
    CODEX_MSG="✅ Registrado en Codex (~/.codex/config.toml) con bearer_token_env_var=HORACIO_MCP_API_KEY"
  fi
fi

# 4) macOS GUI
LAUNCHCTL_MSG="no aplica (no es macOS)"
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
  if launchctl setenv HORACIO_MCP_API_KEY "$KEY" 2>/dev/null; then
    LAUNCHCTL_MSG="✅ Aplicaciones GUI de esta sesión ven HORACIO_MCP_API_KEY (usa LaunchAgent para persistir al reinicio)"
  fi
fi

echo "✅ API key configurada para kg-educacion."
echo "   Entorno: HORACIO_MCP_API_KEY=$KEY"
echo "   Claude Code: ~/.claude/settings.json (env.HORACIO_MCP_API_KEY)"
echo "   Shell: ~/.zshrc y ~/.bashrc"
echo "   Codex: ${CODEX_MSG}"
echo "   macOS GUI: ${LAUNCHCTL_MSG}"
echo "🔁 Reinicia Codex/Claude y valida: runtime_status"
