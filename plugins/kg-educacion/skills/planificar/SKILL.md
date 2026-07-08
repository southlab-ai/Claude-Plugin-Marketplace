---
name: planificar
description: Planificar el año, una unidad, una semana o una clase del Currículum Nacional de Chile usando OA oficiales, secuencias de unidades/clases y horas pedagógicas. El KG entrega evidencia citada + spec (compile_artifact), tú generas la planificación y luego la validas (validate_artifact). Úsala cuando el usuario pida planificar, calendarizar o secuenciar enseñanza.
---

# Planificación curricular (año → unidad → clase)

Apoya al profesor a planificar usando el MCP `kg-educacion` (runtime v2, `serverInfo` 2.0.0,
modo PROMPT_ONLY). **Cambio de paradigma:** el KG ya **no** genera contenido ni aloja un LLM.
El KG **compila evidencia oficial citada + una spec/PromptPacket**; **tú (Claude) generas** la
planificación; **luego se valida**. Todo es read-only y citado, la vista de estudiante va sin
clave, y todo requiere revisión humana del docente.

La planificación baja en cascada: **año → mes → semana → día**, y el KG tiene la evidencia
oficial para cada nivel.

## Flujo recomendado
1. **Encuadre**: confirma curso y asignatura (ej. "Lenguaje 4° básico"). Si falta, pregúntalo.
   Usa `runtime_status` primero para ver el estado del servidor y la **cobertura curricular**
   de tu solicitud (incluye horas/pacing disponibles).
2. **OA objetivo**: `query_curriculum` para recuperar y fijar los OA objetivo **con cita** (por código,
   tema, unidad o secuencia). Si el pedido es amplio, elige los OA razonables y declara el alcance
   antes de seguir.
3. **Spec + evidencia**: `compile_artifact` con `artifact_type` `annual_plan` (año), `unit`
   (unidad) o `class` (clase), pasándole `requested_oa_codes` = los OA que recuperaste (es *stateless*).
   Devuelve un **PromptPacket**: evidencia oficial citada (OA, secuencia unidad→unidad y clase→clase,
   horas pedagógicas, % del año) + la decisión pedagógica + la spec.
4. **Generas tú**: a partir del PromptPacket, **redacta la planificación**. El KG no la genera por ti.
5. **Validación**: `validate_artifact` sobre lo que generaste — conformidad de blueprint y los gates
   correspondientes. Nada es entregable sin pasar la validación.
6. **Cierre**: arma la planificación citando los OA y las horas oficiales. Si el colegio tiene menos
   semanas, redistribuye proporcionalmente y dilo (cobertura/horas vía `runtime_status`).

> ¿Necesitas entender qué secciones y gates exige un tipo de plan? Usa `explain_artifact` para ver el
> contrato (`annual_plan` / `unit` / `class`) antes de compilar.

## Buenas prácticas
- Para **nivelar** al inicio del año, usa `resolve_curricular_targets` con los OA del curso: devuelve `prerequisite_oa` (qué OA del grado anterior sostiene cada uno) con citas — úsalo para secuenciar y detectar prerrequisitos.
- Usa los **códigos OA reales** que devuelve el KG vía `query_curriculum`
  (ej. `LE04 OA 04`), nunca inventados.
- Para recuperación curricular puntual (un OA, un recurso, horas de una unidad, panorama temático),
  usa `query_curriculum`: retrieval oficial **con cita por resultado**. Nunca devuelve ítems fuente
  ni claves.
- Para integrar varias asignaturas en una unidad, combina con la skill `temas-transversales`
  (consultas temáticas vía `query_curriculum`).
- Si el usuario pide nivelar al inicio del año, consulta las **progresiones** con `query_curriculum`
  ("progresión …") para saber qué OA del grado anterior se apoyan en los del actual.
- Cita siempre la fuente. Si no hay evidencia para algo, dilo; nunca inventes OA ni códigos.
- Si el MCP responde **401**, deriva a la skill `setup` para configurar el acceso.
