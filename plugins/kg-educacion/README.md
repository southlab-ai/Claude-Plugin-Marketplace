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
```bash
codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin install kg-educacion@southlab-marketplace
```
El plugin aporta las **skills**. El MCP autenticado se registra aparte en Codex (el manifiesto
del plugin **no** transporta credenciales — Codex solo aplica auth desde `config.toml`); ver
"Configurar el acceso".

## Configurar el acceso
La key (`KG_API_KEY`) es **la misma para Claude y Codex**. Crea cuenta y key una vez:
1. Cuenta (requiere **código de invitación**, pídelo a hola@southlab.ai): `POST https://api.southlab.ai/account/register` `{username,password,invite_code}`.
2. API key: `POST https://api.southlab.ai/account/keys` `{username,password,label}` → `kg_live_…` (se muestra una vez).

La forma fácil es `/kg-setup` (o la skill `setup`), que hace lo anterior y configura ambos clientes. Manual:

**Claude Code** — el `.mcp.json` del plugin lee `Bearer ${KG_API_KEY}` del entorno:
```bash
export KG_API_KEY=kg_live_…          # en tu ~/.zshrc / ~/.bashrc
```
(o pon `"env": { "KG_API_KEY": "kg_live_…" }` en `~/.claude/settings.json`). Reinicia Claude.

**Codex** — registra el MCP con la key **por variable de entorno** (nunca el token literal en el repo):
```bash
export KG_API_KEY=kg_live_…
codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var KG_API_KEY
```
Reinicia Codex.

**macOS (apps GUI)** — si abres Codex/Claude desde el Dock no heredan `~/.zshrc`. Expón la key:
```bash
launchctl setenv KG_API_KEY "$KG_API_KEY"
```
Para que sobreviva reinicios del Mac, deja un LaunchAgent que haga ese `setenv` al iniciar sesión.

## Skills incluidas
`kg-overview` (qué es y cómo usarlo), `planificar`, `crear-evaluacion`, `buscar-recursos`,
`temas-transversales`, `setup`.

## Herramientas MCP (read-only)
`search`, `search_global`, `answer`, `entity_lookup`, `graph_neighbors`, `graph_path`,
`fetch`, `list_sources`. El servidor expone un onboarding completo en `initialize`
(`instructions`) para que el modelo sepa qué puede hacer apenas se conecta.

---
SouthLab AI · datos de origen público (curriculumnacional.cl) modelados en un grafo de conocimiento.
