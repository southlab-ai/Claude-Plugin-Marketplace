---
name: crear-evaluacion
description: Crear evaluaciones originales alineadas a OA con el KG Educación v3. Resuelve el target, consulta materiales autorizados si aplican, obtiene un framework firmado, compila una spec, genera los ítems y valida el resultado.
---

# Crear evaluaciones v3

Usa el MCP `kg-educacion` (`serverInfo` `3.0.0`). Es un KG privado e independiente con sourcing
trazable; no está afiliado a MINEDUC. El KG no genera preguntas: resuelve, recupera, compila y valida.
Tú generas ítems originales y mantienes separadas la vista de estudiante y la pauta docente.

## Flujo obligatorio

1. **Alcance**: confirma asignatura, curso, propósito, cantidad de ítems y OA/tema/unidad. Si la
   evaluación se basa en un libro, conserva su `package_id` activo.
2. **Target**: llama `resolve_curricular_targets`. Usa los OA explícitos de la solicitud o del material
   elegido. Si devuelve alternativas, pide aclaración; no elijas silenciosamente.
3. **Evidencia curricular**: usa `query_curriculum` sobre el target resuelto para OA, indicadores y
   demanda pedagógica citada.
4. **Materiales**: si aplica, usa `query_teaching_materials` con los OA resueltos y `selectors.oa_codes`.
   Restringe por `package_id` o `package_ids` solo si ya están activos; sin paquete, recupera ampliamente
   y filtra conservando procedencia. Para OA explícitos usa `limit: 200`, copia `paging.next_cursor` en
   `cursor` hasta que `paging.next_cursor` sea `null` y conserva los `resource_refs`.
5. **Framework**: para una evaluación diagnóstica, formativa, sumativa o de práctica que requiera marco,
   llama `analyze_assessment_framework` y conserva el `framework_ref` firmado. Distingue distribución
   declarada por fuente de distribución modelada u observada.
6. **Compilar**: llama `compile_artifact` con `target_set_ref`, `framework_ref` cuando aplique,
   `resource_refs` y `constraints.item_count`. Usa un `artifact_type` canónico:
   `diagnostic_assessment`, `formative_assessment`, `summative_assessment` o `item_set`.
7. **Generar**: redacta tú los estímulos, ítems, rúbricas y pauta siguiendo `compiled_spec` y el packet.
8. **Validar**: llama `validate_artifact` copiando sin cambios todos los ids, hash, firma, algoritmo,
   key id, encoding, release, tipo y propósito emitidos por `compile_artifact`.

## Materiales y varios paquetes

- `package_id` identifica el libro/bundle; `material_id` identifica una sección concreta.
- Usa `package_id` o `package_ids` solo para un libro o bundle ya activo. Sin paquete, usa asignatura,
  curso y `selectors.oa_codes` para recuperar ampliamente y filtrar conservando origen.
- Puedes combinar materiales de varios paquetes, manteniendo citas y `resource_refs` atribuidos. El
  target se fija con `resolve_curricular_targets`, no por una mezcla implícita de metadata.
- `material_unit_kind` es opcional y no se infiere desde la palabra "unidad"; omitido, admite unidad,
  lección, capítulo y sección equivalentes.
- `material_unit_number` es estructura interna del material; no lo copies a `selectors.unit_number`.

## Límite y paginación

En `query_curriculum` y `query_teaching_materials`, `limit` acepta de 1 a 200. Para una consulta acotada
usa el menor valor suficiente y detente con evidencia suficiente. Para OA explícitos o completitud
exhaustiva usa `limit: 200` y copia `paging.next_cursor` en `cursor` hasta que `paging.next_cursor` sea
`null`. Nunca uses ni esperes `has_more`.

## Reglas duras

- Los ítems fuente son evidencia interna y nunca se entregan ni se adaptan como ítems finales.
- Genera al menos un ítem y exactamente `constraints.item_count` cuando se haya compilado esa restricción.
- Cada ítem lleva `target_oa`, `slot_id`, tipo de respuesta y estímulo; la pauta generada vive solo en
  `teacher_view.generated_answer_key`.
- `student_view` nunca contiene claves, respuestas esperadas ni notas docentes.
- Si la validación falla, corrige el payload y revalida contra la misma spec; no cambies el target ni la
  firma para hacerla pasar.
- Todo requiere revisión humana antes de uso en aula.
- Si el MCP responde 401, usa `setup`.
