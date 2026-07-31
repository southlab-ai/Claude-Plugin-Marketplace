---
name: crear-evaluacion
description: Use when the user asks to create an original Chilean curriculum-aligned assessment, rubric, answer key, or student and teacher versions grounded in OA and authorized sources.
---

# Crear una evaluación

1. Usa `explorar_oa` y `consultar_curriculum` para resolver curso, asignatura, OA e
   indicadores.
2. Usa `consultar_recursos` si la evaluación depende de un texto autorizado.
3. Usa `consultar_marco_evaluacion` cuando corresponda un marco o familia evaluativa.
4. Inicia el workflow con `evaluacion_preparar`, completa la especificación y persiste
   con `evaluacion_guardar`.
5. Genera ítems originales; no copies ítems fuente ni expongas claves en la vista estudiante.

Conserva citas. No inventes texto ausente. Una denegación de materiales se resuelve en
los permisos de la cuenta, no agregando headers ni regenerando la API key.
