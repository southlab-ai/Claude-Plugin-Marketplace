---
name: buscar-recursos
description: Encontrar recursos y evidencia curricular oficial citada (lecturas, videos, actividades, imágenes, OA, clases) del Currículum Nacional de Chile por OA, curso, asignatura o formato, y el CATÁLOGO de libros/textos escolares oficiales MINEDUC (texto del estudiante, guía docente, cuaderno) con la URL que abre el libro. Úsala cuando el usuario pida materiales, recursos, actividades, o el LIBRO/TEXTO oficial de un curso. Usa query_curriculum (evidencia por OA) y query_resources (catálogo de libros); runtime_status para cobertura.
---

# Buscar recursos didácticos por OA y curso

Apoya al profesor a encontrar evidencia y materiales oficiales usando el MCP `kg-educacion` (runtime v2,
serverInfo 2.0.0, modo PROMPT_ONLY). En este runtime el KG **no genera contenido ni aloja un LLM**:
compila evidencia oficial **citada** y, cuando hace falta, una spec/PromptPacket; el modelo que llama
(tú) redacta el artefacto y luego se valida. Para solo buscar recursos, basta con recuperar y presentar
la evidencia citada.

## Flujo recomendado
1. **Cobertura primero**: `runtime_status` para confirmar el estado del servidor y la cobertura
   curricular de la solicitud (curso/asignatura/OA). Si algo no está cubierto, dilo antes de prometer.
2. **Qué busca**: OA o tema + curso/asignatura, y opcionalmente el formato (video, lectura, actividad,
   imagen).
3. **Búsqueda**: `query_curriculum` con la consulta. Es la recuperación curricular oficial **con cita
   por resultado**. Para "qué recursos hay para X curso" filtra por (curso, asignatura) y agrupa por
   categoría y formato disponibles.
4. **Por OA puntual**: si el usuario da un código (ej. `LE04 OA 04`), `query_curriculum` con ese código
   trae los recursos y clases que apuntan a ese OA, cada uno con su cita.
5. **Presenta** los recursos con su título y enlace/cita oficial, agrupados por categoría o formato.

## Libros / textos escolares oficiales → `query_resources`
Cuando el usuario pide el **libro o texto oficial** que usan los estudiantes (no evidencia suelta por OA),
usa **`query_resources`**, no `query_curriculum`:
- Filtra por `subject` + `grade` y, opcional, `resource_type` (`texto_estudiante` | `guia_docente` |
  `cuaderno_actividades`). Ej: "¿qué texto de Matemática usa 4° básico?" → `query_resources(subject="matematica",
  grade="4_basico", resource_type="texto_estudiante")`.
- Devuelve cada libro con su **`source_url`** oficial (`curriculumnacional.cl`) — el enlace que **abre el libro**,
  con los tomos agrupados, editorial y tipo.
- Por defecto trae la categoría "Libro - Textos Escolares MINEDUC". `query_curriculum` es para evidencia citada
  por OA; **no reconstruyas un libro desde snippets** de `query_curriculum` — para "el libro", usa `query_resources`.

## Buenas prácticas
- `query_curriculum` nunca devuelve ítems fuente ni claves; es read-only y citado, vista de estudiante.
- Filtra por curso/asignatura para no mezclar niveles.
- Si el usuario quiere un proyecto que cruce asignaturas, combina con `temas-transversales`
  (consultas temáticas vía `query_curriculum`).
- Si pasa de buscar a **crear** (actividad, evaluación, clase): resuelve objetivos con
  `resolve_curricular_targets`, compila con `compile_artifact` (recibes un PromptPacket), **tú generas**
  el artefacto y luego corres `validate_artifact`. El KG entrega evidencia + spec; tú generas; luego validas.
- Devuelve siempre la fuente/cita. Si no hay evidencia, dilo; nunca inventes recursos, OA ni códigos.
- Si el MCP responde 401, ve a la skill `setup` para configurar el acceso.
