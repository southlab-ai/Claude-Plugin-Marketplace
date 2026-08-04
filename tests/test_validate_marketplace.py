from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "validate_marketplace.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_repo(tmp_path: Path, *, source: str = "./plugins/example") -> Path:
    write_json(
        tmp_path / ".claude-plugin" / "marketplace.json",
        {"plugins": [{"name": "example", "version": "1.0.0", "source": source}]},
    )
    return tmp_path


def add_manifest(repo: Path, *, name: str = "example", version: str = "1.0.0") -> Path:
    plugin = repo / "plugins" / "example"
    write_json(plugin / ".claude-plugin" / "plugin.json", {"name": name, "version": version})
    return plugin


def run_guard(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda repo: None, "does not exist"),
        (lambda repo: (repo / "plugins" / "example").mkdir(parents=True), "missing manifest"),
    ],
)
def test_missing_source_or_manifest_fails(tmp_path: Path, setup, message: str) -> None:
    repo = make_repo(tmp_path)
    setup(repo)
    result = run_guard(repo)
    assert result.returncode == 1
    assert message in result.stderr


def test_manifest_without_component_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    plugin = add_manifest(repo)
    (plugin / "README.md").write_text("documentation only", encoding="utf-8")
    result = run_guard(repo)
    assert result.returncode == 1
    assert "has no plugin component" in result.stderr


@pytest.mark.parametrize(
    ("manifest_values", "field"),
    [({"name": "different"}, "name mismatch"), ({"version": "2.0.0"}, "version mismatch")],
)
def test_manifest_identity_mismatch_fails(tmp_path: Path, manifest_values: dict[str, str], field: str) -> None:
    repo = make_repo(tmp_path)
    plugin = add_manifest(repo, **manifest_values)
    (plugin / "skills").mkdir()
    (plugin / "skills" / "SKILL.md").write_text("component", encoding="utf-8")
    result = run_guard(repo)
    assert result.returncode == 1
    assert field in result.stderr


def test_duplicate_name_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    marketplace = repo / ".claude-plugin" / "marketplace.json"
    write_json(
        marketplace,
        {
            "plugins": [
                {"name": "example", "version": "1.0.0", "source": "./plugins/example"},
                {"name": "example", "version": "1.0.0", "source": "./plugins/second"},
            ]
        },
    )
    for directory in ("example", "second"):
        plugin = repo / "plugins" / directory
        write_json(plugin / ".claude-plugin" / "plugin.json", {"name": "example", "version": "1.0.0"})
        (plugin / ".mcp.json").write_text("{}", encoding="utf-8")
    result = run_guard(repo)
    assert result.returncode == 1
    assert "duplicates the name" in result.stderr


def test_valid_registry_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    plugin = add_manifest(repo)
    (plugin / "commands").mkdir()
    (plugin / "commands" / "hello.md").write_text("component", encoding="utf-8")
    result = run_guard(repo)
    assert result.returncode == 0, result.stderr


def test_unregistered_plugin_prototype_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    plugin = add_manifest(repo)
    (plugin / ".mcp.json").write_text("{}", encoding="utf-8")
    prototype = repo / "plugins" / "prototype"
    prototype.mkdir()
    (prototype / "README.md").write_text("work in progress", encoding="utf-8")
    result = run_guard(repo)
    assert result.returncode == 0, result.stderr


def test_original_failure_is_caught(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_json(
        repo / ".claude-plugin" / "marketplace.json",
        {
            "plugins": [
                {"name": "docs-only", "version": "1.0.0", "source": "./plugins/docs-only"},
                {"name": "missing", "version": "1.0.0", "source": "./plugins/missing"},
            ]
        },
    )
    docs_only = repo / "plugins" / "docs-only"
    write_json(
        docs_only / ".claude-plugin" / "plugin.json",
        {"name": "docs-only", "version": "1.0.0"},
    )
    (docs_only / "README.md").write_text("documentation only", encoding="utf-8")

    result = run_guard(repo)
    print(result.stderr, end="")
    print(f"exit code: {result.returncode}")
    assert result.returncode == 1
    assert "has no plugin component" in result.stderr
    assert "source './plugins/missing' does not exist" in result.stderr


def test_real_repository_passes() -> None:
    result = run_guard(REPO_ROOT)
    assert result.returncode == 0, result.stderr
