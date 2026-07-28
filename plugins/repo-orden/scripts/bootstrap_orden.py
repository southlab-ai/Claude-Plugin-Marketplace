#!/usr/bin/env python3
"""Instalar en cualquier repositorio el orden que sobrevive a un cambio de agente.

## El problema que resuelve

Trabajas un rato con un agente, dejas el repo ordenado, y vuelves con otro —o con el mismo, tres
semanas después— y está desordenado otra vez. Documentos que se declaran autoridad, cifras
copiadas que ya no son ciertas, runbooks que nombran cosas retiradas.

**No se arregla escribiendo mejores instrucciones.** Un agente lee las instrucciones al empezar,
las comprime, y a la tercera hora está trabajando de memoria. Lo comprobamos midiendo un repo
real el 2026-07-28: 160 documentos, ~60 declarándose autoridad, **49 contradiciendo producción**,
y los cinco runbooks nombrando releases retirados.

**Lo que sí sobrevive es lo que FALLA.** Ningún agente ignora un test rojo, porque no puede
entregar con la suite en rojo. Así que el orden no se pide: se convierte en un test.

## Qué instala

    AGENTS.md          las reglas, cortas y numeradas. Claude Code, Codex y Cursor lo leen.
    CLAUDE.md          un puntero de tres líneas a AGENTS.md, para que no haya dos fuentes.
    docs/README.md     el mapa: qué clase de documento manda sobre qué
    docs/<clases>/     las carpetas; la carpeta ES la clase
    .orden.json        la configuración por proyecto: qué valores caducan aquí
    tests/docs/        el guard, que lee `.orden.json` y no sabe nada de tu dominio

## La única regla que hay que entender

**Un documento no puede COPIAR un valor que caduca.** Lo referencia, o lo genera.

Todo lo demás sale de ahí: por eso hay un solo documento con derecho a hablar del presente, por
eso los runbooks no llevan literales, y por eso lo histórico lleva su fecha donde se ve.

## Uso

    python3 tools/bootstrap_orden.py --en /ruta/al/repo
    python3 tools/bootstrap_orden.py --en . --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CLASES = {
    "adr": "el porqué de una decisión, nunca el ahora. Se supersede, no se edita",
    "arquitectura": "cómo es algo. La forma sí; las cifras que caducan no",
    "contratos": "manda sobre el código. Cede ante el estado en toda cifra",
    "runbooks": "se EJECUTA, así que es lo más peligroso: ningún valor literal",
    "handoff": "lo que un consumidor externo debe saber. Fechado",
    "pendientes": "lo que falta, con su número",
    "evidence": "recibos congelados. Ninguna autoridad sobre el presente",
    "planes": "trabajo futuro. Un plan ejecutado NO describe lo que quedó",
    "archivo": "cero autoridad. Prohibido citarlo desde código o desde un doc vivo",
}

#: Las clases que hablan del presente. Copiar un valor volátil aquí es lo que envejece.
#: `planes/` y `evidence/` quedan fuera a propósito: son registros de algo que pasó, y reescribir
#: la historia para poner un guard verde es peor que el defecto que se quería cazar.
DEL_PRESENTE = ["contratos", "arquitectura", "runbooks", "pendientes", "handoff"]

CONFIG_POR_DEFECTO = {
    "_comentario": [
        "Que caduca EN ESTE PROYECTO. El guard es generico; esta lista es lo unico que sabe",
        "de tu dominio. Anade aqui los patrones de los valores que cambian con cada despliegue:",
        "ids de release, nombres de coleccion, hashes de build, urls de entorno.",
    ],
    "documento_de_estado": "docs/ESTADO.md",
    "valores_volatiles": [],
    "simbolos_retirados": [],
    "clases_del_presente": DEL_PRESENTE,
}

AGENTS_BLOQUE = """
<!-- ORDEN:INICIO — instalado por tools/bootstrap_orden.py. Lo verifica tests/docs/. -->
## Cómo está ordenado este repositorio

**Lee primero [`docs/ESTADO.md`](docs/ESTADO.md).** Es el único documento con derecho a describir
el presente. Si algo de este fichero lo contradice, gana ESTADO y esto está desactualizado.

**La regla, y de ella sale todo lo demás:**

> Un documento **no copia** un valor que caduca. Lo referencia, o lo genera.

Un valor que caduca es cualquiera que cambie con un despliegue: un id de release, un nombre de
colección, un hash de build, un conteo. Copiarlo en un documento lo separa de la realidad en el
momento en que cambia — y nadie se entera, porque el documento sigue leyéndose igual de bien.

**La carpeta es la clase.** No hace falta leer un documento para saber qué autoridad tiene:

| carpeta | qué es | ¿puede afirmar el presente? |
|---|---|---|
| `docs/ESTADO.md` | el estado | **sí, y es el único** |
| `docs/contratos/` | manda sobre el código | reglas sí, cifras no |
| `docs/arquitectura/` | cómo es algo | forma sí, cifras no |
| `docs/adr/` | por qué se decidió así | no |
| `docs/runbooks/` | se ejecuta | **ningún valor literal** |
| `docs/handoff/` | para consumidores externos | fechado |
| `docs/pendientes/` | lo que falta | no |
| `docs/evidence/` | recibos congelados | no |
| `docs/planes/` | trabajo futuro | no |
| `docs/archivo/` | historia | **ninguna** |

**Antes de crear un documento, pregúntate si lo que vas a escribir caduca.** Si caduca con un
despliegue va en ESTADO y se genera; si describe algo que pasó lleva la fecha en el nombre; si ya
no volverá va a `archivo/`.

**Esto no es una recomendación: hay un guard.** `python3 -m pytest tests/docs/ -q` falla si copias
una cifra volátil fuera de ESTADO, si dejas un enlace roto, si citas el archivo desde un documento
vivo o si sueltas un fichero en la raíz de `docs/`. Córrelo antes de entregar.
<!-- ORDEN:FIN -->
"""

CLAUDE_MD = """# CLAUDE.md

Este repositorio usa `AGENTS.md` como fichero canónico de instrucciones para agentes.

Existe este puntero, y no una copia, por la misma razón que gobierna todo lo demás aquí: **dos
ficheros con las mismas instrucciones son dos fuentes de verdad**, y una de las dos empieza a
envejecer el día que alguien edita la otra.

Ver [AGENTS.md](AGENTS.md).
"""

GUARD = '''"""El orden del repositorio, como test. Generado por `tools/bootstrap_orden.py`.

POR QUE ESTO ES UN TEST Y NO UN DOCUMENTO
------------------------------------------
Un agente lee las instrucciones al empezar, las comprime, y a las tres horas trabaja de memoria.
Y cuando cambias de agente —de Claude Code a Codex y vuelta— el segundo no hereda nada de lo que
el primero entendio: hereda el repositorio.

Lo unico que sobrevive a ese cambio es lo que FALLA. Ningun agente entrega con la suite en rojo.

Este fichero no sabe nada de tu dominio: lee `.orden.json`. Copialo tal cual a otro repositorio y
ajusta solo esa configuracion.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
CONFIG = json.loads((REPO / ".orden.json").read_text(encoding="utf-8"))

ESTADO = REPO / CONFIG["documento_de_estado"]
VOLATILES = [re.compile(p) for p in CONFIG["valores_volatiles"]]
RETIRADOS = CONFIG["simbolos_retirados"]
DEL_PRESENTE = tuple(CONFIG["clases_del_presente"])


def _vivos() -> list[Path]:
    """Todo .md salvo el archivo, que por definicion no habla del presente."""
    return [p for p in sorted(DOCS.rglob("*.md")) if "archivo" not in p.relative_to(DOCS).parts]


def _del_presente() -> list[Path]:
    return [p for p in _vivos() if p.relative_to(DOCS).parts[0] in DEL_PRESENTE]


def test_ningun_documento_del_presente_copia_un_valor_volatil() -> None:
    """La regla que gobierna todo lo demas.

    Un valor que caduca, copiado, se separa de la realidad en el momento en que cambia — y nadie
    se entera, porque el documento sigue leyendose igual de bien.
    """
    if not VOLATILES:
        pytest.skip("`.orden.json` no declara valores volatiles todavia")
    ofensores = [
        f"{p.relative_to(REPO)}: {v}"
        for p in [*_del_presente(), REPO / "AGENTS.md", REPO / "README.md"]
        if p.exists()
        for patron in VOLATILES
        for v in sorted(set(patron.findall(p.read_text(encoding="utf-8", errors="replace"))))
    ]
    assert ofensores == [], (
        "valores que caducan, copiados fuera del documento de estado:\\n  "
        + "\\n  ".join(ofensores[:10])
        + "\\n\\nReferencialos o generalos; no los copies."
    )


def test_ningun_documento_vivo_nombra_algo_retirado() -> None:
    """Nombrar una tool o un modulo que ya no existe hace que un agente escriba codigo que falla.

    Nombrarlo para decir que NO existe es legitimo, y necesario.
    """
    if not RETIRADOS:
        pytest.skip("`.orden.json` no declara simbolos retirados todavia")
    ofensores: list[str] = []
    for p in _del_presente():
        texto = p.read_text(encoding="utf-8", errors="replace")
        for simbolo in RETIRADOS:
            if simbolo in texto and not re.search(
                rf"(no existe|ya no|retirad|muerta|inexistente)[^\\n]{{0,80}}{re.escape(simbolo)}"
                rf"|{re.escape(simbolo)}[^\\n]{{0,80}}(no existe|ya no|retirad|muerta|inexistente)",
                texto, re.I,
            ):
                ofensores.append(f"{p.relative_to(REPO)}: {simbolo}")
    assert ofensores == [], (
        "documentos vivos que nombran algo retirado sin decir que lo esta:\\n  "
        + "\\n  ".join(ofensores[:10])
    )


def test_todo_enlace_relativo_resuelve() -> None:
    """Un puntero roto es la senal que decidiria que documento manda, perdida."""
    rotos = [
        f"{p.relative_to(REPO)} -> {destino}"
        for p in _vivos()
        for destino in re.findall(r"\\]\\(([^)#][^)]*\\.md)(?:#[^)]*)?\\)",
                                  p.read_text(encoding="utf-8", errors="replace"))
        if not destino.startswith(("http://", "https://"))
        and not (p.parent / destino).resolve().exists()
    ]
    assert rotos == [], "enlaces rotos:\\n  " + "\\n  ".join(rotos[:12])


def test_ningun_documento_vivo_cita_el_archivo() -> None:
    """El archivo existe para que nadie lo confunda con el presente.

    Enlazarlo desde un documento vigente deshace exactamente eso.
    """
    ofensores = [
        f"{p.relative_to(REPO)} -> {d}"
        for p in _vivos()
        for d in re.findall(r"\\]\\(([^)]+\\.md)\\)", p.read_text(encoding="utf-8", errors="replace"))
        if "archivo/" in d and p.name != "README.md"
    ]
    assert ofensores == [], "documentos vivos que enlazan al archivo:\\n  " + "\\n  ".join(ofensores[:8])


def test_todo_archivado_lleva_su_aviso_en_la_primera_linea() -> None:
    """Tiene que verse en cualquier fragmento recuperado, no solo abriendo el fichero."""
    archivo = DOCS / "archivo"
    if not archivo.is_dir():
        pytest.skip("este repositorio todavia no tiene docs/archivo/")
    sin_aviso = [
        str(p.relative_to(REPO)) for p in sorted(archivo.rglob("*.md"))
        if "DOCUMENTO ARCHIVADO" not in p.read_text(encoding="utf-8", errors="replace")[:400]
    ]
    assert sin_aviso == [], "archivados sin aviso:\\n  " + "\\n  ".join(sin_aviso[:10])


def test_la_raiz_de_docs_solo_tiene_el_estado_y_el_mapa() -> None:
    """Un documento suelto en la raiz se lee como de primer nivel.

    Asi es como un repositorio llega a tener sesenta autoridades: cada uno se puso ahi por una
    buena razon, y ninguno dice cual es su clase.
    """
    sueltos = sorted(p.name for p in DOCS.glob("*.md"))
    assert sueltos == ["ESTADO.md", "README.md"], f"ficheros sueltos en docs/: {sueltos}"


def test_agents_publica_las_reglas_y_claude_no_las_duplica() -> None:
    """Los dos agentes convergen en AGENTS.md; CLAUDE.md solo apunta.

    Dos ficheros con las mismas instrucciones son dos fuentes de verdad, y una empieza a
    envejecer el dia que alguien edita la otra.
    """
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- ORDEN:INICIO" in agents and "<!-- ORDEN:FIN -->" in agents, (
        "AGENTS.md perdio el bloque de reglas; reinstalalo con tools/bootstrap_orden.py"
    )
    claude = REPO / "CLAUDE.md"
    if claude.exists():
        texto = claude.read_text(encoding="utf-8")
        assert len(texto.splitlines()) < 20 and "AGENTS.md" in texto, (
            "CLAUDE.md dejo de ser un puntero: ahora hay dos fuentes de instrucciones"
        )
'''


def instalar(raiz: Path, dry_run: bool) -> list[str]:
    hechos: list[str] = []

    def escribir(rel: str, contenido: str, solo_si_falta: bool = False) -> None:
        destino = raiz / rel
        if solo_si_falta and destino.exists():
            hechos.append(f"  = {rel} (ya existe, no se toca)")
            return
        hechos.append(f"  {'+' if not destino.exists() else '~'} {rel}")
        if not dry_run:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")

    for clase, descripcion in CLASES.items():
        carpeta = raiz / "docs" / clase
        if not carpeta.exists():
            hechos.append(f"  + docs/{clase}/")
            if not dry_run:
                carpeta.mkdir(parents=True, exist_ok=True)
                (carpeta / ".gitkeep").write_text(f"# {descripcion}\n", encoding="utf-8")

    escribir(".orden.json", json.dumps(CONFIG_POR_DEFECTO, ensure_ascii=False, indent=2) + "\n",
             solo_si_falta=True)
    escribir("tests/docs/test_orden.py", GUARD)
    escribir("CLAUDE.md", CLAUDE_MD, solo_si_falta=True)

    agents = raiz / "AGENTS.md"
    texto = agents.read_text(encoding="utf-8") if agents.exists() else "# AGENTS.md\n"
    if "<!-- ORDEN:INICIO" in texto:
        import re as _re
        texto = _re.sub(r"<!-- ORDEN:INICIO.*?<!-- ORDEN:FIN -->", AGENTS_BLOQUE.strip(), texto, flags=_re.S)
        hechos.append("  ~ AGENTS.md (bloque de orden actualizado)")
    else:
        texto = texto.rstrip() + "\n\n" + AGENTS_BLOQUE
        hechos.append("  + AGENTS.md (bloque de orden añadido)")
    if not dry_run:
        agents.write_text(texto, encoding="utf-8")

    return hechos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", required=True, type=Path, help="raíz del repositorio destino")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raiz = args.en.resolve()
    if not raiz.is_dir():
        raise SystemExit(f"no existe: {raiz}")

    print(f"{'(simulacro) ' if args.dry_run else ''}instalando el orden en {raiz}\n")
    for linea in instalar(raiz, args.dry_run):
        print(linea)

    print(f"""
Siguiente paso, y es el único que no puedo hacer por ti: **rellena `.orden.json`**.

    "valores_volatiles":  los patrones de lo que caduca AQUÍ. Ejemplos reales:
                          "v3-curriculum-[0-9a-f]{{12}}"   un id de release
                          "knowledge_chunks_[a-z0-9_]+"   una colección
                          "sha256:[0-9a-f]{{64}}"          un hash de build
    "simbolos_retirados": tools, endpoints o módulos que ya no existen y que un agente
                          podría seguir llamando porque los leyó en un documento viejo

Con eso, `python3 -m pytest tests/docs/ -q` empieza a parar el desorden en vez de describirlo.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
