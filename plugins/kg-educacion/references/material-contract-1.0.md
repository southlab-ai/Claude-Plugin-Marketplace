# Subcontrato de materiales 1.0

Esta referencia aplica al flujo interno de Horacio que, antes de llamar al contrato de
materiales, ya resolvió la cuenta, las habilitaciones y el scope del usuario.
Horacio publica una capability efímera dentro de su runtime para poder consultar el
contenedor de materiales del grant vigente.

En un consumidor autorizado, el contrato es clean-cut: cada request incluye
`"material_contract_version": "1.0"` y una sola `operation`. No reintentes con el
payload anterior si el schema lo rechaza.

## Elegir la operación

| Necesidad | `operation` | Devuelve |
|---|---|---|
| Descubrir paquetes o materiales autorizados | `catalog` | Metadatos sin `source_text` |
| Encontrar evidencia por significado | `search` | Extractos citados y recibo de selección |
| Enumerar segmentos de un recurso elegido | `index` | Entradas de índice sin hidratar texto |
| Obtener el texto exacto de una cita | `hydrate` | `source_text` de esa cita y su extensión |

`catalog` y `search` aceptan filtros materiales. Nunca envíes `package_id` y
`package_ids` juntos. La unidad interna del material (`material_unit_*`) no es una
unidad curricular (`selectors.unit_*`).

## Requests válidos

Catálogo. Requiere `selectors` o `material_ids`; un filtro de paquete no basta por sí
solo:

```json
{
  "material_contract_version": "1.0",
  "operation": "catalog",
  "selectors": {
    "subject": "Ciencias Naturales",
    "grade": "8 basico"
  },
  "limit": 50
}
```

Búsqueda semántica. `query` es obligatoria y va fuera de `selectors`:

```json
{
  "material_contract_version": "1.0",
  "operation": "search",
  "query": "actividades experimentales sobre transferencia de calor",
  "selectors": {
    "subject": "Ciencias Naturales",
    "grade": "8 basico"
  },
  "component_kinds": [
    "teaching_activity"
  ],
  "limit": 10
}
```

Índice de un recurso ya elegido:

```json
{
  "material_contract_version": "1.0",
  "operation": "index",
  "resource_ref": "resource:student-text",
  "limit": 50
}
```

Hidratación exacta. No admite `query`, filtros, `resource_ref`, `limit` ni cursor:

```json
{
  "material_contract_version": "1.0",
  "operation": "hydrate",
  "citation_id": "citation:page-segment:1"
}
```

## Paginación disjunta

La respuesta MCP publica la continuación en
`structuredContent.paging.next_cursor`. Si no es `null`, repite la misma operación y
los mismos filtros, copiando ese valor en el campo de request que corresponde:

| Operación | Campo de request |
|---|---|
| `catalog` | `catalog_cursor` |
| `search` | `search_cursor` |
| `index` | `index_cursor` |

Los cursores son opacos y no se intercambian. `hydrate` devuelve `paging: null`.

Cada cursor queda ligado a la identidad, release, autorización y grano de su
operación; el release material es read-only e inmutable, y `search_cursor` además fija
el snapshot del ranking. No lo edites ni lo reutilices con otro scope. Si el runtime
rechaza un cursor, detén esa paginación; si el usuario aún necesita completitud,
reinicia desde la primera página con el mismo scope **una sola vez**. Si vuelve a
fallar, detente y reporta que no se demostró completitud.

Durante una lectura exhaustiva:

- registra los cursores ya vistos y detente si uno se repite;
- trata una página vacía con cursor no nulo como anomalía y no entres en un loop;
- deduplica paquetes de catálogo por `package_id`, materiales de catálogo por
  `(package_id, material_id)`, búsqueda por `winning_citation_id` e índice por
  `citation_id`, conservando la primera aparición;
- reporta la anomalía si hubo duplicados o un cursor inválido: no declares
  exhaustividad silenciosamente.

## Lectura segura de resultados

- `catalog`: usa `structuredContent.llm_context.result.packages` y `materials` para
  elegir; `content_status` es `metadata`.
- `search`: cada material utilizable en `structuredContent.llm_context.result.materials`
  trae `content_status: excerpt`, `source_text`,
  `winning_citation_id` y `content_extent`. `relevant_total` coincide con
  `structuredContent.paging.total`; `candidate_total` es anterior al umbral.
- `index`: usa `structuredContent.llm_context.result.entries` para elegir una cita; no
  presentes el índice como texto fuente.
- `hydrate`: presenta como cita exacta sólo
  `structuredContent.llm_context.result.source_text` con
  `content_status: source_text`; conserva `citation_id`, `resource_ref`,
  `content_extent` y `navigation`.

Para una cita exacta encontrada por búsqueda, hidrata su `winning_citation_id`. Para
explorar un recurso, usa primero `index` y después hidrata únicamente la cita elegida.
No reconstruyas un libro completo ni conviertas un extracto en una cita textual más
amplia.

## Autorización y errores

El catálogo, el texto y sus conteos ya están limitados por la autorización efectiva.
`401 missing_capability` no significa que falte la API key: significa que este
consumidor no emitió una capability material válida. Ante ese error, `403`, denegación
o `not_found`, no amplíes el scope, no cambies de operación para eludir la respuesta y
no uses un fallback legacy. Explica el límite o pide al usuario usar el consumidor
autorizado.
