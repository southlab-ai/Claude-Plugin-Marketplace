---
name: kg-overview
description: Qué es el Knowledge Layer del Currículum Nacional de Chile y cómo usar sus herramientas MCP (search, search_global, answer, graph). Lee esto primero cuando el usuario pregunte por currículum, OA, planificación, evaluaciones o recursos chilenos.
---

# Knowledge Layer del Currículum Nacional de Chile

Tienes acceso, vía el MCP `kg-educacion`, a un grafo de conocimiento construido sobre las
fuentes oficiales del Currículum Nacional (curriculumnacional.cl, MINEDUC). Sirve para apoyar
a profesores y equipos directivos. **Todo es de solo lectura y siempre citas la fuente.**

## Qué contiene (capas)
- **OA oficiales** por curso, asignatura y eje, con sus recursos y clases asociadas.
- **Habilidades transversales** que cruzan asignaturas (argumentar, investigar, modelar, colaborar…).
- **Secuencias** de unidades y clases con **horas pedagógicas** (pacing del año).
- **Recursos** catalogados por curso/asignatura/categoría/formato (lecturas, videos, actividades…).
- **Demanda cognitiva** (Bloom y DOK) de OA e ítems, para balancear evaluaciones.
- **Progresiones** entre grados (qué OA se apoya en el del nivel anterior).
- **Comunidades temáticas (GraphRAG)**: grandes hilos que conectan el currículum de forma interdisciplinaria.

## Herramientas y cuándo usarlas
| Herramienta | Úsala para |
|---|---|
| `search` | Preguntas **específicas**: un OA por código/tema, recursos de un curso, horas de una unidad. |
| `search_global` | Preguntas **temáticas/panorama**: "qué temas cruzan el currículum", "cómo se conectan dos asignaturas". |
| `answer` | Una respuesta **redactada con citas** verificables. |
| `entity_lookup` → `graph_neighbors` / `graph_path` | Explorar **relaciones** de una entidad (OA, eje, habilidad, comunidad). |
| `fetch` / `list_sources` | Traer un chunk/documento por id; ver fuentes indexadas. |

## Reglas
- Cita siempre la fuente oficial que devuelve la herramienta.
- Si no hay evidencia, dilo explícitamente — no inventes OA ni códigos.
- Para tareas de planificación, evaluación, recursos o proyectos interdisciplinarios, usa las skills
  específicas de este plugin (`planificar`, `crear-evaluacion`, `buscar-recursos`, `temas-transversales`).
- Si el MCP responde 401, falta configurar `KG_API_KEY`: usa la skill `setup`.
