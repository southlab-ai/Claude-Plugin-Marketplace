---
name: temas-transversales
description: Explorar conexiones curriculares y diseñar proyectos interdisciplinarios con el KG Educación v3. Recupera evidencia citada, resuelve un target por asignatura y compila un proyecto sin mezclar OA o materiales silenciosamente.
---

# Temas transversales y proyectos interdisciplinarios v3

Usa el MCP `kg-educacion` (`serverInfo` `3.0.0`). Es un KG privado e independiente con sourcing en
fuentes trazables; no es una superficie oficial de MINEDUC. El KG no genera el proyecto: recupera
evidencia, resuelve targets, compila una spec y valida lo que tú generas.

## Explorar

1. Usa `runtime_status` solo si necesitas comprobar release, cobertura o paridad.
2. Consulta `query_curriculum` para habilidades, progresiones, OA y evidencia pedagógica de cada
   asignatura. Mantén cada OA atribuido a su asignatura, curso, programa y cita.
3. Si el proyecto usa libros o recursos concretos, consulta `query_teaching_materials` por asignatura y
   curso, conservando `package_id`, `resource_ref` y citas de cada material.

## Construir el proyecto

1. Resuelve con `resolve_curricular_targets` los OA explícitos de cada dominio. Si una combinación no
   forma un target canónico único, conserva targets separados y no los fuerces.
2. Selecciona una conexión sustentada por evidencia; no conviertas una similitud temática en una relación
   curricular declarada.
3. Llama `compile_artifact` con `artifact_type: project`, un propósito compatible, el
   `target_set_ref` no ambiguo y los `resource_refs` pertinentes.
4. Genera tú el proyecto desde el packet.
5. Valida con `validate_artifact`, copiando intactos ids, hash, firma, algoritmo, key id, encoding,
   release, tipo y propósito de `compile_artifact`.

## Varios materiales

- `package_ids` representa los libros/bundles activos; `material_ids` son secciones concretas.
- Un `package_id` activo restringe; sin paquete activo consulta todos los paquetes autorizados y pagina
  hasta completar. Puedes combinar evidencia manteniendo procedencia y targets resueltos.
- Si se pide una estructura interna por número, usa `material_unit_number`. `material_unit_kind` es un
  filtro opcional: no lo infieras desde la palabra "unidad" ni lo confundas con una unidad curricular.

## Reglas

- Cita cada afirmación y distingue fuente declarada, modelado y síntesis.
- Nunca inventes OA ni escondas ausencia de cobertura.
- Los ítems fuente no son entregables.
- Todo proyecto requiere revisión humana.
- Si el MCP responde 401, usa `setup`.
