---
name: setup
description: Use when Horacio and KG Educación are being connected in Claude or Codex, the user needs a personal MCP API key, the plugin was upgraded, or requests return 401.
---

# Configurar Horacio + KG Educación

El plugin conecta al MCP de Horacio. Horacio usa el KG educativo privado e independiente
para recuperar evidencia con fuentes y resuelve en cada request los features, colegio y
grants vigentes de la cuenta. Las capabilities efímeras para materiales se generan dentro
del servidor; el usuario no debe crearlas ni guardar headers adicionales.

## Elegir el flujo

- Si ya existe `HORACIO_MCP_API_KEY` o el otro cliente funciona, no generes otra key:
  configura solo el cliente faltante.
- Si no existe, sigue "Obtener la key".
- Tras actualizar, conserva la key y refresca marketplace, cliente y sesión.

## Obtener la key

1. Indica al usuario que ingrese a Horacio.
2. Debe abrir **Mi cuenta → API key para Codex y MCP**.
3. Debe crear o regenerar la key y copiarla. Horacio la muestra una sola vez.
4. No le pidas que pegue la API key en el chat.

## Configurar ambos clientes

Resuelve `<plugin-root>` como dos niveles sobre este `SKILL.md`; no asumas
`CLAUDE_PLUGIN_ROOT`, porque Codex no define esa variable. Pide al usuario que ejecute en
su propia terminal interactiva:

```bash
bash "<plugin-root>/scripts/kg-onboard.sh"
```

El script solicita la key sin eco y configura Claude, Codex, el shell y las apps GUI de
macOS. No recibe el secreto como argumento de línea de comandos.

## Configurar un cliente con una key existente

- Claude Code: `.mcp.json` lee `Bearer ${HORACIO_MCP_API_KEY}`. Exporta la variable
  o define `env.HORACIO_MCP_API_KEY` en `~/.claude/settings.json`; reinicia Claude.
- Codex:

  ```bash
  codex mcp add kg-educacion --url https://chatgpt.southlab.ai/mcp --bearer-token-env-var HORACIO_MCP_API_KEY
  ```

- Apps macOS abiertas desde el Dock:
  `launchctl setenv HORACIO_MCP_API_KEY "$HORACIO_MCP_API_KEY"`.

El manifiesto de Codex guarda el nombre de la variable, no el secreto.

## Verificar

1. Reinicia Claude o Codex y abre una sesión nueva.
2. Ejecuta `consultar_curriculum` para Lenguaje 4° básico y verifica citas.
3. Si la cuenta tiene acceso material, ejecuta `consultar_recursos` para un texto escolar.
4. Si esa tool responde que la función no está habilitada, el plugin está autenticado pero
   la cuenta no tiene el feature o grant vigente; no regeneres la key.

## Diagnóstico

| Síntoma | Acción |
|---|---|
| Consulta `401` | Revisa `codex mcp get kg-educacion`, `launchctl getenv HORACIO_MCP_API_KEY` y reinicia. |
| Función no habilitada | Revisa el feature de la cuenta en Control Tower; la key no amplía permisos. |
| Material sin acceso | Revisa el grant de materiales de esa cuenta; no agregues headers manuales. |
| `Deserialize error … JsonRpcMessage` | Codex inició el MCP sin token; revisa la variable y el registro MCP. |

## Seguridad

Nunca pegues la key en el chat ni la subas a un repositorio. Regenerar desde Mi cuenta
revoca inmediatamente la anterior. Bloquear la cuenta también corta el acceso.
