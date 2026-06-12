---
name: planificar
description: Planificar el año, una unidad, una semana o una clase del Currículum Nacional de Chile usando OA oficiales, secuencias de unidades/clases y horas pedagógicas. Úsala cuando el usuario pida planificar, calendarizar o secuenciar enseñanza.
---

# Planificación curricular (año → unidad → clase)

Apoya al profesor a planificar usando el MCP `kg-educacion`. La planificación baja en cascada:
**año → mes → semana → día**, y el grafo tiene las piezas para cada nivel.

## Flujo recomendado
1. **Encuadre**: confirma curso y asignatura (ej. "Lenguaje 4° básico"). Si falta, pregúntalo.
2. **OA del curso**: `search` con la consulta de los OA de ese curso/asignatura para listar objetivos oficiales.
3. **Secuencia y horas**: `search` con términos como "secuencia de unidades" / "orden" para traer el
   pacing (horas pedagógicas por unidad, % del año) y el orden unidad→unidad.
4. **Clases**: `search` con "secuencia de clases" de la unidad para el orden clase→clase y los objetivos por clase.
5. **Cierre**: arma la planificación citando los OA y las horas oficiales. Si el colegio tiene menos
   semanas, redistribuye proporcionalmente y dilo.

## Buenas prácticas
- Usa los **códigos OA reales** que devuelve el grafo (ej. `LE04 OA 04`), nunca inventados.
- Para integrar varias asignaturas en una unidad, combina con la skill `temas-transversales`.
- Si el usuario pide nivelar al inicio del año, consulta las **progresiones** (`search` "progresión …")
  para saber qué OA del grado anterior se apoyan en los del actual.
- Cita siempre la fuente. Si no hay evidencia para algo, dilo.
