---
name: ordenar-repo
description: Instalar en un repositorio el orden documental que sobrevive a un cambio de agente — una sola fuente de verdad, la carpeta como clase, y un guard que falla si alguien copia un valor que caduca. Úsala cuando el usuario pida ordenar la documentación, dejar una fuente de verdad, evitar que los agentes desordenen el repo, o preparar un repositorio nuevo para trabajar con Claude Code y Codex.
---

# Ordenar un repositorio

Instala una estructura documental que **no depende de que el agente se acuerde**.

## El problema que resuelve, y por qué no es de documentación

Trabajas un rato con un agente, dejas el repo ordenado, y vuelves con otro —o con el mismo, tres
semanas después— y está desordenado otra vez.

**No se arregla escribiendo mejores instrucciones.** Un agente las lee al empezar, las comprime, y
a la tercera hora trabaja de memoria. Y al cambiar de agente, el segundo **no hereda lo que el
primero entendió: hereda el repositorio.**

Lo único que sobrevive a ese cambio es **lo que falla**. Ningún agente entrega con la suite en
rojo. Así que el orden no se pide: se convierte en un test.

## La única regla

> **Un documento no COPIA un valor que caduca. Lo referencia, o lo genera.**

Un valor que caduca es cualquiera que cambie con un despliegue: un id de release, un nombre de
colección, un hash de build, un conteo. Copiarlo lo separa de la realidad en el momento en que
cambia — y nadie se entera, porque el documento sigue leyéndose igual de bien.

Todo lo demás sale de ahí.

## Cómo se ejecuta

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_orden.py" --en . --dry-run
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_orden.py" --en .
```

Corre siempre `--dry-run` primero y **enséñale al usuario lo que va a cambiar**. El script no
borra nada y respeta los ficheros que ya existan.

## Qué instala

| | |
|---|---|
| `AGENTS.md` | las reglas, en un bloque delimitado y reinstalable. **Claude Code, Codex y Cursor leen este fichero** |
| `CLAUDE.md` | un **puntero** a AGENTS.md, no una copia |
| `docs/<9 clases>/` | la carpeta **es** la clase |
| `.orden.json` | lo único que sabe del dominio: qué caduca en *este* proyecto |
| `tests/docs/test_orden.py` | el guard genérico, que lee esa config |

## Después de instalar: rellenar `.orden.json`

Es el único paso que el script no puede hacer solo, y **es el que da valor a todo lo demás**.
Ayuda al usuario a llenarlo mirando su repositorio:

```json
{
  "valores_volatiles":  ["v3-curriculum-[0-9a-f]{12}", "knowledge_chunks_[a-z0-9_]+"],
  "simbolos_retirados": ["query_resources", "assemble_exam"]
}
```

**Cómo encontrarlos sin preguntar:**

- **valores volátiles** — busca en la documentación cadenas que se repitan con forma de
  identificador: ids de release, nombres de bucket o colección, tags de imagen, hashes.
  `grep -rhoE '[a-z0-9-]+-[0-9a-f]{8,}' docs/ | sort | uniq -c | sort -rn | head` suele
  destaparlos. Si el mismo patrón aparece con **valores distintos** en varios ficheros, ya
  encontraste una fuente de desorden: alguno miente.
- **símbolos retirados** — compara lo que la documentación nombra con lo que el código exporta
  hoy. Endpoints, tools, módulos o comandos que sólo existan en `docs/` son candidatos.

## Verificar

```bash
python3 -m pytest tests/docs/ -q
```

Si el repositorio ya tenía documentación, **esto va a fallar**, y eso es exactamente lo que se
quería: te está diciendo dónde estaba el desorden. Para arreglarlo hay una skill hermana,
`migrar-a-orden`, que lo hace en el orden correcto y sin reescribir historia.

## Lo que esta skill NO debe hacer

- **No reescribas historia para poner el guard verde.** Un plan o un recibo que nombra un valor
  caducado está diciendo la verdad sobre el día en que se escribió. Sólo se le exige llevar su
  fecha donde se vea.
- **No muevas ficheros ligados por hash.** Recibos, manifiestos y evidencia firmada registran sus
  propias rutas: renombrar su carpeta rompe la firma. Si un test se pone rojo al mover algo, esa
  es la señal — devuélvelo a su sitio.
- **No dupliques las instrucciones en `CLAUDE.md`.** Dos ficheros con las mismas reglas son dos
  fuentes de verdad, y una empieza a envejecer el día que alguien edita la otra.
