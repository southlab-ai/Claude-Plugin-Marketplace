---
name: kg-overview
description: Qué es el KG Educación privado y cómo usar las 7 herramientas MCP v3 (runtime_status, query_curriculum, query_teaching_materials, resolve_curricular_targets, analyze_assessment_framework, compile_artifact y validate_artifact). Lee esto primero para consultas sobre currículum chileno, OA, materiales docentes, planificación o evaluación.
---

# KG Educación v3

Tienes acceso al MCP `kg-educacion` (`serverInfo` `3.0.0`). Es un **KG privado, independiente y no
afiliado a MINEDUC**. Su sourcing incluye fuentes públicas y materiales publicados o distribuidos por
MINEDUC, además de materiales privados autorizados para una cuenta. La autoridad corresponde a cada
fuente citada; nunca presentes al KG, sus tools o su catálogo como "oficial MINEDUC".

El corpus y el KG se consultan en modo read-only. Auth, uso y auditoría pueden registrar actividad.
El KG no aloja un LLM ni redacta artefactos: **resuelve y recupera evidencia → compila una spec y un
packet → el modelo genera → el KG valida**. Todo entregable requiere revisión humana.

## Las 7 tools v3

| Tool | Responsabilidad |
|---|---|
| `runtime_status` | Descubre release activo, capacidades, cobertura y paridad. No responde preguntas curriculares. |
| `query_curriculum` | Recupera evidencia curricular citada: OA, indicadores, programas, unidades curriculares, horas, progresiones y pedagogía. |
| `query_teaching_materials` | Recupera paquetes y componentes docentes: textos, guías, cuadernos, actividades, BDA y materiales privados autorizados. |
| `resolve_curricular_targets` | Convierte curso, asignatura, OA o texto libre en un `target_set_ref` canónico y explicita ambigüedades. |
| `analyze_assessment_framework` | Selecciona un framework evaluativo y devuelve un `framework_ref` firmado. |
| `compile_artifact` | Compila un target no ambiguo, materiales y restricciones en `compiled_spec` + `TeacherContextPacket`. No redacta. |
| `validate_artifact` | Valida el artefacto generado contra exactamente el packet y la spec firmada de `compile_artifact`. |

## Separar currículum de materiales

- `selectors.unit_id` / `selectors.unit_number` identifican una **unidad curricular canónica** del
  programa y se usan en `query_curriculum` o `resolve_curricular_targets`.
- `material_unit_number` / `material_unit_name` identifican una **estructura interna declarada por el
  material**: puede ser unidad, lección, capítulo o sección. Se usan solo en `query_teaching_materials`.
- `package_id` identifica el libro o bundle activo. `material_id` identifica una sección o material
  concreto; no lo uses como identidad del libro completo.
- Conserva en el contexto de conversación el `package_id` o los `package_ids` elegidos por el docente.

Cuando el docente diga "Unidad 1" y exista un libro activo en la conversación, interpreta la solicitud
como la estructura interna número 1 del material y usa `query_teaching_materials` con ese `package_id` y
`material_unit_number: 1`. `material_unit_kind` es un refinamiento opcional: no lo infieras desde la
palabra "unidad". Si se omite, admite unidad, lección, capítulo y sección equivalentes; di "estructura
interna 1" y continúa. Dentro del mismo paquete, unidad, lección, capítulo o sección pueden combinarse si
la evidencia muestra el mismo alcance conceptual.

Usa `package_id` o `package_ids` solo con un libro o bundle activo. Si no hay uno, recupera ampliamente
por asignatura, curso, `material_unit_number` cuando aplique y `selectors.oa_codes` cuando los OA estén
resueltos. Conserva la procedencia por `package_id` y deja que el modelo filtre o combine la evidencia.

## Retrieval amplio

- En `query_curriculum` y `query_teaching_materials`, `limit` acepta de 1 a 200. Usa el menor valor
  suficiente para una consulta acotada y termina con evidencia suficiente.
- Un OA explícito o una solicitud exhaustiva usa `limit: 200` y copia `paging.next_cursor` en `cursor`
  hasta que `paging.next_cursor` sea `null`, salvo que `package_id` o `package_ids` de paquetes ya
  activos restrinjan la búsqueda.
- Sin paquete activo, recupera ampliamente con asignatura, curso y `selectors.oa_codes`; no elijas un libro.
- La evidencia de varios paquetes puede combinarse. El target curricular sigue siendo canónico: resuelve
  los OA declarados y aclara solo si apuntan a programas o cursos incompatibles.
- Nunca uses ni esperes `has_more`; `paging.next_cursor` es la única señal de continuación.

## Flujo obligatorio para crear algo

1. Resuelve el target con `resolve_curricular_targets`. Si devuelve `needs_clarification`, pregunta; no
   elijas una alternativa por tu cuenta.
2. Recupera evidencia con `query_curriculum` usando el target resuelto.
3. Si aplica, recupera materiales con `query_teaching_materials`. Para un OA usa `package_id` o
   `package_ids` solo si ya están activos; si no, usa asignatura, curso y `selectors.oa_codes`, con
   `limit: 200` y la regla de `paging.next_cursor` anterior.
4. Llama `compile_artifact` con el `target_set_ref` completo, los `resource_refs` autorizados y las
   restricciones. Para una unidad de cinco clases usa `constraints.class_count: 5`.
5. Genera tú el artefacto siguiendo `compiled_spec` y `TeacherContextPacket`.
6. Llama `validate_artifact`, copiando sin cambios `context_packet_id`, `spec_id`, `spec_hash`, firma,
   algoritmo, key id, encoding, `release_id`, `artifact_type` y `purpose`. Corrige y revalida si falla.

## Reglas de respuesta

- Cita la fuente devuelta y distingue autoridad declarada, modelado y síntesis.
- No inventes OA, `package_id`, `resource_ref`, citas, hashes ni firmas.
- Los ítems fuente son evidencia interna, nunca entregables. Genera ítems originales y mantén la
  clave solo en `teacher_view`.
- Si el MCP responde 401, usa la skill `setup`.
