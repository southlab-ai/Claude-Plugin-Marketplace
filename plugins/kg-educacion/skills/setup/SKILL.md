---
name: setup
description: Asistente de configuración de kg-educacion v3, un KG educativo privado e independiente con sourcing MINEDUC. Conecta el MCP en Claude Code o Codex usando la API key que tengas en tu cuenta de Horacio (`HORACIO_MCP_API_KEY`).
---

# Asistente de configuración de kg-educacion

`kg-educacion` es un KG privado, independiente y no afiliado a MINEDUC. Conecta al runtime
`serverInfo 3.0.0`; la autoridad de los datos corresponde a las fuentes citadas.

El acceso a material docente y herramientas usa la **key por cuenta** de tu cuenta de Horacio con permisos completos de tu plan.
La clave correcta se genera en `mi-cuenta` y aparece como `HORACIO_MCP_API_KEY`.

## Flujo de configuración

1. Pide la key al usuario (la única fuente válida). Si no la tiene, guíalo a
   `https://api.southlab.ai/mi-cuenta?vista=perfil` para crearla.
2. Ejecuta el script con la key:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh" "<HORACIO_MCP_API_KEY>"
```

3. Si la key ya está en entorno (`HORACIO_MCP_API_KEY`) también puede correr el script sin args:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh"
```

4. Reinicia Claude/Codex, valida que quedó el token y prueba `runtime_status`.

## Qué configura el script
- `~/.claude/settings.json` → `env.HORACIO_MCP_API_KEY`
- `export HORACIO_MCP_API_KEY=...` en `~/.zshrc` y `~/.bashrc`
- Registro de Codex: `codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var HORACIO_MCP_API_KEY`
- macOS GUI: `launchctl setenv HORACIO_MCP_API_KEY ...`

## Errores
- 401 al consultar = la key no llegó al cliente. Revisa que `HORACIO_MCP_API_KEY` exista en entorno,
  que `~/.claude/settings.json` y `~/.codex/config.toml` apunten a esa variable, y reinicia cliente.
- Si `runtime_status` responde y trae `serverInfo 3.0.0`, el plugin está autenticado correctamente.
- Si aparece `Deserialize error ... JsonRpcMessage` al conectar, suele faltar el `codex mcp add` con la
  variable `HORACIO_MCP_API_KEY`.

## Seguridad
La API key se guarda en el equipo del usuario (settings de Claude, shell, config.toml de Codex).
Nunca pegues la key completa en el chat ni la subas a repositorios. La contraseña del usuario no se guarda en archivos del proyecto.
