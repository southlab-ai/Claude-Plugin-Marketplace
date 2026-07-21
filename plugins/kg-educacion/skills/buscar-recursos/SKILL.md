---
name: buscar-recursos
description: Buscar evidencia curricular y materiales docentes con el KG Educación v3. Usa query_curriculum para OA, programas e indicadores; usa query_teaching_materials para libros, guías, BDA, actividades y componentes por package_id, OA o estructura interna del material.
---

# Buscar evidencia y materiales docentes v3

El MCP `kg-educacion` (`serverInfo` `3.0.0`) expone un KG privado e independiente. Las citas pueden
apuntar a fuentes publicadas o distribuidas por MINEDUC, pero el KG y su catálogo no son oficiales ni
están afiliados a MINEDUC.

## Elegir la tool correcta

- Usa `query_curriculum` para verdad curricular: OA, indicadores, programas, unidades curriculares,
  horas, progresiones y evidencia pedagógica.
- Usa `query_teaching_materials` para materiales: textos del estudiante, guías docentes, cuadernos,
  actividades, BDA, multimedia, aplicaciones y materiales privados autorizados.
- Usa `runtime_status` solo para release, capacidades, cobertura o paridad.

## Buscar por OA

1. Resuelve el OA con `resolve_curricular_targets` si el código o el alcance no son ya inequívocos.
2. Consulta `query_curriculum` para recuperar evidencia curricular citada.
3. Consulta `query_teaching_materials` con `selectors.subject`, `selectors.grade` y
   `selectors.oa_codes`. Si hay libro(s) activo(s), restringe con `package_id` o `package_ids`; si no,
   consulta todos los paquetes autorizados. Pagina con `next_cursor` hasta terminar.
4. Presenta cada resultado con título, componente, disponibilidad, `package_id`, estructura interna,
   `resource_ref` y cita. No prometas contenido ausente o bloqueado.

## Buscar por libro o bundle

1. Busca por asignatura, curso y tipo de componente con `query_teaching_materials`.
2. Trata `package_id` como la identidad del libro/bundle completo y mantenla en el contexto de la
   conversación cuando el docente elija ese material.
3. Trata `material_id` como una sección o material concreto. No lo uses para representar todo el libro.
4. Para hidratar una cita o recurso exacto, reutiliza el `citation_id` o `resource_ref` devuelto; no lo
   fabriques.

## Buscar por "Unidad 1" del material

Con un `package_id` activo, llama:

```json
{
  "package_id": "<libro activo>",
  "material_unit_number": 1
}
```

`material_unit_kind` es opcional. No lo infieras desde la palabra "Unidad"; si viene omitido, presenta
"estructura interna 1". No lo confundas con `selectors.unit_number`, una unidad curricular canónica.

Sin libro activo, consulta todos los paquetes autorizados por asignatura, curso y número. El modelo
filtra o combina la evidencia. Dentro del mismo paquete, unidad y lección pueden combinarse si la
evidencia muestra el mismo alcance conceptual.

## Varios paquetes

`package_ids` permite restringir, comparar o combinar materiales activos. Sin paquetes activos, la
búsqueda es amplia sobre todos los autorizados. Mantén la procedencia por paquete y deja que el modelo
filtre; resuelve los OA antes de compilar y aclara solo incompatibilidades curriculares reales.

## Pasar de búsqueda a creación

Resuelve el target con `resolve_curricular_targets`, compila con `compile_artifact` usando el
`target_set_ref` completo y los `resource_refs` seleccionados, genera tú el artefacto y llama
`validate_artifact` con la spec firmada intacta.

## Reglas

- Cita siempre la fuente y distingue disponibilidad `available`, `partial`, `metadata_only` o `blocked`.
- Nunca reconstruyas un libro completo desde snippets ni inventes OA o enlaces.
- Los ítems fuente y sus claves no son entregables.
- Si el MCP responde 401, usa `setup`.
