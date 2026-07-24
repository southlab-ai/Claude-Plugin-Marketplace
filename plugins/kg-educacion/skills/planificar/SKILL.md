---
name: planificar
description: Planificar año, semestre, unidad o clase usando evidencia curricular y materiales recuperados desde KG Educación V3.
---

# Planificar con KG Educación

El KG aporta contexto; tú diseñas la planificación. Confirma asignatura, curso,
alcance, tiempo y restricciones solo cuando falten.

1. Usa `resolve_curricular_targets` para normalizar programa, OA o unidad curricular.
2. Usa `query_curriculum` para OA, indicadores, secuencia, horas y progresiones.
3. Usa `query_teaching_materials` cuando el docente pida usar un libro o cuando sus
   actividades mejoren la planificación.
4. Pagina hasta `paging.next_cursor: null` cuando la cobertura deba ser exhaustiva.
5. Construye la planificación respetando continuidad, duración, evidencia y fuentes.

Para una estructura interna de un libro usa `material_unit_number`; no la copies a
`selectors.unit_number`. Mantén `package_id`, página, `resource_ref` y cita. Sin libro
activo, busca ampliamente por curso, asignatura y OA.

Entrega una planificación clara y aplicable. El KG no compila ni valida el artefacto;
si la aplicación dispone de validadores propios, estos se ejecutan fuera del KG.
