---
description: Configura el acceso a kg-educacion (cuenta + API key + KG_API_KEY)
---

Guía al usuario para dejar operativo el MCP `kg-educacion` siguiendo la skill `setup`:

1. Pregúntale si ya tiene cuenta en api.southlab.ai y su **código de invitación** (el acceso es por invitación). Si no, ayúdalo a registrarse
   (`POST https://api.southlab.ai/account/register` con usuario, contraseña e `invite_code`).
2. Crea una API key (`POST https://api.southlab.ai/account/keys`). La key `kg_live_…` se muestra una sola vez.
3. Indícale exportar `KG_API_KEY` en su shell y reiniciar el cliente.
4. Verifica preguntando algo curricular; si responde con citas, quedó conectado.

Nunca muestres ni guardes la contraseña del usuario en archivos. La API key va solo en la variable de entorno.
