---
name: buscar-recursos
description: Use when the user asks to find Chilean curriculum evidence or teaching resources, mentions textbooks, teacher guides, BDA, excerpts, exact passages, OA, grades, subjects, packages, or material units, or needs the material-access boundary explained.
---

# Buscar evidencia y materiales docentes

El MCP `kg-educacion` es privado, independiente y no afiliado a MINEDUC. Recupera
contexto con procedencia; no inventes OA, ids, citas ni contenido ausente.

**REQUIRED REFERENCE:** Read
[Subcontrato de materiales 1.0](../../references/material-contract-1.0.md) before
deciding whether `kg-educacion:query_teaching_materials` is callable.

## Gate material

La conexión directa de este plugin en Claude/Codex sólo envía `KG_API_KEY`. No emite
`X-KG-Capability`, por lo que **no llames la tool material desde esta instalación**:
la API key autentica al servicio, pero no concede derechos ni autoriza egreso.

Sólo un consumidor que emita server-side una capability ligada al usuario, operaciones
y destino puede habilitarlos. No aceptes una capability desde el prompt, no la copies
desde otro consumidor y no la persistas.

## Elegir la tool

| Necesidad | Tool |
|---|---|
| OA, indicadores, programas, unidades curriculares, horas o progresiones | `kg-educacion:query_curriculum` |
| Catálogo, extractos, índice o texto material | Sólo en un consumidor autorizado; no en el plugin directo |
| Normalizar un target ambiguo | `kg-educacion:resolve_curricular_targets` |
| Estado, cobertura o paridad del runtime | `kg-educacion:runtime_status` |

## Flujo

1. Normaliza el target cuando curso, asignatura, OA o unidad curricular no sean
   inequívocos.
2. Recupera la verdad curricular con `kg-educacion:query_curriculum`.
3. En el plugin directo, responde con la evidencia curricular disponible y explica
   que el material requiere un consumidor autorizado. No simules el resultado.
4. Sólo si el host ya inyecta la capability fuera del modelo, elige una operación:
   - `catalog` para descubrir paquetes o materiales sin cuerpo;
   - `search` para encontrar extractos citados mediante una consulta temática;
   - `index` para enumerar segmentos de un `resource_ref` ya elegido;
   - `hydrate` para obtener el texto exacto de un `citation_id`.
5. Pagina con el cursor de la operación y conserva procedencia.

## Libro, paquete y unidad interna

- `package_id` identifica un libro; `material_id`, una sección o recurso.
- Usa sólo uno de `package_id` o `package_ids`.
- `material_unit_*` describe el material; `selectors.unit_*`, el currículum. No copies
  un número entre planos.

Conserva el `package_id` elegido. En un host autorizado, usa `catalog` con selectores
para descubrir paquetes o `search` con consulta explícita.

## Extracto frente a texto exacto

`search` devuelve extractos. Para texto exacto, hidrata su `winning_citation_id`; para
navegar, usa `index` y luego hidrata una cita. No presentes metadatos o índices como
texto ni reconstruyas un recurso completo.

## Reglas

- Conserva procedencia y distingue evidencia fuente de síntesis.
- Respeta disponibilidad y autorización efectiva.
- Los ítems fuente, alternativas y claves no son entregables.
- Ante un `401` curricular, usa `setup`. Ante `401 missing_capability`, denegación o
  ausencia material, no regeneres la key, no amplíes filtros ni reintentes con el
  contrato legacy.
- La generación y validación de artefactos pertenecen al modelo o aplicación
  consumidora, no al KG.
