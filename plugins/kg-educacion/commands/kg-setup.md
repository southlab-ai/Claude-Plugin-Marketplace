---
description: Conecta Horacio y su KG en Claude o Codex usando la API key personal de Mi cuenta
---

Sigue la skill `setup` hasta dejar el plugin conectado.

1. El usuario obtiene su key en **Horacio → Mi cuenta → API key para Codex y MCP**.
2. No le pidas que pegue el secreto en el chat.
3. Pídele que ejecute localmente:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh"
   ```

   El script pide la key sin eco y configura Claude, Codex y apps GUI de macOS.
4. Tras reiniciar el cliente, prueba `consultar_curriculum` y, si la cuenta tiene
   acceso material, `consultar_recursos`.

La key conserva los permisos actuales de la cuenta; no concede features ni materiales
por sí misma y no necesita que el usuario gestione capabilities.
