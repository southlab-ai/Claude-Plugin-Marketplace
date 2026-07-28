---
name: migrar-a-orden
description: Migrar un repositorio que ya tiene documentación acumulada al orden de una sola fuente de verdad — clasificar lo que hay, archivar lo histórico sin reescribirlo, y dejar los guards en verde. Úsala cuando el repo ya tenga docs/ con muchos ficheros, cuando la documentación contradiga a producción, o cuando el usuario diga que los agentes le desordenan el proyecto.
---

# Migrar un repositorio que ya tiene historia

Instalar la estructura en un repo vacío es trivial. **Lo difícil es un repo con 160 documentos
donde sesenta se declaran autoridad y cuarenta y nueve mienten** — y ahí la tentación es borrar,
que es el error.

## Antes de tocar nada: mide

El diagnóstico define la solución, y casi siempre sorprende. Mide **al menos** esto y enséñaselo
al usuario:

```bash
find docs -name '*.md' | wc -l                                    # cuántos hay
find docs -name '*.md' -exec cat {} + | wc -l                     # cuánto pesan
grep -rl 'fuente de verdad\|source of truth\|EL CONTRATO' docs/   # cuántos se declaran autoridad
find docs -name '*.md' -mtime +30 | wc -l                         # cuánto es sedimento
```

Y lo que de verdad importa: **¿qué de todo eso es ejecutable?** Un runbook no se lee, **se
ejecuta**, así que un runbook desactualizado hace daño de verdad. Cruza cada valor que citen
contra el sistema vivo.

> En un repositorio real esa medición dio: 160 documentos, 42.161 líneas, ~60 autoridades,
> **49 contradiciendo producción** — y los **cinco** runbooks nombrando releases retirados,
> ninguno el vivo.

## El orden de la migración, y por qué es ese

### 1 · Arregla la fuente de verdad antes que nada

Si existe un documento que se declara la verdad, **compruébalo primero**. Suele ser el más
desactualizado de todos, precisamente porque todo el mundo confía en él y nadie lo verifica.

Si contiene valores que caducan, no los corrijas a mano: **haz que se generen**. Un bloque
delimitado que un script rellena preguntándole al sistema, y un `--check` que falla si dejan de
coincidir.

### 2 · Instala la estructura

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_orden.py" --en . --dry-run
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_orden.py" --en .
```

### 3 · Clasifica lo que ya hay, y **usa `git mv`**

La clase la da la carpeta. Para cada documento pregúntate **una sola cosa: ¿esto caduca?**

| si el documento… | va a |
|---|---|
| describe qué está desplegado ahora | el documento de estado (y se genera) |
| manda sobre el código | `contratos/` |
| describe cómo es algo | `arquitectura/` |
| explica por qué se decidió algo | `adr/` |
| se **ejecuta** | `runbooks/` — y **sin un solo valor literal** |
| le habla a un consumidor externo | `handoff/` |
| lista lo que falta | `pendientes/` |
| es el recibo de una medición | `evidence/`, con la fecha en el nombre |
| es un plan o un charter | `planes/` |
| ya pasó y no volverá | `archivo/` |

**Un charter ejecutado no describe lo que quedó.** Va a `planes/`, no a arquitectura.
**Una auditoría fechada es evidencia**, aunque hable de la arquitectura.

### 4 · Marca el archivo en la PRIMERA línea

```
> **DOCUMENTO ARCHIVADO.** No describe el sistema desplegado y no debe copiarse a un
> runtime, a un paquete de consumidor ni a una decisión. Estado vivo: docs/ESTADO.md
```

Tiene que verse en **cualquier fragmento recuperado**, no sólo abriendo el fichero. Un archivado
puede imitar tan bien a un vivo que su título sea literalmente `# AGENTS.md`.

### 5 · Reapunta los enlaces, no los borres

Mover ficheros rompe enlaces. Un puntero roto es **la señal que decidiría qué documento manda,
perdida**. Reapúntalos por nombre de fichero; si un nombre es ambiguo, resuélvelo a mano.

### 6 · Deja los guards en verde, uno a uno

Cada fallo te está enseñando dónde estaba el desorden. **Léelo antes de arreglarlo.**

## Las tres trampas, y las tres las he pisado

### No reescribas la historia para poner un guard verde

Un ADR que nombra una tool retirada **describe correctamente el mundo en que se decidió**. Un
charter que cita el release sobre el que trabajó está diciendo la verdad. Reescribirlos pierde la
trazabilidad de qué se midió contra qué — y eso vale más que un test verde.

La regla se aplica a **lo que habla del presente**. A lo histórico sólo se le exige llevar su
fecha donde se vea.

### No muevas lo que está ligado por hash

Recibos, manifiestos y evidencia firmada **registran sus propias rutas dentro de la firma**.
Renombrar su carpeta rompe la cadena, y regenerar el recibo para acomodar un renombrado cosmético
es falsificar historia.

**Si un test se pone rojo al mover algo, esa es la señal.** Devuélvelo a su nombre original; casi
siempre el nombre viejo ya marcaba su clase con claridad.

### Un guard puede convertirse en el guardián del defecto

Cuando arregles una duplicación, **busca el test que la exigía**. Es más común de lo que parece:

- un test que exige que dos ficheros copien el mismo id de release
- un test que afirma que un hueco sigue abierto, escrito cuando lo estaba

Ese test no envejece solo: hay que darle la vuelta a mano, y hay que **buscarlo**, porque hasta
que lo haces te está impidiendo el arreglo con cara de estar protegiéndote.

## Al terminar

```bash
python3 -m pytest tests/docs/ -q
```

Y enséñale al usuario el antes y el después con números, no con adjetivos:

```
releases copiados fuera del estado    5  →  0
enlaces rotos                        20  →  0
documentos en la raíz de docs/       13  →  2
```
