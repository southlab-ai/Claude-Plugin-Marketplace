---
name: buscar-recursos
description: Encontrar recursos didácticos oficiales (lecturas, videos, actividades, imágenes) del Currículum Nacional de Chile por OA, curso, asignatura o formato. Úsala cuando el usuario pida materiales, recursos o actividades para enseñar algo.
---

# Buscar recursos didácticos por OA y curso

Apoya al profesor a encontrar materiales oficiales usando el MCP `kg-educacion`.

## Flujo recomendado
1. **Qué busca**: OA o tema + curso/asignatura, y opcionalmente el formato (video, lectura, actividad, imagen).
2. **Búsqueda**: `search` con la consulta. Para "qué recursos hay para X curso" el grafo tiene un
   índice por (curso, asignatura) con el desglose de categorías y formatos disponibles.
3. **Por OA puntual**: si el usuario da un código (ej. `LE04 OA 04`), `search` con ese código trae los
   recursos y clases que apuntan a ese OA.
4. **Presenta** los recursos con su título y enlace/cita oficial, agrupados por categoría o formato.

## Buenas prácticas
- Filtra por curso/asignatura para no mezclar niveles.
- Si el usuario quiere un proyecto que cruce asignaturas, combina con `temas-transversales`.
- Devuelve siempre la fuente/enlace. No inventes recursos que el grafo no devuelva.
