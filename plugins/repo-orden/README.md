# repo-orden

**Orden documental que sobrevive a un cambio de agente.**

Trabajas un rato con un agente, dejas el repositorio ordenado, y vuelves con otro —o con el
mismo, tres semanas después— y está desordenado otra vez. Documentos que se declaran autoridad,
cifras copiadas que ya no son ciertas, runbooks que nombran cosas retiradas.

## Por qué no se arregla con mejores instrucciones

Un agente lee las instrucciones al empezar, las comprime, y a la tercera hora trabaja de memoria.
Y cuando cambias de agente, **el segundo no hereda lo que el primero entendió: hereda el
repositorio.**

Lo único que sobrevive a ese cambio es **lo que falla**. Ningún agente entrega con la suite en
rojo.

Así que el orden no se pide: **se convierte en un test.**

## La única regla

> Un documento **no copia** un valor que caduca. Lo referencia, o lo genera.

Un valor que caduca es cualquiera que cambie con un despliegue: un id de release, un nombre de
colección, un hash de build, un conteo. Copiarlo lo separa de la realidad en el momento en que
cambia — y nadie se entera, porque el documento **sigue leyéndose igual de bien**.

De ahí sale todo lo demás: por eso hay un solo documento con derecho a hablar del presente, por
eso los runbooks no llevan literales, y por eso lo histórico lleva su fecha donde se ve.

## Las dos skills

| | |
|---|---|
| **`ordenar-repo`** | instala la estructura. Para un repo nuevo, o uno con poca documentación |
| **`migrar-a-orden`** | clasifica lo que ya hay sin reescribir historia, y deja los guards en verde |

## Qué instala

```
AGENTS.md                    las reglas, en un bloque delimitado y reinstalable
CLAUDE.md                    un PUNTERO a AGENTS.md, no una copia
docs/ESTADO.md               el único documento con derecho a describir el presente
docs/README.md               el mapa: qué clase manda sobre qué
docs/{contratos,arquitectura,adr,runbooks,handoff,pendientes,evidence,planes,archivo}/
.orden.json                  lo único que sabe de tu dominio: qué caduca aquí
tests/docs/test_orden.py     el guard genérico, que lee esa config
```

**La carpeta es la clase.** No hace falta leer un documento para saber qué autoridad tiene — que
es justamente lo que fallaba: el modo imperativo y las cifras exactas estaban tanto en los
documentos vivos como en los retirados.

## Por qué funciona igual con Claude Code y con Codex

Los dos leen **`AGENTS.md`**, y `CLAUDE.md` es un puntero de tres líneas para que no haya dos
fuentes de instrucciones. Pero eso es la mitad menos importante.

La mitad que de verdad funciona es que **Codex corre `pytest`**. Si `tests/docs/` está rojo, tiene
que arreglarlo antes de entregar. La regla deja de ser una petición y pasa a ser una condición de
salida — y eso no depende de qué agente sea, ni de cuánto contexto le quede.

## Lo que deliberadamente NO hace

- **No reescribe historia.** Un charter que cita el release sobre el que trabajó está diciendo la
  verdad; sólo se le exige llevar la fecha donde se vea. La regla se aplica a lo que habla del
  presente.
- **No toca lo ligado por hash.** Recibos y manifiestos firmados registran sus propias rutas:
  renombrar su carpeta rompe la firma, y regenerarlos para acomodar un renombrado cosmético es
  falsificar historia.
- **No borra.** Archiva y marca; `git mv`, nunca `rm`.

## Uso directo, sin skill

```bash
python3 scripts/bootstrap_orden.py --en /ruta/al/repo --dry-run
python3 scripts/bootstrap_orden.py --en /ruta/al/repo
python3 -m pytest tests/docs/ -q
```

## De dónde salió

De ordenar un repositorio real que tenía **160 documentos, 42.161 líneas y unos sesenta
declarándose autoridad**, de los cuales **49 contradecían producción**. Los cinco runbooks
nombraban releases retirados; ninguno el vivo. Y el propio documento que se declaraba fuente de
verdad llegó a nombrar **seis release ids distintos**, ninguno el que se estaba sirviendo.

Cada regla de este plugin corresponde a un defecto que se midió allí.
