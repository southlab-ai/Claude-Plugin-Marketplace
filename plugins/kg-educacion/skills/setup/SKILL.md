---
name: setup
description: Use when kg-educacion is being installed or upgraded, the user lacks KG_API_KEY, Claude or Codex cannot connect, runtime_status fails, tools are stale after an update, or the MCP returns 401.
---

# Configurar kg-educacion

`kg-educacion` es privado e independiente. La misma `KG_API_KEY` sirve en Claude y
Codex.

## Elegir el flujo

- Si ya existe `KG_API_KEY` o el otro cliente funciona, no registres otra cuenta:
  configura sólo el cliente faltante.
- Si no existe una key, ejecuta el registro guiado.
- Tras actualizar, conserva la key y refresca marketplace, cliente y sesión.

## Registro guiado

Pide un dato a la vez:

1. Código de invitación `kg-inv-…`; si no tiene, debe solicitarlo a
   `hola@southlab.ai`.
2. Email.
3. Username.
4. Indícale que el script solicitará una contraseña de forma interactiva. No la pidas
   en el chat.

Resuelve `<plugin-root>` como dos niveles sobre este `SKILL.md`; no asumas
`CLAUDE_PLUGIN_ROOT`, porque Codex no define esa variable. Después ejecuta:

```bash
bash "<plugin-root>/scripts/kg-onboard.sh" "<invite_code>" "<email>" "<username>"
```

El script solicita la contraseña, crea la key y configura ambos clientes.

## Configurar un cliente con una key existente

- Claude Code: `.mcp.json` lee `Bearer ${KG_API_KEY}`. Exporta la variable o define
  `env.KG_API_KEY` en `~/.claude/settings.json`; reinicia Claude.
- Codex:

  ```bash
  codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var KG_API_KEY
  ```

- Apps macOS abiertas desde el Dock: expón la variable con
  `launchctl setenv KG_API_KEY "$KG_API_KEY"`.

El manifiesto de Codex guarda el nombre de la variable, no el secreto.

## Verificar

1. Reinicia Claude o Codex y abre una sesión nueva.
2. Consulta `kg-educacion:runtime_status`; debe informar `serverInfo 3.0.0`.
3. Comprueba que la schema fresca de
   `kg-educacion:query_teaching_materials` exige `material_contract_version` y
   `operation`.
4. Prueba una consulta curricular que devuelva citas.

Si aún aparece el contrato material anterior, refresca el marketplace y reinicia el
cliente. No pruebes con payloads legacy.

La verificación material no forma parte del setup directo: requiere
`X-KG-Capability`, emitida server-side por un consumidor autorizado y ligada al
usuario, operaciones, proveedor y modelo. No la solicites al usuario ni la guardes.

## Diagnóstico

| Síntoma | Acción |
|---|---|
| Registro `403` | El código es inválido o usado; solicita otro. |
| Consulta `401` | La key no llegó al proceso; revisa `codex mcp get kg-educacion` o `launchctl getenv KG_API_KEY` y reinicia. |
| `401 missing_capability` material | La API key funciona, pero este consumidor no puede usar materiales; no regeneres la key. |
| Material `403` | La identidad no posee ese acceso; no regeneres la key ni amplíes el scope. |
| `Deserialize error … JsonRpcMessage` | Codex inició el MCP sin token; revisa la variable y el registro MCP. |

## Seguridad

Nunca pegues la key o contraseña en el chat ni las subas a un repositorio. El script
no imprime la API key; la persiste localmente para ambos clientes. Si el archivo de
settings existente es inválido, debe detenerse sin sobrescribirlo.
