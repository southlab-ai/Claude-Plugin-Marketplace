---
name: setup
description: Asistente de configuración de kg-educacion — guía al usuario para conectar el MCP del Currículum Nacional. Pide código de invitación, email y username, registra la cuenta, genera la API key y la deja configurada sola. Úsala la primera vez, cuando el usuario diga "configurar/conectar/setup", o si el MCP responde 401.
---

# Asistente de configuración de kg-educacion

El acceso es por invitación y de pago por consulta. Tu trabajo es **guiar al usuario paso a paso**
hasta dejar el plugin conectado. NO empieces diagnosticando errores: corre el asistente.

## Flujo (pregunta uno por uno, no todo junto)
1. **Código de invitación**: "¿Cuál es tu código de invitación? (formato `kg-inv-…`; si no tienes,
   pídelo a hola@southlab.ai)". No sigas sin un código.
2. **Email**: "¿Tu email de contacto?".
3. **Username**: "¿Qué nombre de usuario quieres? (3-64 caracteres, letras/números . _ - @)".
4. **Contraseña**: "¿Quieres elegir una contraseña o que la genere por ti?" — si la genera, el script
   la muestra una vez para que la guarde (sirve para gestionar/revocar tus keys más adelante).

## Ejecutar el registro + configuración
Con los datos, corre el script de onboarding (registra, crea la API key y la deja configurada
automáticamente en `~/.claude/settings.json` y en el shell):
```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/kg-onboard.sh" "<invite_code>" "<email>" "<username>" "<password opcional>"
```
- Si el usuario eligió contraseña, pásala como 4º argumento; si no, omítela y el script genera una.
- Pasa los argumentos entre comillas.

## Después de correrlo
- El script confirma "✅ Cuenta creada y API key configurada". **Dile al usuario que reinicie
  Claude Code o Codex** para que tome la conexión.
- Recuérdale guardar la contraseña (si fue generada) y su API key.
- Tras reiniciar, que pruebe: "¿qué OA tiene Lenguaje 4° básico?". Si responde con citas, quedó listo.

## Errores
- 403 en el registro = código de invitación inválido o ya usado → pide uno nuevo.
- 401 al consultar luego = la API key no se cargó → confirma que reinició el cliente, o vuelve a correr el script.

## Seguridad
- La API key se guarda en el equipo del usuario (settings de Claude + shell). Nunca la pegues en el chat
  ni la subas a repos. La contraseña del usuario no se guarda en ningún archivo del proyecto.
