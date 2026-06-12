---
name: crear-evaluacion
description: Crear evaluaciones y pruebas alineadas a OA del Currículum Nacional de Chile, balanceadas por demanda cognitiva (Bloom/DOK). Úsala cuando el usuario pida armar una prueba, evaluación, ensayo o set de ítems.
---

# Crear evaluaciones alineadas y balanceadas

Apoya al profesor a construir una evaluación válida usando el MCP `kg-educacion`.

## Flujo recomendado
1. **Alcance**: curso, asignatura y qué OA o unidad se evalúa. Si falta, pregúntalo.
2. **OA a evaluar**: `search` para traer los OA oficiales de ese alcance (con su descripción).
3. **Demanda cognitiva**: `search` con "demanda cognitiva" / "bloom" del curso/asignatura para ver la
   distribución por nivel (recordar→crear, DOK 1-4). Úsala para **balancear** la prueba: no todo "recordar".
4. **Construcción**: redacta ítems alineados a cada OA, etiquetando el nivel Bloom/DOK objetivo de cada uno.
   Si existen ítems en el banco para ese OA, recupéralos con `search` y reúsalos/adáptalos.
5. **Tabla de especificaciones**: presenta la prueba con su blueprint (OA × nivel cognitivo × puntaje).

## Buenas prácticas
- Alinea **cada ítem a un OA real** (código del grafo) y declara su nivel cognitivo.
- Balancea la demanda: combina niveles bajos (recordar/comprender) y altos (analizar/evaluar/crear)
  según lo que el OA exige, apoyándote en la distribución cognitiva del grafo.
- Para evaluaciones tipo SIMCE/PAES, pide explícitamente el eje/habilidad y respeta su proporción.
- Cita la fuente de cada OA. Si no hay evidencia, dilo en vez de inventar.
