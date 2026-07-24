---
name: kg-overview
description: Qué es KG Educación y cómo usar sus cinco tools V3 para recuperar currículum, OA, materiales y marcos de evaluación.
---

# KG Educación V3

El MCP `kg-educacion` es un KG privado, independiente y no afiliado a MINEDUC.
Recupera evidencia y contexto; tú completas la tarea solicitada por el usuario.

## Tools

| Tool | Uso inequívoco |
|---|---|
| `runtime_status` | Estado del release, cobertura y paridad. |
| `query_curriculum` | OA, indicadores, programas, unidades, horas y progresiones. |
| `query_teaching_materials` | Textos, guías, actividades y recursos docentes. |
| `resolve_curricular_targets` | Normaliza curso, asignatura, OA, programa o unidad. |
| `analyze_assessment_framework` | Recupera criterios y marcos para evaluaciones. |

## Flujo

1. Resuelve el target si la identidad curricular no es inequívoca.
2. Recupera evidencia curricular.
3. Recupera materiales si la tarea se beneficia de textos o recursos.
4. Recupera un marco cuando la tarea sea evaluativa.
5. Sintetiza el artefacto solicitado conservando citas y procedencia.

No llames tools inexistentes de compilación o validación. No conviertas el KG en una
política de comportamiento del modelo.

## Reglas de retrieval

- Unidad curricular y estructura interna del libro son conceptos distintos.
- Usa `package_id` solo para un libro activo o elegido.
- Para completitud, pagina copiando `paging.next_cursor` hasta `null`.
- No inventes OA, ids, citas, hashes ni contenido ausente.
- Expresa el resultado útil; evita convertir limitaciones internas en el centro de la
  respuesta.
