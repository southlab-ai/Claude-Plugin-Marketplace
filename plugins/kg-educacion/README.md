# kg-educacion

Plugin para Claude Code y Codex que conecta `kg-educacion`, un **KG educativo privado, independiente y
no afiliado a MINEDUC**. Su sourcing incluye fuentes públicas y materiales publicados o distribuidos
por MINEDUC, además de materiales privados autorizados. La autoridad pertenece a cada fuente citada;
el KG, sus tools y su catálogo no son "oficiales MINEDUC".

El corpus/KG se consulta en modo read-only; auth, uso y auditoría pueden registrar actividad. El runtime
no aloja un LLM: resuelve targets, recupera evidencia y materiales, y compila una spec. El modelo genera
el artefacto y el KG lo valida. Todo entregable requiere revisión humana.

## Instalación

**Claude Code**

```bash
claude plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
claude plugin install kg-educacion@southlab-marketplace
```

**Codex**

```bash
codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin install kg-educacion@southlab-marketplace
```

El plugin aporta las skills. El MCP autenticado se registra aparte en Codex.

## Configurar acceso

La variable `KG_API_KEY` sirve para Claude y Codex. La forma guiada es `/kg-setup` o la skill `setup`.
Configuración manual de Codex:

```bash
export KG_API_KEY=kg_live_…
codex mcp add kg-educacion --url https://api.southlab.ai/mcp --bearer-token-env-var KG_API_KEY
```

En macOS, las apps abiertas desde el Dock pueden requerir:

```bash
launchctl setenv KG_API_KEY "$KG_API_KEY"
```

Nunca guardes el token literal en el repositorio. Si el MCP responde 401, ejecuta `setup` y reinicia el
cliente.

## Skills

- `kg-overview`: contrato y orquestación v3.
- `planificar`: año, unidad, semana y clase.
- `crear-evaluacion`: evaluaciones e ítems originales.
- `buscar-recursos`: evidencia curricular y materiales docentes.
- `temas-transversales`: proyectos interdisciplinarios.
- `setup`: registro y conexión.

## Runtime v3

El servidor debe anunciar `serverInfo` `3.0.0` y exactamente estas **7 tools**:

1. `runtime_status`
2. `query_curriculum`
3. `query_teaching_materials`
4. `resolve_curricular_targets`
5. `analyze_assessment_framework`
6. `compile_artifact`
7. `validate_artifact`

## Orquestación de artefactos

```text
resolve_curricular_targets
  → query_curriculum
  → query_teaching_materials (si aplica)
  → analyze_assessment_framework (solo si aplica)
  → compile_artifact
  → el modelo genera
  → validate_artifact
```

`compile_artifact` recibe el `target_set_ref` firmado completo, `resource_refs` autorizados y las
restricciones. `validate_artifact` recibe el artefacto generado y copia sin cambios los ids, hash, firma,
algoritmo, key id, encoding, release, tipo y propósito emitidos por la compilación.

## Currículum y material no son lo mismo

- `selectors.unit_id` / `selectors.unit_number`: unidad curricular canónica del programa.
- `material_unit_number` / `material_unit_name`: estructura interna del libro o bundle.
- `material_unit_kind`: refinamiento opcional (`unidad`, `leccion`, `capitulo`, `seccion`); nunca se
  infiere desde la palabra "unidad" y su ausencia no bloquea.
- `package_id`: identidad del libro/bundle activo.
- `material_id`: sección o material concreto.

Si el docente dice "Unidad 1" y hay un `package_id` activo, se consulta ese paquete con
`material_unit_number: 1`. Sin paquete activo, se consultan todos los paquetes autorizados que calcen;
el modelo filtra o combina evidencia conservando procedencia. Dentro del mismo paquete, unidad y lección
pueden combinarse si la evidencia demuestra el mismo alcance conceptual.

Un OA explícito recupera evidencia y materiales de todas las estructuras y paquetes autorizados, salvo
que un `package_id` o `package_ids` activo restrinja la búsqueda. Toda consulta paginada debe continuar
con `next_cursor` mientras exista o la respuesta indique `has_more`.

## Ejemplo: estructura 1 de Lenguaje 4° en cinco clases

1. `query_teaching_materials` con asignatura, curso y `material_unit_number: 1`; agrega `package_id` solo
   si el libro ya está activo.
2. Reúne los OA declarados por las estructuras recuperadas y resuélvelos con
   `resolve_curricular_targets`. Aclara solo si corresponden a identidades curriculares incompatibles.
3. Consulta `query_curriculum` para evidencia curricular de esos OA.
4. Compila:

```json
{
  "artifact_type": "unit",
  "purpose": "plan",
  "planning_granularity": "unit",
  "target_set_ref": "<objeto firmado completo>",
  "resource_refs": ["<refs recuperadas>"],
  "constraints": {"class_count": 5}
}
```

5. El modelo genera exactamente cinco elementos en `artifact_payload.periods` y llama
   `validate_artifact`.

## Invariantes

- Cita las fuentes y distingue autoridad declarada, modelado y síntesis.
- Nunca inventa OA, referencias, ids, hashes o firmas.
- Los ítems fuente y sus claves no son entregables; los ítems finales son originales.
- La vista de estudiante no contiene claves; la pauta vive en la vista docente.
- Una falla de validación se corrige contra la misma spec, sin alterar sus bindings.

---
SouthLab AI · KG privado con sourcing trazable en materiales educativos chilenos.
