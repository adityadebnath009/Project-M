"""
Unit tests for Project-M CLI commands and setup automation.
"""

import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from project_m.cli import main
from project_m.setup import configure_codex, configure_json_client, run_setup


@pytest.fixture
def runner() -> CliRunner:
    """Fixture providing Click's CLI test runner."""
    return CliRunner()


def test_cli_help(runner: CliRunner):
    """Verifies that the root help menu displays all commands."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "board" in result.output
    assert "status" in result.output
    assert "run" in result.output
    assert "export" in result.output
    assert "setup" in result.output
    assert "fetch" in result.output
    assert "shell" in result.output


def test_cli_fetch(runner: CliRunner):
    """Verifies that project-m fetch renders the Fastfetch screen."""
    result = runner.invoke(main, ["fetch"])
    assert result.exit_code == 0
    assert "Engine:" in result.output
    assert "Storage:" in result.output
    assert "4-Tier Lossless State Compiler" in result.output


def test_cli_default_invocation_launches_shell(runner: CliRunner):
    """Verifies that running project-m with no arguments launches the interactive shell."""
    result = runner.invoke(main, [], input="/help\n/exit\n")
    assert result.exit_code == 0
    assert "REPL ACTIVE" in result.output
    assert "Engine:" in result.output
    assert "Project-M Shell Commands" in result.output
    assert "Goodbye!" in result.output


def test_cli_shell_command(runner: CliRunner):
    """Verifies project-m shell with task and decision commands."""
    commands = (
        "/task test-t1 in_progress @claude 'Testing shell'\n"
        "/decide ADR-T1 'Test Decision' 'Test Rationale'\n"
        "/tasks\n"
        "/decisions\n"
        "/exit\n"
    )
    result = runner.invoke(main, ["shell"], input=commands)
    assert result.exit_code == 0
    assert "Updated task test-t1" in result.output
    assert "Recorded decision" in result.output
    assert "test-t1" in result.output
    assert "ADR-T1" in result.output


def test_cli_version(runner: CliRunner):
    """Verifies the --version flag."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "project-m" in result.output
    assert "0.1.2" in result.output


def test_cli_board(runner: CliRunner):
    """Verifies that project-m board renders the state card."""
    result = runner.invoke(main, ["board", "--target-tokens", "300"])
    assert result.exit_code == 0
    assert "PROJECT-M" in result.output
    assert "Living State Card" in result.output
    assert "Goal" in result.output


def test_cli_status(runner: CliRunner):
    """Verifies that project-m status renders the metrics table."""
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Context & Repository Health" in result.output
    assert "Project Goal" in result.output
    assert "Architectural Decisions" in result.output


def test_cli_export(runner: CliRunner, tmp_path: Path):
    """Verifies that project-m export writes the state card to disk."""
    export_target = tmp_path / "TEST_STATE.md"
    result = runner.invoke(main, ["export", "-o", str(export_target)])
    assert result.exit_code == 0
    assert "Exported living state contract" in result.output
    assert export_target.exists()
    assert "# Project-M: Living Project Board" in export_target.read_text(encoding="utf-8")


def test_configure_json_client(tmp_path: Path):
    """Verifies JSON configuration injection with backup creation."""
    cfg = tmp_path / "claude_desktop_config.json"
    # Pre-populate with another tool
    cfg.write_text(json.dumps({"mcpServers": {"existing": {"command": "echo"}}}), encoding="utf-8")

    success, msg = configure_json_client("claude", repo_path=tmp_path, config_path=cfg)
    assert success is True
    assert "Configured" in msg

    # Backup should exist
    backup = tmp_path / "claude_desktop_config.json.bak"
    assert backup.exists()

    # Injected content should have both existing and project-m
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "existing" in data["mcpServers"]
    assert "project-m" in data["mcpServers"]
    assert data["mcpServers"]["project-m"]["command"] == "uv"
    assert "--directory" in data["mcpServers"]["project-m"]["args"]


def test_configure_codex_toml(tmp_path: Path):
    """Verifies TOML configuration injection for Codex with backup."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('model = "gpt-4o"\n', encoding="utf-8")

    success, msg = configure_codex(repo_path=tmp_path, config_path=cfg)
    assert success is True
    assert "Configured" in msg

    # Backup should exist
    backup = tmp_path / "config.toml.bak"
    assert backup.exists()

    content = cfg.read_text(encoding="utf-8")
    assert '[mcp_servers.project-m]' in content
    assert 'command = "uv"' in content

    # Second run should be idempotent
    success2, msg2 = configure_codex(repo_path=tmp_path, config_path=cfg)
    assert success2 is True
    assert "already configured" in msg2


def test_install_skills(tmp_path: Path, monkeypatch):
    """Verifies that install_skills installs SKILL.md into client skill directories."""
    from project_m.setup import install_skills

    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: test-skill\n---\n# Test Skill Content\n", encoding="utf-8")

    results = install_skills(repo_path=tmp_path, clients=["claude", "antigravity", "codex"])
    assert results["claude_skill"][0] is True
    assert results["antigravity_skill"][0] is True
    assert results["codex_skill"][0] is True

    # Verify files were written
    claude_dest = fake_home / ".claude" / "skills" / "project-m" / "SKILL.md"
    antigravity_dest = fake_home / ".gemini" / "antigravity" / "skills" / "project-m" / "SKILL.md"
    codex_dest = fake_home / ".codex" / "skills" / "project-m" / "SKILL.md"

    assert claude_dest.exists()
    assert antigravity_dest.exists()
    assert codex_dest.exists()
    assert "Test Skill Content" in claude_dest.read_text(encoding="utf-8")
