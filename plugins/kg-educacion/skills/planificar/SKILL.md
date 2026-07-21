---
name: planificar
description: Planificar año, unidad, semana o clase con el KG Educación v3. Resuelve OA canónicos, recupera evidencia y materiales docentes por package_id, compila una spec, genera la planificación y la valida. Úsala al planificar, calendarizar o secuenciar enseñanza.
---

# Planificación curricular v3

Usa el MCP `kg-educacion` (`serverInfo` `3.0.0`). Es un KG privado e independiente con sourcing en
materiales publicados o distribuidos por MINEDUC; la autoridad pertenece a la fuente citada, no al KG.
El KG resuelve, recupera y compila. Tú generas la planificación y luego la validas.

## Encuadre

Confirma asignatura, curso, alcance y restricciones. Usa `runtime_status` solo si necesitas conocer
release, cobertura o paridad. No lo uses como respuesta curricular.

Distingue estas dos intenciones:

1. **Por currículum/OA**: el docente pide un OA, tema o unidad curricular del programa.
2. **Por libro/material**: el docente pide "la Unidad 1", "la Lección 3" o una sección del libro que
   está usando. El contexto de conversación puede mantener ese libro activo por `package_id`.

## Planificar por currículum u OA

1. `resolve_curricular_targets` con asignatura, curso y OA/tema/unidad curricular. Para varios OA del
   mismo programa, envíalos juntos en `selectors.oa_codes`. Si hay ambigüedad, pregunta.
2. `query_curriculum` con el target para OA, indicadores, horas, progresiones y evidencia pedagógica.
3. `query_teaching_materials` con los OA resueltos y `selectors.oa_codes`. Usa `package_id` o
   `package_ids` solo si el libro ya está activo; si no, recupera ampliamente y filtra con procedencia.
   Para OA explícitos usa `limit: 200` y copia `paging.next_cursor` en `cursor` hasta que
   `paging.next_cursor` sea `null`.
4. `compile_artifact` con el `target_set_ref` completo, `resource_refs` relevantes y restricciones.
5. Genera la planificación desde el packet y valida con `validate_artifact`.

## Planificar por unidad, lección o sección del material

1. Si el libro está activo en la conversación, llama `query_teaching_materials` con su `package_id` y
   `material_unit_number` o `material_unit_name`. Si el docente dice "Unidad 1", usa
   `material_unit_number: 1`. No infieras `material_unit_kind` desde la palabra "unidad"; es un filtro
   opcional. Si se omite, recupera unidades, lecciones, capítulos y secciones equivalentes y sigue.
2. Si no hay libro activo, recupera ampliamente por asignatura, curso y número. El modelo filtra o
   combina la evidencia preservando procedencia; no inventes `package_id` para acotar.
3. Conserva la procedencia por `package_id` y extrae los OA atribuidos a las estructuras recuperadas.
   Dentro del mismo paquete, unidad, lección, capítulo o sección pueden combinarse si evidencian el mismo
   alcance conceptual.
4. Resuelve esos OA con `resolve_curricular_targets`. `material_unit_number` **no** se copia a
   `selectors.unit_number`: uno es estructura del libro y el otro es unidad curricular.
5. Recupera evidencia curricular de los OA resueltos con `query_curriculum`.
6. Compila con `target_set_ref`, los `resource_refs` de la estructura elegida y las restricciones.

Para "estructúralo en 5 clases", usa:

```json
{
  "artifact_type": "unit",
  "purpose": "plan",
  "planning_granularity": "unit",
  "target_set_ref": "<copiar objeto firmado completo>",
  "resource_refs": ["<refs de query_teaching_materials>"],
  "constraints": {"class_count": 5}
}
```

Cada elemento de `artifact_payload.periods` representa una clase; deben existir exactamente cinco.

## Varios libros

- Un paquete activo restringe. Sin paquete activo, recupera ampliamente con asignatura, curso y
  `selectors.oa_codes` cuando los OA sean conocidos.
- Puedes combinar evidencia de varios paquetes, manteniendo sus citas y `resource_refs` atribuidos.
- El target se determina con `resolve_curricular_targets`; aclara solo si los OA apuntan a identidades
  curriculares incompatibles.
- No reemplaces `package_id` por `material_id`: el primero identifica el libro/bundle; el segundo una sección.

## Límite y paginación

En `query_curriculum` y `query_teaching_materials`, `limit` acepta de 1 a 200. Para una consulta acotada
usa el menor valor suficiente y detente con evidencia suficiente. Para OA explícitos o completitud
exhaustiva usa `limit: 200` y copia `paging.next_cursor` en `cursor` hasta que `paging.next_cursor` sea
`null`. Nunca uses ni esperes `has_more`.

## Generación y validación

Genera tú el artefacto respetando OA, duración, número de clases, citas y `resource_refs` del packet.
Para validar, copia sin modificar todos los ids, hash, firma, algoritmo, key id, encoding, release,
`artifact_type` y `purpose` de `compile_artifact`. Nada se entrega si `validate_artifact` falla.

## Reglas

- Cita las fuentes y etiqueta correctamente autoridad declarada, modelado o síntesis.
- Nunca inventes OA ni completes huecos de cobertura en silencio.
- Todo artefacto requiere revisión del docente.
- Si el MCP responde 401, usa `setup`.
