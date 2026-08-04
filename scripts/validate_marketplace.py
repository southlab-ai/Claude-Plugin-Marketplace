#!/usr/bin/env python3
"""Validate that every published Claude Code plugin is installable and useful."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MARKETPLACE_PATH = Path(".claude-plugin/marketplace.json")
COMPONENT_DIRECTORIES = ("skills", "commands", "agents", "hooks", "bin")
COMPONENT_FILES = (".mcp.json", ".lsp.json", "settings.json")


def load_json(path: Path, description: str, errors: list[str]) -> Any | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        errors.append(f"{path}: missing {description}; create it and add valid JSON.")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: cannot read {description} ({exc}); fix its permissions or encoding.")
    except json.JSONDecodeError as exc:
        errors.append(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON in {description} ({exc.msg}); fix the JSON syntax."
        )
    return None


def has_files(path: Path) -> bool:
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def has_component(plugin_dir: Path) -> bool:
    if any(has_files(plugin_dir / name) for name in COMPONENT_DIRECTORIES):
        return True
    return any((plugin_dir / name).is_file() for name in COMPONENT_FILES)


def entry_label(index: int, entry: Any) -> str:
    if isinstance(entry, dict) and isinstance(entry.get("name"), str):
        return f"plugins[{index}] ({entry['name']!r})"
    return f"plugins[{index}]"


def validate_marketplace(repo_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = repo_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        return [f"{repo_root}: repository root cannot be resolved ({exc}); pass an existing directory."]

    marketplace_path = root / MARKETPLACE_PATH
    marketplace = load_json(marketplace_path, "marketplace registry", errors)
    if marketplace is None:
        return errors
    if not isinstance(marketplace, dict) or not isinstance(marketplace.get("plugins"), list):
        return [
            f"{marketplace_path}: 'plugins' must be an array; add a plugins array containing plugin entries."
        ]

    seen_names: dict[str, int] = {}
    for index, entry in enumerate(marketplace["plugins"]):
        label = entry_label(index, entry)
        if not isinstance(entry, dict):
            errors.append(f"{marketplace_path}: {label} must be an object; replace it with a plugin entry object.")
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{marketplace_path}: {label} needs a non-empty string 'name'; add the plugin name.")
        elif name in seen_names:
            errors.append(
                f"{marketplace_path}: {label} duplicates the name from plugins[{seen_names[name]}]; "
                "remove or rename one entry so published names are unique."
            )
        else:
            seen_names[name] = index

        source = entry.get("source")
        if not isinstance(source, str) or not source:
            errors.append(f"{marketplace_path}: {label} needs a non-empty string 'source'; add a repository-relative directory path.")
            continue

        source_path = Path(source)
        if source_path.is_absolute():
            errors.append(
                f"{marketplace_path}: {label} source {source!r} is absolute; use a repository-relative plugin directory."
            )
            continue

        candidate = root / source_path
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError):
            errors.append(
                f"{marketplace_path}: {label} source {source!r} does not exist; create the plugin directory or remove the registry entry."
            )
            continue

        if not resolved.is_relative_to(root):
            errors.append(
                f"{marketplace_path}: {label} source {source!r} resolves outside the repository; move it inside the repository and update 'source'."
            )
            continue
        if not resolved.is_dir():
            errors.append(
                f"{marketplace_path}: {label} source {source!r} is not a directory; point 'source' at the plugin directory."
            )
            continue

        manifest_path = resolved / ".claude-plugin" / "plugin.json"
        manifest = load_json(manifest_path, f"manifest for {label}", errors)
        if manifest is None:
            continue
        if not isinstance(manifest, dict):
            errors.append(f"{manifest_path}: manifest for {label} must be a JSON object; replace it with a plugin manifest object.")
            continue

        for field in ("name", "version"):
            registry_value = entry.get(field)
            manifest_value = manifest.get(field)
            if registry_value != manifest_value:
                errors.append(
                    f"{manifest_path}: {label} {field} mismatch: registry has {registry_value!r}, manifest has {manifest_value!r}; "
                    f"set both {field} values to the same value."
                )

        if not has_component(resolved):
            formats = ", ".join((*COMPONENT_DIRECTORIES, *COMPONENT_FILES))
            errors.append(
                f"{resolved}: {label} has no plugin component; add a real component file under one of: {formats}, "
                "or remove the entry until the plugin is installable."
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (defaults to the parent of this script's directory)",
    )
    args = parser.parse_args(argv)
    errors = validate_marketplace(args.repo_root)
    marketplace = args.repo_root.resolve() / MARKETPLACE_PATH
    if errors:
        print(f"Marketplace validation failed with {len(errors)} problem(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Marketplace validation passed: all registered plugins in {marketplace} are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
