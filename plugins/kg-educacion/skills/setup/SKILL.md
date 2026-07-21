---
name: setup
description: Asistente de configuración de kg-educacion v3, un KG educativo privado e independiente con sourcing MINEDUC. Conecta el MCP en Claude Code o Codex, registra la cuenta y configura una API key para ambos clientes. Úsala la primera vez o ante un 401.
---

# Asistente de configuración de kg-educacion

`kg-educacion` es un KG privado, independiente y no afiliado a MINEDUC. Conecta al runtime
`serverInfo 3.0.0`; la autoridad de los datos corresponde a las fuentes citadas.

El acceso es por invitación y de pago por consulta. La **API key es la misma para Claude y Codex**.
Tu trabajo es **guiar al usuario paso a paso** hasta dejar el plugin conectado.

## Primero distingue el caso
- **Ya tiene `KG_API_KEY`** (o dice que ya lo configuró en el otro cliente): NO registres otra cuenta.
  Salta directo a "Configurar el cliente que falta" usando la key existente.
- **Primera instalación / sin key**: sigue el "Flujo de registro".

## Flujo de registro (pregunta uno por uno, no todo junto)
1. **Código de invitación**: "¿Cuál es tu código de invitación? (formato `kg-inv-…`; si no tienes,
   pídelo a hola@southlab.ai)". No sigas sin un código.
2. **Email**: "¿Tu email de contacto?".
3. **Username**: "¿Qué nombre de usuario quieres? (3-64 caracteres, letras/números . _ - @)".
4. **Contraseña**: "¿Quieres elegir una contraseña o que la genere por ti?" — si la genera, el script
   la muestra una vez para que la guarde (sirve para gestionar/revocar tus keys más adelante).

## Ejecutar el registro + configuración
Con los datos, corre el script de onboarding. Registra, crea la API key y configura **ambos clientes**:
`~/.claude/settings.json` (Claude), `export KG_API_KEY` en el shell, `codex mcp add` (Codex) y
`launchctl setenv` para las apps GUI de macOS.
```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh" "<invite_code>" "<email>" "<username>" "<password opcional>"
```
- Si el usuario eligió contraseña, pásala como 4º argumento; si no, omítela y el script genera una.
- Pasa los argumentos entre comillas.

## Configurar el cliente que falta (si ya hay key)
La key (`KG_API_KEY`) es la misma. Por cliente:
- **Claude Code**: el `.mcp.json` del plugin lee `Bearer ${KG_API_KEY}`. Exporta `KG_API_KEY` en el
  shell (o pon `env.KG_API_KEY` en `~/.claude/settings.json`) y reinicia Claude.
- **Codex**: `codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var KG_API_KEY`
  con `KG_API_KEY` exportada. El manifiesto del plugin **no** transporta la auth; va en `config.toml`.
- **macOS (apps GUI)**: si abren Codex/Claude desde el Dock, expón la key con
  `launchctl setenv KG_API_KEY "$KG_API_KEY"` (y, para que sobreviva reinicios, un LaunchAgent que lo haga al login).

## Después de correrlo
- El script confirma "✅ Cuenta creada y API key configurada". **Dile que reinicie Claude Code o Codex**.
- Recuérdale guardar la contraseña (si fue generada) y su API key.
- Tras reiniciar, que consulte `runtime_status` y luego pruebe: "¿qué OA tiene Lenguaje 4° básico?".
  Si el runtime reporta `serverInfo 3.0.0` y la consulta responde con citas, quedó listo.

## Errores
- 403 en el registro = código de invitación inválido o ya usado → pide uno nuevo.
- 401 al consultar luego = la key no llegó al cliente → confirma que reinició; en Codex revisa
  `codex mcp get kg-educacion`; en apps GUI de macOS revisa `launchctl getenv KG_API_KEY`.
- En Codex, el error `Deserialize error … JsonRpcMessage` al iniciar significa que el MCP arrancó
  **sin** token (401 del servidor): falta `KG_API_KEY` en el entorno o falta el `codex mcp add`.

## Seguridad
- La API key se guarda en el equipo del usuario (settings de Claude, shell, config.toml de Codex).
  Nunca la pegues en el chat ni la subas a repos. La contraseña del usuario no se guarda en archivos del proyecto.
