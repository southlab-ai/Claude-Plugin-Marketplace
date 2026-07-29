from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "kg-onboard.sh"
TEST_KEY = "kg-secret-test-key"


def _fake_environment(tmp_path: Path, *, codex_state: str | None = None) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        """#!/bin/sh
case "$*" in
  *"/account/register"*) printf '{}\\n200\\n' ;;
  *"/account/keys"*) printf '{"api_key":"kg-secret-test-key"}\\n' ;;
  *) exit 99 ;;
esac
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    uname = fake_bin / "uname"
    uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n", encoding="utf-8")
    uname.chmod(0o755)
    if codex_state is not None:
        codex = fake_bin / "codex"
        codex.write_text(
            """#!/bin/sh
log="${CODEX_TEST_LOG:?}"
case "$1 $2 $3" in
  "mcp get kg-educacion")
    if [ "${CODEX_TEST_STATE}" = "missing" ]; then exit 1; fi
    case "${CODEX_TEST_STATE}" in
      current)
        printf '{"enabled":true,"transport":{"type":"streamable_http","url":"https://kg.invalid/mcp","bearer_token_env_var":"KG_API_KEY","http_headers":null,"env_http_headers":null}}\\n'
        ;;
      disabled)
        printf '{"enabled":false,"transport":{"type":"streamable_http","url":"https://kg.invalid/mcp","bearer_token_env_var":"KG_API_KEY","http_headers":null,"env_http_headers":null}}\\n'
        ;;
      capability)
        printf '{"enabled":true,"transport":{"type":"streamable_http","url":"https://kg.invalid/mcp","bearer_token_env_var":"KG_API_KEY","http_headers":{"X-KG-Capability":"copied"},"env_http_headers":null}}\\n'
        ;;
      *)
        printf '{"enabled":true,"transport":{"type":"streamable_http","url":"https://old.invalid/mcp","bearer_token_env_var":"OLD_KEY","http_headers":null,"env_http_headers":null}}\\n'
        ;;
    esac
    ;;
  "mcp remove kg-educacion") printf 'remove\\n' >>"$log" ;;
  "mcp add kg-educacion") printf '%s\\n' "$*" >>"$log" ;;
  *) exit 99 ;;
esac
""",
            encoding="utf-8",
        )
        codex.chmod(0o755)
    return {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "KG_API_BASE": "https://kg.invalid",
        "CODEX_TEST_STATE": codex_state or "",
        "CODEX_TEST_LOG": str(tmp_path / "codex.log"),
    }


def _run(
    tmp_path: Path,
    *extra_args: str,
    codex_state: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "/bin/bash",
            str(SCRIPT),
            "kg-inv-test",
            "teacher@example.test",
            "teacher",
            *extra_args,
        ],
        input="chosen-password\n",
        check=False,
        capture_output=True,
        text=True,
        env=_fake_environment(tmp_path, codex_state=codex_state),
    )


def test_invalid_claude_settings_are_preserved_before_registration(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "home" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{broken", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode != 0
    assert settings.read_text(encoding="utf-8") == "{broken"
    assert TEST_KEY not in result.stdout
    assert TEST_KEY not in result.stderr


def test_password_is_not_accepted_as_a_command_line_argument(tmp_path: Path) -> None:
    result = _run(tmp_path, "leaked-password")

    assert result.returncode != 0
    assert "contraseña" in result.stderr


def test_success_persists_but_never_prints_the_api_key(tmp_path: Path) -> None:
    zshrc = tmp_path / "home" / ".zshrc"
    zshrc.parent.mkdir(parents=True)
    zshrc.write_text("export EXISTING=value\n", encoding="utf-8")
    zshrc.chmod(0o644)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert TEST_KEY not in result.stdout
    assert TEST_KEY not in result.stderr
    settings = json.loads(
        (tmp_path / "home" / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["KG_API_KEY"] == TEST_KEY
    assert zshrc.read_text(encoding="utf-8") == (
        f"export EXISTING=value\nexport KG_API_KEY={TEST_KEY}\n"
    )
    assert stat.S_IMODE(zshrc.stat().st_mode) == 0o600


def test_shell_rc_symlink_is_rejected_before_any_local_write(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("untouched\n", encoding="utf-8")
    (home / ".zshrc").symlink_to(victim)

    result = _run(tmp_path)

    assert result.returncode != 0
    assert "enlace simbólico" in result.stderr
    assert victim.read_text(encoding="utf-8") == "untouched\n"
    assert not (home / ".claude" / "settings.json").exists()


def test_claude_settings_symlink_is_rejected_before_network(tmp_path: Path) -> None:
    settings_dir = tmp_path / "home" / ".claude"
    settings_dir.mkdir(parents=True)
    victim = tmp_path / "victim-settings"
    victim.write_text('{"untouched": true}\n', encoding="utf-8")
    (settings_dir / "settings.json").symlink_to(victim)

    result = _run(tmp_path)

    assert result.returncode != 0
    assert "enlace simbólico" in result.stderr
    assert victim.read_text(encoding="utf-8") == '{"untouched": true}\n'


def test_stale_codex_registration_is_replaced_and_verified(tmp_path: Path) -> None:
    result = _run(tmp_path, codex_state="stale")

    assert result.returncode == 0, result.stdout + result.stderr
    log = (tmp_path / "codex.log").read_text(encoding="utf-8").splitlines()
    assert log[0] == "remove"
    assert log[1] == (
        "mcp add kg-educacion --url https://kg.invalid/mcp "
        "--bearer-token-env-var KG_API_KEY"
    )


def test_current_codex_registration_is_preserved(tmp_path: Path) -> None:
    result = _run(tmp_path, codex_state="current")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "codex.log").exists()


def test_disabled_codex_registration_is_replaced(tmp_path: Path) -> None:
    result = _run(tmp_path, codex_state="disabled")

    assert result.returncode == 0, result.stdout + result.stderr
    log = (tmp_path / "codex.log").read_text(encoding="utf-8").splitlines()
    assert log[0] == "remove"
    assert log[1].startswith("mcp add kg-educacion ")


def test_codex_registration_with_persisted_capability_is_replaced(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, codex_state="capability")

    assert result.returncode == 0, result.stdout + result.stderr
    log = (tmp_path / "codex.log").read_text(encoding="utf-8").splitlines()
    assert log[0] == "remove"
    assert log[1].startswith("mcp add kg-educacion ")
