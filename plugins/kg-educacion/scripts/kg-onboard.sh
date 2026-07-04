#!/usr/bin/env bash
# Onboarding de kg-educacion: registra la cuenta con el código de invitación,
# genera la API key (la MISMA para Claude y Codex) y la deja CONFIGURADA en:
#   - Claude Code: ~/.claude/settings.json (env.KG_API_KEY)
#   - shell:       ~/.zshrc / ~/.bashrc (export KG_API_KEY)
#   - Codex:       ~/.codex/config.toml (codex mcp add ... --bearer-token-env-var KG_API_KEY)
#   - macOS GUI:   launchctl setenv KG_API_KEY (apps abiertas desde el Dock)
#
# Uso: kg-onboard.sh <invite_code> <email> <username> [password]
# Si no se pasa password, se genera una segura y se muestra una vez.
set -euo pipefail

API="${KG_API_BASE:-https://api.southlab.ai}"
INVITE="${1:?falta el código de invitación}"
EMAIL="${2:-}"
USERNAME="${3:?falta el username}"
PASSWORD="${4:-}"
GEN_PW=0
if [ -z "$PASSWORD" ]; then PASSWORD="kg-$(openssl rand -hex 10)"; GEN_PW=1; fi

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }

# 1) Registro (gateado por invitación)
REG=$(curl -fsS -w '\n%{http_code}' -X POST "$API/account/register" -H 'Content-Type: application/json' \
  -d "{\"username\":$(json_escape "$USERNAME"),\"password\":$(json_escape "$PASSWORD"),\"email\":$(json_escape "$EMAIL"),\"invite_code\":$(json_escape "$INVITE")}" 2>/dev/null) || true
HTTP=$(printf '%s' "$REG" | tail -1)
BODY=$(printf '%s' "$REG" | sed '$d')
if [ "$HTTP" != "200" ]; then
  case "$HTTP" in
    403) echo "❌ Código de invitación inválido o ya usado. Pide uno nuevo a hola@southlab.ai." >&2 ;;
    422) echo "❌ Datos inválidos: $BODY" >&2 ;;
    *)   echo "❌ No se pudo registrar (HTTP $HTTP): $BODY" >&2 ;;
  esac
  exit 1
fi

# 2) Crear API key
KEYJSON=$(curl -fsS -X POST "$API/account/keys" -H 'Content-Type: application/json' \
  -d "{\"username\":$(json_escape "$USERNAME"),\"password\":$(json_escape "$PASSWORD"),\"label\":$(json_escape "$(hostname 2>/dev/null || echo plugin)")}")
KEY=$(printf '%s' "$KEYJSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_key"])')

# 3) Persistir KG_API_KEY automáticamente
# 3a) Claude Code: ~/.claude/settings.json -> env.KG_API_KEY
python3 - "$KEY" <<'PY'
import json, sys, pathlib
key = sys.argv[1]
p = pathlib.Path.home() / ".claude" / "settings.json"
p.parent.mkdir(parents=True, exist_ok=True)
try:
    d = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}
except Exception:
    d = {}
d.setdefault("env", {})["KG_API_KEY"] = key
p.write_text(json.dumps(d, indent=2) + "\n")
PY
# 3b) Codex / terminal: shell rc (sin sed -i, portable)
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  [ -f "$rc" ] || { [ "$rc" = "$HOME/.zshrc" ] && touch "$rc" || continue; }
  grep -v '^export KG_API_KEY=' "$rc" > "$rc.kgtmp" 2>/dev/null || true
  mv "$rc.kgtmp" "$rc"
  printf 'export KG_API_KEY=%s\n' "$KEY" >> "$rc"
done

# 3c) Codex: registra el MCP remoto con la key por variable de entorno (config.toml)
CODEX_MSG="codex CLI no encontrado; en Codex corre: codex mcp add kg-educacion --url $API/mcp --bearer-token-env-var KG_API_KEY"
if command -v codex >/dev/null 2>&1; then
  export KG_API_KEY="$KEY"
  codex mcp remove kg-educacion >/dev/null 2>&1 || true
  if codex mcp add kg-educacion --url "$API/mcp" --bearer-token-env-var KG_API_KEY >/dev/null 2>&1; then
    CODEX_MSG="registrado en Codex (~/.codex/config.toml) con bearer_token_env_var=KG_API_KEY"
  else
    CODEX_MSG="no se pudo registrar solo; corre: codex mcp add kg-educacion --url $API/mcp --bearer-token-env-var KG_API_KEY"
  fi
fi

# 3d) macOS: las apps GUI (Dock/Finder) no heredan ~/.zshrc → expón la key vía launchctl
LAUNCHCTL_MSG="no aplica (no es macOS)"
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
  if launchctl setenv KG_API_KEY "$KEY" 2>/dev/null; then
    LAUNCHCTL_MSG="expuesta a apps GUI de esta sesión; para que sobreviva reinicios deja un LaunchAgent"
  fi
fi

echo "✅ Cuenta creada y API key configurada automáticamente."
echo "   usuario: $USERNAME"
[ "$GEN_PW" = 1 ] && echo "   contraseña (guárdala para gestionar tus keys): $PASSWORD"
echo "   API key: ${KEY}"
echo "   Claude Code: ~/.claude/settings.json (env.KG_API_KEY) + shell (export)."
echo "   Codex:       ${CODEX_MSG}."
echo "   macOS GUI:   ${LAUNCHCTL_MSG}."
echo "👉 Reinicia Claude Code o Codex para que tome la conexión, y pregunta algo curricular."
