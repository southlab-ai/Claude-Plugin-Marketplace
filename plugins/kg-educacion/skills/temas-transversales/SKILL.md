---
name: temas-transversales
description: Diseñar proyectos interdisciplinarios y explorar los grandes temas que cruzan el Currículum Nacional de Chile (habilidades transversales y panorama temático). Úsala para preguntas de panorama o cuando se quiera conectar varias asignaturas, usando query_curriculum + runtime_status.
---

# Temas transversales y proyectos interdisciplinarios

Apoya a profesores y directivos a ver el currículum como un todo conectado, usando el MCP `kg-educacion`
(runtime v2, modo PROMPT_ONLY). El KG no genera contenido ni aloja un LLM: compila **evidencia oficial
citada** y, cuando corresponde, una **spec/PromptPacket**; **tú (Claude) generas** el artefacto y luego lo
**validas**. Todo es read-only y citado; la vista de estudiante va sin clave; todo requiere revisión humana.

## Flujo recomendado
1. **Panorama y cobertura**: parte con `runtime_status` para ver el estado del servidor y la cobertura
   curricular disponible para tu solicitud (asignaturas, cursos, temas presentes).
2. **Grandes hilos temáticos**: `query_curriculum` con una consulta temática (p.ej. "grandes temas que
   cruzan el currículum") devuelve los hilos que conectan asignaturas, **con cita por resultado**.
3. **Conexión entre asignaturas**: `query_curriculum` con algo como "cómo se conectan ciencias y matemática"
   trae los OA y ejes que las puentean, cada uno con su fuente oficial citada.
4. **Habilidad transversal puntual**: `query_curriculum` con "habilidad transversal argumentar" (o investigar,
   colaborar…) trae la habilidad y los OA por asignatura que la desarrollan, citados.
5. **Aterriza el proyecto (PROMPT_ONLY)**: toma los OA reales que devolvió `query_curriculum` y usa
   `resolve_curricular_targets` para fijar el set de OA objetivo; luego `compile_artifact`
   (artifact_type `unit` o `class`) te entrega evidencia + decisión pedagógica + spec en un PromptPacket;
   **tú generas** la unidad interdisciplinaria; finalmente `validate_artifact`. (Puede combinarse con las
   skills `planificar` y `crear-evaluacion`.)

## Buenas prácticas
- Para "qué grandes temas…" usa `query_curriculum` con la consulta temática; `runtime_status` confirma qué
  hay realmente cubierto antes de prometer una conexión.
- `query_curriculum` nunca devuelve ítems fuente ni claves: cita siempre los OA y códigos reales que entrega.
- Nada es entregable sin pasar `validate_artifact` (conformidad de blueprint, ausencia de clave en la vista
  de estudiante, no-reuso de ítems fuente). Recuerda: el KG da evidencia+spec, tú generas, luego validas.
- Si no hay evidencia que calce, dilo en vez de forzar una conexión; nunca inventes OA ni códigos.
- Si el MCP responde 401, ve a la skill `setup` para configurar el acceso.
