# kg-educacion

Knowledge layer del **Currículum Nacional de Chile** (MINEDUC) para Claude Code y Codex.
Conecta el modelo a un MCP remoto que resuelve, con citas oficiales:

- **Planificación** de año / unidad / clase con OA, secuencias y horas pedagógicas.
- **Evaluaciones** alineadas a OA y balanceadas por demanda cognitiva (Bloom / DOK).
- **Recursos** didácticos por OA, curso, asignatura y formato.
- **Temas transversales** y proyectos interdisciplinarios (comunidades temáticas GraphRAG).

Es de **solo lectura** y cita siempre la fuente. El servicio es de pago por consulta:
cada usuario crea su cuenta y genera **API keys** revocables.

## Instalación (Claude Code)
```bash
claude plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
claude plugin install kg-educacion@southlab-marketplace
```

## Instalación (Codex)
El plugin trae `.codex-plugin/`. Tras instalarlo, configura el MCP remoto en Codex
apuntando a `https://api.southlab.ai/mcp` con `Authorization: Bearer $KG_API_KEY`.

## Configurar el acceso
Ejecuta `/kg-setup` (o sigue la skill `setup`):
1. Crea cuenta (requiere **código de invitación**, pídelo a hola@southlab.ai): `POST https://api.southlab.ai/account/register` `{username,password,invite_code}`.
2. Crea API key: `POST https://api.southlab.ai/account/keys` `{username,password,label}` → `kg_live_…` (se muestra una vez).
3. Exporta `KG_API_KEY=kg_live_…` en tu shell y reinicia el cliente.

## Skills incluidas
`kg-overview` (qué es y cómo usarlo), `planificar`, `crear-evaluacion`, `buscar-recursos`,
`temas-transversales`, `setup`.

## Herramientas MCP (read-only)
`search`, `search_global`, `answer`, `entity_lookup`, `graph_neighbors`, `graph_path`,
`fetch`, `list_sources`. El servidor expone un onboarding completo en `initialize`
(`instructions`) para que el modelo sepa qué puede hacer apenas se conecta.

---
SouthLab AI · datos de origen público (curriculumnacional.cl) modelados en un grafo de conocimiento.
