---
name: temas-transversales
description: Diseñar proyectos interdisciplinarios y explorar los grandes temas que cruzan el Currículum Nacional de Chile (habilidades transversales y comunidades temáticas GraphRAG). Úsala para preguntas de panorama o cuando se quiera conectar varias asignaturas.
---

# Temas transversales y proyectos interdisciplinarios

Apoya a profesores y directivos a ver el currículum como un todo conectado, usando el MCP `kg-educacion`.

## Flujo recomendado
1. **Panorama**: `search_global` (sin query o con un tema) devuelve las **comunidades temáticas** —
   los grandes hilos que conectan asignaturas. Nivel `L0` = temas amplios, `L1` = más finos.
2. **Conexión entre asignaturas**: `search_global` con algo como "cómo se conectan ciencias y matemática"
   trae las comunidades que las puentean, con su descripción y OA representativos.
3. **Habilidad transversal puntual**: `search` con "habilidad transversal argumentar" (o investigar,
   colaborar…) trae la habilidad y los ejes/OA por asignatura que la desarrollan.
4. **Aterriza el proyecto**: toma los OA representativos de la comunidad/habilidad y arma una unidad
   interdisciplinaria concreta (puede combinarse con las skills `planificar` y `crear-evaluacion`).

## Buenas prácticas
- Para "qué grandes temas…" usa `search_global`, NO `search` (el local no sintetiza el panorama).
- Cita los OA reales que devuelve cada comunidad. La aplicación docente de cada reporte ya sugiere usos.
- Si no hay una comunidad que calce, dilo en vez de forzar una conexión.
