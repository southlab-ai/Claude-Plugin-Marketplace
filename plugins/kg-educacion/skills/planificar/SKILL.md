---
name: planificar
description: Use when the user asks to plan a Chilean school year, semester, unit, week, lesson, learning sequence, or classroom activity aligned to curriculum and optionally grounded in teaching materials.
---

# Planificar con KG Educación

El KG aporta contexto; tú diseñas la planificación. Confirma asignatura, curso,
alcance, tiempo y restricciones solo cuando falten.

**REQUIRED REFERENCE FOR MATERIALS:** Read
[Subcontrato de materiales 1.0](../../references/material-contract-1.0.md) before
deciding whether the material tool is callable.

1. Usa `kg-educacion:resolve_curricular_targets` para normalizar programa, OA o unidad
   curricular.
2. Usa `kg-educacion:query_curriculum` para OA, indicadores, secuencia, horas y
   progresiones.
3. En Claude/Codex directos, no llames materiales: la conexión no emite la capability
   de usuario y destino. Planifica desde currículum o desde un texto que el usuario
   haya proporcionado legítimamente en la conversación.
4. Sólo en un consumidor autorizado, usa `search` con `package_id`, consulta temática
   y selectores; usa `catalog` para descubrir el paquete, `index` para recorrer un
   recurso e `hydrate` para una cita exacta.
5. En ese consumidor, repite la misma operación y copia
   `paging.next_cursor` al cursor de esa operación. No uses un `cursor` genérico.
6. Construye la planificación respetando continuidad, duración, evidencia y fuentes.

Para una estructura interna de un libro usa `material_unit_number`; no la copies a
`selectors.unit_number`. Mantén `package_id`, página, `resource_ref` y cita. Sin libro
activo, busca ampliamente por curso, asignatura y OA.

Entrega una planificación clara y aplicable. El KG no compila ni valida el artefacto;
si la aplicación dispone de validadores propios, estos se ejecutan fuera del KG.
