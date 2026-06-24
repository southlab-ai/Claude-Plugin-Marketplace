---
name: kg-overview
description: Qué es el Knowledge Layer del Currículum Nacional de Chile y cómo usar sus 7 herramientas MCP v2 (runtime_status, query_curriculum, resolve_curricular_targets, analyze_assessment_framework, compile_artifact, validate_artifact, explain_artifact). Lee esto primero cuando el usuario pregunte por currículum, OA, planificación, evaluaciones o recursos chilenos.
---

# Knowledge Layer del Currículum Nacional de Chile

Tienes acceso, vía el MCP `kg-educacion` (runtime v2, serverInfo 2.0.0, modo PROMPT_ONLY), a un grafo de
conocimiento construido sobre las fuentes oficiales del Currículum Nacional (curriculumnacional.cl,
MINEDUC). Sirve para apoyar a profesores y equipos directivos. **Todo es de solo lectura y siempre citas
la fuente.**

**Cambio de paradigma clave:** el KG ya **no genera contenido ni aloja un LLM**. El KG **compila evidencia
oficial citada + una spec (PromptPacket)**; el modelo que llama (tú, Claude) **genera el artefacto**; luego
el KG **valida** lo que generaste. En resumen: *el KG entrega evidencia+spec, tú generas, luego validas.*
La vista de estudiante **no lleva clave**, y todo requiere **revisión humana** antes de usarse en aula.

## Qué contiene (capas)
- **OA oficiales** por curso, asignatura y eje, con sus recursos y clases asociadas.
- **Habilidades transversales** que cruzan asignaturas (argumentar, investigar, modelar, colaborar…).
- **Secuencias** de unidades y clases con **horas pedagógicas** (pacing del año).
- **Recursos** catalogados por curso/asignatura/categoría/formato (lecturas, videos, actividades…).
- **Demanda cognitiva** (Bloom y DOK) de OA e ítems, para balancear evaluaciones.
- **Progresiones** entre grados (qué OA se apoya en el del nivel anterior).
- **Marcos evaluativos oficiales** (SIMCE/PAES/DEMRE) por familia exacta, con su distribución oficial.

## Las 7 herramientas v2 y cuándo usarlas
| Herramienta | Úsala para |
|---|---|
| `runtime_status` | **Úsala primero**: estado del servidor + cobertura curricular por solicitud (qué hay disponible, horas, alcance). |
| `query_curriculum` | Recuperación curricular oficial **con cita por resultado**: un OA por código/tema, recursos de un curso, horas de una unidad, y también consultas **temáticas/panorama** ("qué temas cruzan el currículum"). Nunca devuelve ítems fuente ni claves. |
| `resolve_curricular_targets` | Resolver (asignatura, curso, OA explícitos / programa / unidad) a un **set de OA objetivo**. Si es ambiguo (p.ej. dos programas para la misma asignatura+curso), **pide aclaración**. |
| `analyze_assessment_framework` | **Marco evaluativo oficial** (SIMCE/PAES/DEMRE) por familia EXACTA; distingue **distribución oficial vs. observada** (nunca presentes lo observado como oficial). |
| `compile_artifact` | **PROMPT_ONLY**: compila evidencia + decisión pedagógica + spec y devuelve un **PromptPacket** para que **tú generes** el artefacto (clase, actividad, evaluación, planificación anual/unidad, rúbrica, retroalimentación…). El KG **no genera**. |
| `validate_artifact` | **Valida** el artefacto que generaste: conformidad de blueprint, **ausencia de clave en la vista de estudiante**, no-reuso de ítems fuente. **Nada es entregable sin pasar la validación.** |
| `explain_artifact` | Explica el **contrato** de un tipo de artefacto: secciones requeridas y gates de validación. |

## Flujos típicos (de intención a herramientas)
- **Buscar recursos / responder dudas:** `query_curriculum` (+ `runtime_status` para cobertura).
- **Crear evaluación / ítems / kit:** `resolve_curricular_targets` → `analyze_assessment_framework` (marco)
  → `compile_artifact` (`artifact_type` `formative_assessment` | `summative_assessment`) → **generas los ítems**
  → `validate_artifact`. El banco de ítems fuente es **auditoría local** y **nunca** se expone por el MCP remoto.
- **Planificar año/unidad/clase:** `resolve_curricular_targets` → `compile_artifact` (`artifact_type`
  `annual_plan` | `unit` | `class`) → **generas** → `validate_artifact`; cobertura/horas vía `runtime_status`.
- **Temas transversales / panorama interdisciplinario:** `query_curriculum` con consultas temáticas.

## Reglas
- Cita siempre la fuente oficial que devuelve la herramienta.
- Si no hay evidencia, dilo explícitamente — no inventes OA ni códigos.
- Recuerda el paradigma PROMPT_ONLY: el KG entrega **evidencia+spec**, **tú generas**, luego **validas**;
  nada es entregable sin pasar `validate_artifact`.
- Para tareas de planificación, evaluación, recursos o proyectos interdisciplinarios, usa las skills
  específicas de este plugin (`planificar`, `crear-evaluacion`, `buscar-recursos`, `temas-transversales`).
- Si el MCP responde 401, falta configurar `KG_API_KEY`: usa la skill `setup`.
