from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
VALIDATOR = PLUGIN_ROOT / "scripts" / "validate_plugin.py"


def test_published_plugin_contract_is_self_consistent() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--plugin-root", str(PLUGIN_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK kg-educacion ")


def _copy_publishable_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "marketplace"
    plugin = repo / "plugins" / "kg-educacion"
    shutil.copytree(PLUGIN_ROOT, plugin)
    for relative in (
        Path(".claude-plugin/marketplace.json"),
        Path(".agents/plugins/marketplace.json"),
        Path("README.md"),
        Path("CLAUDE.md"),
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)
    return repo, plugin


def _run_validator(plugin_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "validate_plugin.py")],
        check=False,
        capture_output=True,
        text=True,
    )


def test_codex_catalog_cannot_drop_the_plugin(tmp_path: Path) -> None:
    repo, plugin = _copy_publishable_repo(tmp_path)
    catalog_path = repo / ".agents" / "plugins" / "marketplace.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["plugins"] = [
        row for row in catalog["plugins"] if row["name"] != "kg-educacion"
    ]
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "marketplace Codex" in result.stderr


def test_public_readme_cannot_restore_the_legacy_tool_surface(tmp_path: Path) -> None:
    repo, plugin = _copy_publishable_repo(tmp_path)
    readme_path = repo / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8").replace(
            "cinco tools MCP v3", "siete tools MCP v3"
        ),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "superficie V3" in result.stderr


def test_plugin_cannot_persist_a_material_capability_header(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    mcp_path = plugin / ".mcp.json"
    mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    mcp["mcpServers"]["kg-educacion"]["headers"]["X-KG-Capability"] = (
        "${KG_CAPABILITY}"
    )
    mcp_path.write_text(json.dumps(mcp), encoding="utf-8")

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "capability efímera" in result.stderr


def test_reference_cannot_restore_the_internal_data_path(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    reference = plugin / "references" / "material-contract-1.0.md"
    reference.write_text(
        reference.read_text(encoding="utf-8").replace(
            "structuredContent.llm_context.result.source_text",
            "data.source_text",
        ),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "envelope MCP público" in result.stderr


def test_material_examples_are_validated_beyond_field_names(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    reference = plugin / "references" / "material-contract-1.0.md"
    reference.write_text(
        reference.read_text(encoding="utf-8")
        .replace('"teaching_activity"', '"not-a-component-kind"')
        .replace('"limit": 10', '"limit": 0'),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "schema material" in result.stderr


def test_material_selector_ids_use_the_canonical_enums(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    reference = plugin / "references" / "material-contract-1.0.md"
    reference.write_text(
        reference.read_text(encoding="utf-8").replace(
            '"subject": "Ciencias Naturales",',
            '"subject_family_id": "not-a-canonical-family",',
        ),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "selectors.subject_family_id contiene un enum inválido" in result.stderr


def test_direct_consumer_skills_must_remain_fail_closed(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    skill = plugin / "skills" / "planificar" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace(
            "no llames materiales", "llama materiales"
        ),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "fail-closed material" in result.stderr


def test_skill_body_cannot_exceed_the_authoring_budget(tmp_path: Path) -> None:
    _repo, plugin = _copy_publishable_repo(tmp_path)
    skill = plugin / "skills" / "planificar" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\n" + ("relleno " * 600),
        encoding="utf-8",
    )

    result = _run_validator(plugin)

    assert result.returncode == 1
    assert "500 palabras" in result.stderr
