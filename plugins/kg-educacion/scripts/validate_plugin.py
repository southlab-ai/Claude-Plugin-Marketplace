#!/usr/bin/env python3
"""Validate the publishable kg-educacion plugin as one coherent artifact."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
MATERIAL_CONSUMERS = {
    "buscar-recursos",
    "crear-evaluacion",
    "kg-overview",
    "planificar",
    "temas-transversales",
}
COMPONENT_KINDS = {
    "student_text",
    "teacher_guide",
    "workbook",
    "teaching_activity",
    "multimedia",
    "application",
    "other",
}
CONTENT_CLASSES = {
    "curriculum_basis",
    "study_plan",
    "study_program",
    "program_unit",
    "learning_objective",
    "evaluation_indicator",
    "assessment_framework",
    "planning_guidance",
    "student_text",
    "teacher_guide",
    "resource_activity_repository",
    "digital_activity_bank",
    "workbook",
    "activity",
    "assessment",
    "solution_key",
    "rubric",
    "reading",
    "video",
    "audio",
    "transcript",
    "application",
    "image",
    "normative_guidance",
    "professional_learning",
    "other",
}
MODALITIES = {
    "pdf",
    "html",
    "office",
    "image",
    "audio",
    "video",
    "application",
    "archive",
}
AVAILABILITY = {"available", "partial", "metadata_only", "blocked"}
SELECTOR_STRING_FIELDS = {
    "subject",
    "grade",
    "program_id",
    "program_slug",
    "unit_id",
    "unit_name",
}
SELECTOR_ENUMS = {
    "discipline_component_id": {"biologia", "fisica", "quimica"},
    "axis_id": {"lectura", "escritura", "comunicacion-oral"},
    "formation_type": {"FG", "HC", "TP", "AR"},
    "subject_family_id": {
        "lenguaje",
        "pueblos-originarios",
        "matematica",
        "ciencias",
        "historia-ciudadania",
        "ingles",
        "filosofia",
        "artes",
        "educacion-fisica-salud",
        "orientacion",
        "religion",
        "tecnologia",
        "administracion",
        "agropecuario",
        "alimentacion",
        "confeccion",
        "construccion",
        "electricidad",
        "grafico",
        "hoteleria-turismo",
        "maderero",
        "maritimo",
        "metalmecanica",
        "minero",
        "quimica-industria",
        "salud-educacion",
        "tecnologia-comunicaciones",
    },
    "program_variant_id": {
        "propuesta-curricular",
        "mencion-logistica",
        "mencion-recursos-humanos",
        "mencion-agricultura",
        "mencion-pecuaria",
        "mencion-vitivinicola",
        "mencion-cocina",
        "mencion-pasteleria-reposteria",
        "mencion-edificacion",
        "mencion-obras-viales-infraestructura",
        "mencion-terminaciones-construccion",
        "mencion-mantenimiento-electromecanico",
        "mencion-maquinas-herramientas",
        "mencion-matriceria",
        "mencion-laboratorio-quimico",
        "mencion-planta-quimica",
        "mencion-adulto-mayor",
        "mencion-enfermeria",
        "mencion-interpretacion-musical",
        "mencion-composicion-musical",
        "mencion-apreciacion-musical",
        "mencion-artes-visuales",
        "mencion-artes-audiovisuales",
        "mencion-diseno",
    },
    "curricular_module_id": {
        "bienestar-salud",
        "seguridad-prevencion-autocuidado",
        "ambiente-sostenibilidad",
        "tecnologia-sociedad",
        "chile-region-latinoamericana",
        "mundo-global",
        "educacion-fisica-salud-1",
        "educacion-fisica-salud-2",
    },
}
CURSOR_PATTERNS = {
    "catalog_cursor": re.compile(r"^catalog:v1:[A-Za-z0-9._~-]+$"),
    "search_cursor": re.compile(r"^search:v1:[A-Za-z0-9._~-]+$"),
    "index_cursor": re.compile(r"^index:v1:[A-Za-z0-9._~-]+$"),
}


class ValidationError(Exception):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: JSON inválido: {exc}") from exc


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    if not match:
        raise ValidationError(f"{path}: falta frontmatter YAML delimitado")
    raw, body = match.groups()
    if len(raw) > 1024:
        raise ValidationError(f"{path}: frontmatter excede 1024 caracteres")
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            raise ValidationError(f"{path}: frontmatter no es key: value")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, body


def _validate_manifest_versions(plugin_root: Path) -> str:
    repo_root = plugin_root.parents[1]
    claude = _load_json(plugin_root / ".claude-plugin" / "plugin.json")
    codex = _load_json(plugin_root / ".codex-plugin" / "plugin.json")
    marketplace = _load_json(repo_root / ".claude-plugin" / "marketplace.json")
    codex_marketplace = _load_json(
        repo_root / ".agents" / "plugins" / "marketplace.json"
    )
    entry = next(
        (
            item
            for item in marketplace.get("plugins", [])
            if item.get("name") == "kg-educacion"
        ),
        None,
    )
    if entry is None:
        raise ValidationError("kg-educacion no está en el marketplace Claude")
    codex_entry = next(
        (
            item
            for item in codex_marketplace.get("plugins", [])
            if item.get("name") == "kg-educacion"
        ),
        None,
    )
    expected_codex_entry = {
        "source": {"source": "local", "path": "./plugins/kg-educacion"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    }
    if codex_entry is None:
        raise ValidationError("kg-educacion no está en el marketplace Codex")
    for field, expected in expected_codex_entry.items():
        if codex_entry.get(field) != expected:
            raise ValidationError(
                f"marketplace Codex: {field} no coincide con {expected!r}"
            )

    versions = {
        "Claude manifest": claude.get("version"),
        "Codex manifest": codex.get("version"),
        "marketplace": entry.get("version"),
    }
    if len(set(versions.values())) != 1:
        raise ValidationError(f"versiones divergentes: {versions}")
    version = next(iter(versions.values()))
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValidationError(f"versión no semver: {version!r}")

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    claude_md = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    for label, text in {"README.md": readme, "CLAUDE.md": claude_md}.items():
        row = next(
            (
                line
                for line in text.splitlines()
                if line.startswith("|") and "kg-educacion" in line
            ),
            None,
        )
        if row is None or version not in row:
            raise ValidationError(f"{label}: tabla de kg-educacion no publica {version}")
        if label == "README.md" and (
            "cinco tools MCP v3" not in row
            or "siete tools" in row
            or "compilar artefactos" in row
        ):
            raise ValidationError(
                "README.md: la superficie V3 debe publicar cinco tools de retrieval"
            )
    return version


def _validate_skills(plugin_root: Path) -> None:
    skills_root = plugin_root / "skills"
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        fields, body = _frontmatter(skill_file)
        expected_name = skill_file.parent.name
        name = fields.get("name")
        description = fields.get("description", "")
        if name != expected_name or not SKILL_NAME.fullmatch(name or ""):
            raise ValidationError(
                f"{skill_file}: name debe coincidir con {expected_name!r}"
            )
        if not description.startswith("Use when "):
            raise ValidationError(f"{skill_file}: description debe comenzar con 'Use when '")
        if len(description) > 500:
            raise ValidationError(f"{skill_file}: description excede 500 caracteres")
        if len(body.splitlines()) >= 500:
            raise ValidationError(f"{skill_file}: cuerpo debe tener menos de 500 líneas")
        if len(re.findall(r"\S+", body)) > 500:
            raise ValidationError(f"{skill_file}: cuerpo excede 500 palabras")
        if "\\" in body:
            raise ValidationError(f"{skill_file}: usa rutas con slash, no backslash")
        if expected_name in MATERIAL_CONSUMERS and (
            "../../references/material-contract-1.0.md" not in body
        ):
            raise ValidationError(
                f"{skill_file}: falta referencia al subcontrato material 1.0"
            )
        if expected_name in MATERIAL_CONSUMERS and "no llames" not in body.lower():
            raise ValidationError(
                f"{skill_file}: falta el gate fail-closed material del plugin directo"
            )


def _validate_mcp_transport(plugin_root: Path) -> None:
    manifest = _load_json(plugin_root / ".mcp.json")
    expected = {
        "mcpServers": {
            "kg-educacion": {
                "type": "http",
                "url": "https://api.southlab.ai/mcp",
                "bearer_token_env_var": "KG_API_KEY",
                "headers": {"Authorization": "Bearer ${KG_API_KEY}"},
            }
        }
    }
    if manifest != expected:
        raise ValidationError(
            ".mcp.json: Claude y Codex deben usar KG_API_KEY sin capability persistida"
        )


def _validate_material_request(request: dict[str, Any], origin: str) -> None:
    def fail(message: str) -> None:
        raise ValidationError(f"{origin}: schema material: {message}")

    def nonempty_string(field: str) -> None:
        value = request.get(field)
        if not isinstance(value, str) or not value:
            fail(f"{field} debe ser un string no vacío")

    def string_array(
        field: str,
        *,
        allowed: set[str] | None = None,
        minimum: int = 0,
        maximum: int | None = None,
    ) -> None:
        value = request.get(field)
        if not isinstance(value, list) or len(value) < minimum:
            fail(f"{field} debe ser un array con al menos {minimum} elementos")
        if maximum is not None and len(value) > maximum:
            fail(f"{field} excede {maximum} elementos")
        if any(not isinstance(item, str) or not item for item in value):
            fail(f"{field} sólo admite strings no vacíos")
        if len(value) != len(set(value)):
            fail(f"{field} no admite duplicados")
        if allowed is not None and not set(value) <= allowed:
            fail(f"{field} contiene un enum inválido")

    version = request.get("material_contract_version")
    operation = request.get("operation")
    if version != "1.0":
        fail("material_contract_version debe ser 1.0")
    if "contract_version" in request and request["contract_version"] != "3.0":
        fail("contract_version debe ser 3.0")
    if operation not in {"catalog", "search", "index", "hydrate"}:
        fail("operation material inválida")

    common = {"material_contract_version", "contract_version", "operation"}
    filters = {
        "selectors",
        "package_id",
        "package_ids",
        "material_ids",
        "material_unit_number",
        "material_unit_kind",
        "material_unit_name",
        "component_kinds",
        "content_classes",
        "modalities",
        "availability",
    }
    allowed = {
        "catalog": common | filters | {"limit", "catalog_cursor"},
        "search": common | filters | {"query", "limit", "search_cursor"},
        "index": common | {"resource_ref", "limit", "index_cursor"},
        "hydrate": common | {"citation_id"},
    }[operation]
    extras = set(request) - allowed
    if extras:
        fail(f"campos inválidos para {operation}: {extras}")
    if {"package_id", "package_ids"} <= set(request):
        fail("package_id y package_ids son incompatibles")
    if operation == "catalog" and not ({"selectors", "material_ids"} & set(request)):
        fail("catalog requiere selectors o material_ids")
    for field in (
        "query",
        "package_id",
        "material_unit_kind",
        "material_unit_name",
        "resource_ref",
        "citation_id",
    ):
        if field in request:
            nonempty_string(field)
    for field in ("package_ids", "material_ids"):
        if field in request:
            string_array(field, minimum=1, maximum=100)
    for field, enum in (
        ("component_kinds", COMPONENT_KINDS),
        ("content_classes", CONTENT_CLASSES),
        ("modalities", MODALITIES),
        ("availability", AVAILABILITY),
    ):
        if field in request:
            string_array(field, allowed=enum)
    for field, minimum, maximum in (
        ("limit", 1, 200),
        ("material_unit_number", 1, 100),
    ):
        if field in request:
            value = request[field]
            if isinstance(value, bool) or not isinstance(value, int):
                fail(f"{field} debe ser integer")
            if not minimum <= value <= maximum:
                fail(f"{field} debe estar entre {minimum} y {maximum}")
    for field, pattern in CURSOR_PATTERNS.items():
        if field in request and (
            not isinstance(request[field], str)
            or pattern.fullmatch(request[field]) is None
        ):
            fail(f"{field} no coincide con su prefijo opaco")
    if "selectors" in request:
        selectors = request["selectors"]
        allowed_selectors = (
            SELECTOR_STRING_FIELDS
            | set(SELECTOR_ENUMS)
            | {"unit_number", "oa_codes"}
        )
        if (
            not isinstance(selectors, dict)
            or not selectors
            or not set(selectors) <= allowed_selectors
        ):
            fail("selectors debe ser un objeto no vacío con campos conocidos")
        for field in SELECTOR_STRING_FIELDS & set(selectors):
            if not isinstance(selectors[field], str) or not selectors[field]:
                fail(f"selectors.{field} debe ser un string no vacío")
        if "unit_number" in selectors:
            unit = selectors["unit_number"]
            if (
                isinstance(unit, bool)
                or not isinstance(unit, int)
                or not 1 <= unit <= 100
            ):
                fail("selectors.unit_number debe estar entre 1 y 100")
        if "oa_codes" in selectors:
            values = selectors["oa_codes"]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item for item in values)
                or len(values) != len(set(values))
            ):
                fail("selectors.oa_codes debe tener strings únicos no vacíos")
        for field, enum in SELECTOR_ENUMS.items():
            if field in selectors and selectors[field] not in enum:
                fail(f"selectors.{field} contiene un enum inválido")
    if operation == "search" and "query" not in request:
        fail("search requiere query")
    if operation == "index" and "resource_ref" not in request:
        fail("index requiere resource_ref")
    if operation == "hydrate" and "citation_id" not in request:
        fail("hydrate requiere citation_id")


def _validate_material_reference(plugin_root: Path) -> None:
    reference = plugin_root / "references" / "material-contract-1.0.md"
    text = reference.read_text(encoding="utf-8")
    if (
        "structuredContent.llm_context.result.source_text" not in text
        or "data.source_text" in text
    ):
        raise ValidationError(
            f"{reference}: usa el envelope MCP público, no la ruta interna data"
        )
    requests: list[dict[str, Any]] = []
    for number, raw in enumerate(JSON_BLOCK.findall(text), start=1):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{reference}: bloque JSON {number} inválido: {exc}") from exc
        if isinstance(value, dict) and "operation" in value:
            requests.append(value)
            _validate_material_request(value, f"{reference}: bloque JSON {number}")
    operations = {request["operation"] for request in requests}
    if operations != {"catalog", "search", "index", "hydrate"}:
        raise ValidationError(
            f"{reference}: ejemplos deben cubrir catalog/search/index/hydrate"
        )


def validate(plugin_root: Path) -> str:
    version = _validate_manifest_versions(plugin_root)
    _validate_mcp_transport(plugin_root)
    _validate_skills(plugin_root)
    _validate_material_reference(plugin_root)
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    try:
        version = validate(args.plugin_root.resolve())
    except (ValidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK kg-educacion {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
