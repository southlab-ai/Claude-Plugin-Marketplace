# kg-educacion

Knowledge layer del **Currículum Nacional de Chile** (MINEDUC) para Claude Code y Codex.
Conecta el modelo a un MCP remoto **read-only** que compila **evidencia oficial citada** y una
**spec/PromptPacket** para que **tú (el modelo) generes** el artefacto; luego se **valida**. El KG
**ya no genera contenido ni aloja un LLM**: entrega evidencia + spec, tú produces, después validas.

- **Planificación** de año / unidad / clase con OA, secuencias y horas pedagógicas.
- **Evaluaciones** alineadas a OA y balanceadas por demanda cognitiva (Bloom / DOK).
- **Recursos** y dudas curriculares resueltos con cita oficial por resultado.
- **Temas transversales** y proyectos interdisciplinarios (consultas temáticas de panorama).

Es de **solo lectura** y **cita siempre la fuente**. La vista de estudiante va **sin clave**, el
banco de ítems fuente nunca se expone, y **todo artefacto requiere revisión humana**. El servicio
es de pago por consulta: cada usuario crea su cuenta y genera **API keys** revocables.

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
Si el MCP responde **401**, corre la skill `setup` (o `/kg-setup`).

## Skills incluidas
`kg-overview` (qué es y cómo usarlo), `planificar`, `crear-evaluacion`, `buscar-recursos`,
`temas-transversales`, `setup`.

## Herramientas MCP — Runtime v2 (read-only, `serverInfo` 2.0.0, modo `PROMPT_ONLY`)
La superficie pública del MCP son **7 tools** (cualquier nombre anterior es **obsoleto**):

- **`runtime_status`** — estado del servidor + cobertura curricular por solicitud. **Úsalo primero.**
- **`query_curriculum`** — recuperación curricular oficial **con cita por resultado**. Nunca devuelve
  ítems fuente ni claves. (Reemplaza a toda búsqueda/respuesta/fetch/grafo/listado anterior.)
- **`resolve_curricular_targets`** — resuelve (asignatura, curso, OA explícitos / programa / unidad)
  a un set de **OA objetivo**; si es ambiguo (p. ej. dos programas para la misma asignatura+curso),
  **pide aclaración**.
- **`analyze_assessment_framework`** — marco evaluativo oficial (SIMCE/PAES/DEMRE) por **familia
  exacta**; distingue **distribución oficial vs observada** (nunca presenta lo observado como oficial).
- **`compile_artifact`** — `PROMPT_ONLY`: compila evidencia + decisión pedagógica + spec y devuelve un
  **PromptPacket** para que **tú generes** el artefacto (clase, actividad, evaluación, planificación
  anual/unidad, rúbrica, retroalimentación, etc.). **El KG no genera.**
- **`validate_artifact`** — valida el artefacto que generaste: conformidad de blueprint, **ausencia de
  clave** en la vista de estudiante, **no-reuso** de ítems fuente. Nada es entregable sin pasar la validación.
- **`explain_artifact`** — explica el contrato de un tipo de artefacto (secciones requeridas, gates).

El servidor expone un onboarding completo en `initialize` (`instructions`) para que el modelo sepa
qué puede hacer apenas se conecta.

## Flujos por intención
- **Buscar recursos / responder dudas:** `query_curriculum` (+ `runtime_status` para cobertura).
- **Crear evaluación / ítems / kit:** `resolve_curricular_targets` → `analyze_assessment_framework`
  (marco) → `compile_artifact` (`artifact_type` `formative_assessment` | `summative_assessment`) →
  **tú generas los ítems** → `validate_artifact`. El banco de ítems fuente es **auditoría local** y
  **nunca** se expone por el MCP remoto.
- **Planificar año / unidad / clase:** `resolve_curricular_targets` → `compile_artifact`
  (`artifact_type` `annual_plan` | `unit` | `class`) → **tú generas** → `validate_artifact`;
  cobertura/horas vía `runtime_status`.
- **Temas transversales / panorama interdisciplinario:** `query_curriculum` con consultas temáticas.

Regla general: **cita siempre la fuente**; si no hay evidencia, **dilo**; nunca inventes OA ni códigos.

---
SouthLab AI · datos de origen público (curriculumnacional.cl) modelados en un grafo de conocimiento.
