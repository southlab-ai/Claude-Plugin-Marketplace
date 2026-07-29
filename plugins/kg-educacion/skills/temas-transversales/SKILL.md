---
name: temas-transversales
description: Use when the user asks to connect Chilean curriculum across subjects, explore transversal themes, or design an interdisciplinary project grounded in OA and authorized teaching materials.
---

# Temas transversales

**REQUIRED REFERENCE FOR MATERIALS:** Read
[Subcontrato de materiales 1.0](../../references/material-contract-1.0.md) before
deciding whether the material tool is callable.

1. Normaliza por separado los OA de cada asignatura con
   `kg-educacion:resolve_curricular_targets`.
2. Recupera OA, habilidades y progresiones de cada asignatura con
   `kg-educacion:query_curriculum`.
3. En Claude/Codex directos, no llames materiales: usa currículum o evidencia
   legítimamente aportada por el usuario. Sólo en un consumidor que inyecta una
   capability válida, ejecuta un `search` separado por asignatura/OA; usa `catalog`
   para descubrir paquetes e hidrata sólo una cita exacta seleccionada.
4. Diseña el proyecto manteniendo cada OA atribuido a su asignatura, curso y fuente.

Una similitud temática no es una relación curricular declarada. Distingue evidencia
fuente de síntesis del modelo, conserva citas y no inventes OA. No mezcles cursores ni
materiales de asignaturas distintas en una sola búsqueda opaca. El KG recupera contexto;
el modelo construye el proyecto.
