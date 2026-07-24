---
name: crear-evaluacion
description: Crear evaluaciones originales alineadas a OA usando currículum, materiales y marcos recuperados desde KG Educación V3.
---

# Crear una evaluación con KG Educación

1. Resuelve curso, asignatura, OA y unidad con `resolve_curricular_targets`.
2. Recupera OA, indicadores y demanda cognitiva con `query_curriculum`.
3. Recupera materiales con `query_teaching_materials` si la evaluación usa un texto,
   unidad o recurso específico.
4. Recupera criterios pertinentes con `analyze_assessment_framework`.
5. Genera una evaluación original con cobertura, dificultad y pauta coherentes.

Conserva las citas del contexto. Los ítems fuente y sus claves son evidencia interna:
no se copian como evaluación final. La vista de estudiante no incluye respuestas.
La generación y cualquier validación posterior pertenecen al modelo o aplicación,
no a una tool del KG.
