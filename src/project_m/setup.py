"""
One-click installer and configurator for AI clients (Claude Desktop, Antigravity, Codex).
Safely updates client configuration files with automatic backups (.bak).
"""

import json
from pathlib import Path
import platform
import shutil
from typing import Any


def get_default_config_path(client: str) -> Path:
    """Returns the default configuration file path for the specified client."""
    home = Path.home()
    system = platform.system()

    if client == "claude":
        if system == "Darwin":
            return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        elif system == "Windows":
            return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
        else:
            return home / ".config" / "Claude" / "claude_desktop_config.json"

    elif client == "antigravity":
        return home / ".gemini" / "antigravity" / "mcp_config.json"

    elif client == "codex":
        return home / ".codex" / "config.toml"

    raise ValueError(f"Unknown client '{client}'. Expected 'claude', 'antigravity', or 'codex'.")


def create_backup(target_path: Path) -> Path | None:
    """Creates a timestamp-safe .bak backup if the target file exists."""
    if target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        shutil.copy2(target_path, backup_path)
        return backup_path
    return None


def configure_json_client(
    client_name: str,
    repo_path: Path,
    config_path: Path | None = None,
) -> tuple[bool, str]:
    """Injects Project-M into a standard JSON MCP configuration (Claude Desktop or Antigravity)."""
    target = config_path or get_default_config_path(client_name)
    target.parent.mkdir(parents=True, exist_ok=True)

    backup = create_backup(target)

    data: dict[str, Any] = {}
    if target.exists():
        try:
            content = target.read_text(encoding="utf-8").strip()
            if content:
                data = json.loads(content)
        except Exception as e:
            return False, f"Failed to parse existing JSON: {e}"

    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers["project-m"] = {
        "command": "uv",
        "args": [
            "--directory",
            str(repo_path.resolve()),
            "run",
            "project-m",
            "run",
        ],
    }

    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    msg = f"Configured {target}"
    if backup:
        msg += f" (Backup saved: {backup.name})"
    return True, msg


def configure_codex(
    repo_path: Path,
    config_path: Path | None = None,
) -> tuple[bool, str]:
    """Injects Project-M into Codex's TOML configuration."""
    target = config_path or get_default_config_path("codex")
    target.parent.mkdir(parents=True, exist_ok=True)

    backup = create_backup(target)

    entry = f"""
[mcp_servers.project-m]
command = "uv"
args = ["--directory", "{repo_path.resolve()}", "run", "project-m", "run"]
"""
    if target.exists():
        content = target.read_text(encoding="utf-8")
        if "[mcp_servers.project-m]" in content:
            return True, f"Project-M is already configured in {target}"
        target.write_text(content.strip() + "\n" + entry, encoding="utf-8")
    else:
        target.write_text(entry.strip() + "\n", encoding="utf-8")

    msg = f"Configured {target}"
    if backup:
        msg += f" (Backup saved: {backup.name})"
    return True, msg


def run_setup(
    repo_path: Path | None = None,
    clients: list[str] | None = None,
) -> dict[str, tuple[bool, str]]:
    """Runs setup across requested clients (defaults to all supported)."""
    target_repo = repo_path or Path.cwd()
    selected_clients = clients or ["claude", "antigravity", "codex"]
    results: dict[str, tuple[bool, str]] = {}

    for client in selected_clients:
        if client in ("claude", "antigravity"):
            results[client] = configure_json_client(client, target_repo)
        elif client == "codex":
            results[client] = configure_codex(target_repo)

    return results
