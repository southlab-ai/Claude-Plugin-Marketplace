---
name: crear-evaluacion
description: Crear evaluaciones originales alineadas a OA usando currículum, materiales y marcos recuperados desde KG Educación V3.
---

# Crear una evaluación con KG Educación

1. Resuelve curso, asignatura, OA y unidad con `resolve_curricular_targets`.
2. Recupera OA, indicadores y demanda cognitiva con `query_curriculum`.
3. Recupera materiales con `query_teaching_materials` si la evaluación usa un texto,
   unidad o recurso específico.
4. Recupera criterios pertinentes con `analyze_assessment_framework`. Lee la sección siguiente
   **antes** de comparar cualquier número que devuelva.
5. Genera una evaluación original con cobertura, dificultad y pauta coherentes.

## Cómo leer el marco de evaluación

El marco trae **dos** distribuciones con las mismas claves (`bloom:Aplicar`, `dok:DOK2`), y
significan cosas distintas:

| campo | qué es |
|---|---|
| `target_distribution.dimensions_range` | lo que la prueba **debería** tener: un rango `[min, max]` |
| `observed_distribution.dimensions` | lo que **tienen** las pruebas medidas: un valor |

**Comprueba `unit` en ambas antes de compararlas.** Si las dos dicen `tenths_of_percent`, los
números se comparan directamente: `853` cae dentro de `[780, 900]` y son 85,3%. Si
`target_distribution.unit` dice `percentage_points`, viene de un release anterior y hay que
multiplicar su rango por 10 antes de compararlo.

> Hasta el 2026-07-28 una iba en puntos y la otra en décimas sin declararlo, así que comparar
> `853` contra `[78, 90]` sugería que la prueba estaba nueve veces sobre el máximo. Comprueba la
> unidad; no la supongas.

**`observed_distribution` no es la distribución oficial.** Su campo `measured_on` lo dice: son
ensayos privados, **no ítems SIMCE oficiales de la Agencia de Calidad**. Cítalo como práctica
observada. Nunca escribas "según el marco SIMCE, el N% de los ítems son de X" apoyándote en ese
plano.

`withheld_families` **no es un error**: nombra las familias que el KG no sirve porque no puede
nombrarlas sin ambigüedad, con el motivo. Trátalo como información, no como fallo.

Y usa `total_items` para el número de preguntas; no lo deduzcas de los porcentajes ni de la prosa
de `basis`.

Conserva las citas del contexto. Los ítems fuente y sus claves son evidencia interna:
no se copian como evaluación final. La vista de estudiante no incluye respuestas.
La generación y cualquier validación posterior pertenecen al modelo o aplicación,
no a una tool del KG.
