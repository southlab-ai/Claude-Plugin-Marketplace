# kg-educacion

Plugin para consultar `kg-educacion`, un KG educativo privado, independiente y no
afiliado a MINEDUC. Recupera evidencia curricular, materiales docentes y marcos de
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
  → recuperar materiales cuando aporten a la tarea
  → recuperar marco evaluativo cuando corresponda
  → el modelo sintetiza el artefacto solicitado
```

El plugin no promete compilación o validación dentro del KG. La aplicación o el
modelo pueden aplicar sus propios contratos y revisiones después del retrieval.

## Currículum y materiales

- `selectors.unit_id` y `selectors.unit_number` son unidades curriculares.
- `material_unit_number` y `material_unit_name` son estructuras internas del material.
- `package_id` identifica el libro o bundle.
- `material_id` identifica una sección o recurso concreto.
- `paging.next_cursor` es la única señal de continuación.

Para una solicitud exhaustiva usa el menor límite suficiente y pagina hasta que
`paging.next_cursor` sea `null`. Mantén `package_id`, páginas, citas y procedencia al
combinar evidencia.

## Principios

- No inventar OA, ids, hashes, citas o disponibilidad.
- Distinguir evidencia fuente de síntesis del modelo.
- No entregar ítems fuente protegidos ni sus claves.
- Redactar una respuesta útil y positiva desde la evidencia recuperada.
