---
name: crear-evaluacion
description: Crear evaluaciones y pruebas alineadas a OA del Currículum Nacional de Chile, balanceadas por demanda cognitiva (Bloom/DOK). Úsala cuando el usuario pida armar una prueba, evaluación, ensayo o set de ítems. Resuelve los OA, recupera el marco evaluativo, compila evidencia+spec con compile_artifact, TÚ generas los ítems y luego validate_artifact.
---

# Crear evaluaciones alineadas y balanceadas

Apoya al profesor a construir una evaluación válida usando el MCP `kg-educacion`.

**Paradigma v2 (PROMPT_ONLY):** el KG ya **no** genera contenido ni aloja un LLM. El KG **compila
evidencia oficial citada + una spec/PromptPacket**; **tú (Claude) generas** los ítems y la evaluación;
luego **se valida**. Todo es read-only y citado, la vista de estudiante va **sin clave**, y todo
requiere revisión humana antes de usarse en aula.

## Flujo recomendado
1. **Alcance**: curso, asignatura y qué OA o unidad se evalúa. Si falta, pregúntalo.
2. **Estado y cobertura**: `runtime_status` primero, para ver el estado del servidor y la cobertura
   curricular de tu solicitud antes de prometer una evaluación.
3. **OA a evaluar**: `resolve_curricular_targets` para resolver (asignatura, curso, OA explícitos /
   programa / unidad) al set de OA objetivo. Si es ambiguo (p. ej. dos programas para la misma
   asignatura+curso), pide aclaración antes de seguir.
4. **Marco evaluativo / demanda cognitiva**: `analyze_assessment_framework` para el marco oficial
   (SIMCE/PAES/DEMRE) de la familia EXACTA. Úsalo para **balancear** la prueba (recordar→crear, DOK 1-4):
   distingue siempre la distribución **oficial** de la **observada** y nunca presentes lo observado como oficial.
5. **Compilar evidencia + spec**: `compile_artifact` con `artifact_type` = `formative_assessment` o
   `summative_assessment`. Devuelve un **PromptPacket** (evidencia oficial citada + decisión pedagógica +
   spec/blueprint). El KG **no** redacta los ítems.
6. **Generación (tú)**: redacta los ítems alineados a cada OA, etiquetando el nivel Bloom/DOK objetivo,
   siguiendo el blueprint del PromptPacket. El MCP remoto **no** entrega ni ensambla ítems del banco
   fuente (eso es **auditoría local** y nunca se expone): **genera ítems originales**, no reutilices
   ítems fuente.
7. **Validación**: `validate_artifact` sobre lo que generaste — conformidad del blueprint, **ausencia de
   clave** en la vista de estudiante y no-reuso de ítems fuente. Nada es entregable sin pasar la validación.
   Si dudas del contrato de un tipo de artefacto, consulta `explain_artifact`.

## Buenas prácticas
- Alinea **cada ítem a un OA real** (código del grafo) y declara su nivel cognitivo.
- Balancea la demanda: combina niveles bajos (recordar/comprender) y altos (analizar/evaluar/crear)
  según lo que el OA exige, apoyándote en el marco de `analyze_assessment_framework`.
- Para evaluaciones tipo SIMCE/PAES, pide explícitamente el eje/habilidad y respeta su proporción oficial.
- Cita la fuente de cada OA (`query_curriculum` entrega resultados con cita). Si no hay evidencia, dilo
  en vez de inventar OA o códigos.
- Mantén dos vistas: estudiante (sin clave) y pauta (separada). La validación rechaza claves en la vista
  de estudiante.
- Si el MCP responde **401**, deriva a la skill `setup` para configurar el acceso.
