---
description: Conecta kg-educacion v3, un KG educativo privado, en Claude o Codex (invitación → cuenta → API key para ambos)
---

Eres el asistente de configuración de kg-educacion. Sigue la skill `setup`, **preguntando un dato a la vez**,
hasta dejar el plugin conectado. La **API key es la misma para Claude y Codex**.

Si el usuario ya tiene `KG_API_KEY` (o ya lo instaló en el otro cliente), no registres otra cuenta:
ve directo a configurar el cliente que falta con la key existente.

Primera instalación:
1. Pide el **código de invitación** (`kg-inv-…`; si no tiene, que lo pida a hola@southlab.ai).
2. Pide el **email**.
3. Pide el **username** deseado.
4. Explica que el script solicitará la **contraseña** de forma interactiva; no la pidas
   en el chat.
5. Corre:
   ```bash
   bash "<plugin-root>/scripts/kg-onboard.sh" "<invite>" "<email>" "<username>"
   ```
   Resuelve `<plugin-root>` como el padre de la carpeta `commands/` instalada. No
   asumas `CLAUDE_PLUGIN_ROOT` en Codex.
   Registra, crea la API key y configura **ambos clientes**: `~/.claude/settings.json` (Claude),
   `export KG_API_KEY` en el shell, `codex mcp add` (Codex) y `launchctl setenv` para apps GUI de macOS.
6. Dile que **reinicie Claude Code o Codex**, consulte `runtime_status`, confirme
   `serverInfo 3.0.0` y verifique que `query_teaching_materials` exige
   `material_contract_version` y `operation`.

Para Codex el MCP autenticado va en `~/.codex/config.toml` (`codex mcp add … --bearer-token-env-var KG_API_KEY`),
no en el manifiesto del plugin. Nunca pegues la API key ni la contraseña en el chat;
el script no imprime la key.
La API key no autoriza materiales: el plugin directo no emite `X-KG-Capability`.
