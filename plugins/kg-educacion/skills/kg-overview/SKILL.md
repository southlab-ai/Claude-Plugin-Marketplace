---
name: kg-overview
description: Qué es el Knowledge Layer del Currículum Nacional de Chile y cómo usar sus herramientas MCP v2 (runtime_status, query_curriculum, query_resources, analyze_assessment_framework, compile_artifact, validate_artifact, explain_artifact). Lee esto primero cuando el usuario pregunte por currículum, OA, planificación, evaluaciones o recursos chilenos.
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
- **Marcos evaluativos** (SIMCE, PAES) por familia + asignatura + grado, con ejes, habilidades y
  **distribución modelada** a partir de lo observado. La distribución oficial de SIMCE no es pública, así
  que se representa como `modeled`/`observed`, nunca como oficial.

## Las herramientas v2 y cuándo usarlas
| Herramienta | Úsala para |
|---|---|
| `runtime_status` | **Úsala primero**: estado del servidor + cobertura curricular por solicitud (qué hay disponible, horas, alcance). |
| `query_curriculum` | Recuperación curricular oficial **con cita por resultado**: un OA por código/tema, horas de una unidad, progresiones, y también consultas **temáticas/panorama** ("qué temas cruzan el currículum"). Aquí recuperas y fijas los OA objetivo. Nunca devuelve ítems fuente ni claves. |
| `query_resources` | Catálogo de **recursos y textos escolares oficiales (MINEDUC)** por curso/asignatura/categoría, con `source_url`. Úsala cuando pidan libros, textos del curso o material asociado. |
| `analyze_assessment_framework` | **Marco evaluativo** por `family` (SIMCE/PAES) + `subject` + `grade`. Devuelve ejes, habilidades, `formats` y `target_distribution` **modelada** (con `official_distribution` vacío: la oficial de SIMCE no es pública). Selecciona por grado (Mat 4° y 8° difieren). Úsala en evaluaciones estandarizadas para **balancear**; declara la distribución como modelada, no oficial. |
| `compile_artifact` | **PROMPT_ONLY**: compila evidencia + decisión pedagógica + spec y devuelve un **PromptPacket** para que **tú generes** el artefacto (clase, actividad, evaluación, planificación anual/unidad, rúbrica, retroalimentación…). Es **stateless**: pásale `requested_oa_codes` (los OA que recuperaste). El KG **no genera**. |
| `validate_artifact` | **Valida** el artefacto que generaste: conformidad de blueprint, **ausencia de clave en la vista de estudiante**, no-reuso de ítems fuente. **Nada es entregable sin pasar la validación.** |
| `explain_artifact` | Explica el **contrato** de un tipo de artefacto: secciones requeridas y gates de validación. |

## Cómo se encadenan (orquestación)
Las herramientas **no se llaman entre sí** — **tú** eres quien las encadena. `compile_artifact` es
*stateless*: recuperas los OA con `query_curriculum`, y esos códigos se los pasas como `requested_oa_codes`
a `compile_artifact`; después lo que **tú generas** se lo pasas a `validate_artifact`. El dato viaja por ti,
no por el servidor.

## Flujos típicos (de intención a herramientas)
- **Buscar recursos / responder dudas:** `query_curriculum` para OA/evidencia y `query_resources` para
  textos oficiales (+ `runtime_status` para cobertura).
- **Crear evaluación / ítems / kit:** `query_curriculum` (recupera y fija los OA con cita)
  → si es estandarizada, `analyze_assessment_framework` (`family` SIMCE/PAES + `subject` + `grade`) para el
  blueprint y su `target_distribution` → `compile_artifact` (`artifact_type` `formative_assessment` |
  `summative_assessment`, con esos `requested_oa_codes`) → **generas los ítems** balanceando a la
  distribución → `validate_artifact`. La `target_distribution` es **modelada** (la oficial de SIMCE no es
  pública): balancea a ella pero decláralo como modelado, no como distribución oficial. Genera ítems
  originales; el banco de ítems fuente es **auditoría local** y **nunca** se expone por el MCP remoto.
- **Planificar año/unidad/clase:** `query_curriculum` (recupera OA, secuencia y horas) → `compile_artifact`
  (`artifact_type` `annual_plan` | `unit` | `class`, con `requested_oa_codes`) → **generas** →
  `validate_artifact`; cobertura/horas vía `runtime_status`.
- **Temas transversales / panorama interdisciplinario:** `query_curriculum` con consultas temáticas.

## Reglas
- Cita siempre la fuente oficial que devuelve la herramienta.
- Si no hay evidencia, dilo explícitamente — no inventes OA ni códigos.
- Recuerda el paradigma PROMPT_ONLY: el KG entrega **evidencia+spec**, **tú generas**, luego **validas**;
  nada es entregable sin pasar `validate_artifact`.
- Para tareas de planificación, evaluación, recursos o proyectos interdisciplinarios, usa las skills
  específicas de este plugin (`planificar`, `crear-evaluacion`, `buscar-recursos`, `temas-transversales`).
- Si el MCP responde 401, falta configurar `KG_API_KEY`: usa la skill `setup`.
