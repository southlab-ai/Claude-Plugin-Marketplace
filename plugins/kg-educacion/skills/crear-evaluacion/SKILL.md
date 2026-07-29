---
name: crear-evaluacion
description: Use when the user asks to create an original Chilean curriculum-aligned assessment, quiz, test blueprint, rubric, answer key, or student and teacher versions grounded in OA and source evidence.
---

# Crear una evaluación con KG Educación

**REQUIRED REFERENCE FOR MATERIALS:** Read
[Subcontrato de materiales 1.0](../../references/material-contract-1.0.md) before
deciding whether the material tool is callable.

1. Resuelve curso, asignatura, OA y unidad con
   `kg-educacion:resolve_curricular_targets`.
2. Recupera OA, indicadores y demanda cognitiva con
   `kg-educacion:query_curriculum`.
3. En Claude/Codex directos, no llames materiales: la API key no concede esa
   autorización. Si la evaluación usa un pasaje, trabaja con texto legítimamente
   aportado por el usuario o pide usar un consumidor autorizado.
4. Sólo en ese consumidor, ejecuta material `search`; para una cita textual hidrata el
   `winning_citation_id`, o usa `index` y después `hydrate`.
5. Recupera criterios pertinentes con
   `kg-educacion:analyze_assessment_framework`. Lee la sección siguiente antes de
   comparar cualquier número.
6. Genera una evaluación original con cobertura, dificultad y pauta coherentes.

## Cómo leer el marco de evaluación

El marco trae **dos** distribuciones con las mismas claves (`bloom:Aplicar`, `dok:DOK2`), y
significan cosas distintas:

| campo | qué es |
|---|---|
| `target_distribution.dimensions_range` | lo que la prueba **debería** tener: un rango `[min, max]` |
| `observed_distribution.dimensions` | lo que **tienen** las pruebas medidas: un valor |

**Comprueba `unit` en ambas antes de compararlas.** Si las dos dicen
`tenths_of_percent`, los números se comparan directamente: `853` cae dentro de
`[780, 900]` y son 85,3%. Si las unidades no coinciden, no conviertas ni supongas:
reporta la incompatibilidad del contrato.

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
Un extracto de `search` no es una cita textual ampliable: si el ítem depende de
palabras exactas, usa únicamente el `source_text` devuelto por `hydrate`.
La generación y cualquier validación posterior pertenecen al modelo o aplicación,
no a una tool del KG.
