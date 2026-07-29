# kg-educacion

Plugin para consultar `kg-educacion`, un KG educativo privado, independiente y no
afiliado a MINEDUC. La conexión directa recupera evidencia curricular y marcos de
evaluación con procedencia. El KG es una tool de contexto: no aloja un LLM, no redacta
artefactos y no impone el comportamiento del modelo consumidor.

## Instalación

```bash
claude plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
claude plugin install kg-educacion@southlab-marketplace

codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin add kg-educacion@southlab-marketplace
```

Configura `KG_API_KEY` mediante `/kg-setup` o la skill `setup`. Nunca guardes la key
literal en un repositorio.

## Contrato V3

El servidor anuncia `serverInfo 3.0.0` y exactamente cinco tools:

1. `runtime_status`
2. `query_curriculum`
3. `query_teaching_materials`
4. `resolve_curricular_targets`
5. `analyze_assessment_framework`

Flujo recomendado:

```text
resolver target curricular
  → recuperar evidencia curricular
  → usar materiales sólo desde un consumidor con capability válida
  → recuperar marco evaluativo cuando corresponda
  → el modelo sintetiza el artefacto solicitado
```

El plugin no promete compilación o validación dentro del KG. La aplicación o el
modelo pueden aplicar sus propios contratos y revisiones después del retrieval.

## Currículum y materiales

La API key autentica al servicio, pero no concede derechos sobre materiales. La
instalación directa de este marketplace no emite ni refresca `X-KG-Capability`, por lo
que Claude y Codex no deben llamar `query_teaching_materials` desde esta conexión.
Catálogo, búsqueda, índice e hidratación funcionan únicamente dentro de un consumidor
autorizado que emita una capability efímera de usuario, operaciones y destino real.
Una capability copiada desde otro consumidor o proveedor no es reutilizable.

Para esos consumidores autorizados:

- `selectors.unit_id` y `selectors.unit_number` son unidades curriculares.
- `material_unit_number` y `material_unit_name` son estructuras internas del material.
- `package_id` identifica el libro o bundle.
- `material_id` identifica una sección o recurso concreto.
- Toda llamada material incluye `material_contract_version: "1.0"` y una operación:
  `catalog`, `search`, `index` o `hydrate`.
- `catalog` devuelve metadatos, `search` extractos citados, `index` segmentos e
  `hydrate` el texto exacto de un `citation_id`.

Para una solicitud exhaustiva usa el menor límite suficiente y pagina hasta que
`paging.next_cursor` sea `null`. Copia ese cursor en `catalog_cursor`,
`search_cursor` o `index_cursor`, según la operación; no uses un `cursor` genérico.
Mantén `package_id`, páginas, citas y procedencia al combinar evidencia.

La referencia ejecutable para agentes está en
[`references/material-contract-1.0.md`](references/material-contract-1.0.md).

## Principios

- No inventar OA, ids, hashes, citas o disponibilidad.
- Distinguir evidencia fuente de síntesis del modelo.
- No entregar ítems fuente protegidos ni sus claves.
- Redactar una respuesta útil y positiva desde la evidencia recuperada.
- No tratar `KG_API_KEY` como autorización material ni pedir una capability en el
  prompt, chat o configuración persistente del plugin.
- Ante una denegación material, no ampliar el scope ni reintentar con un contrato
  anterior.
