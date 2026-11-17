"""
Claude Code CLI Harvester Adapter.

Reads Claude Code project sessions from ~/.claude/projects/-<sanitized_path>/*.jsonl,
sanitizes internal command caveats and retry loops, and ingests clean turns
into Project-M SQLite WAL storage with deduplication.
"""

import json
import re
from pathlib import Path
from typing import Any

from project_m.storage.db import insert_turn


def sanitize_project_path(path: Path | str) -> str:
    """
    Converts a filesystem path into Claude Code's project folder naming convention.
    Example: /Users/adityadebnath/Projects/ai-redemption -> -Users-adityadebnath-Projects-ai-redemption
    """
    resolved = str(Path(path).resolve())
    return resolved.replace("/", "-")


def find_active_claude_session(
    project_cwd: Path | str | None = None,
    claude_dir: Path | None = None,
) -> Path | None:
    """
    Locates the most recent Claude Code session JSONL file.
    
    1. If project_cwd is provided, looks under ~/.claude/projects/<sanitized_path>/*.jsonl
    2. Otherwise, finds the most recently updated session JSONL across all projects.
    """
    base = claude_dir or (Path.home() / ".claude")
    projects_dir = base / "projects"
    if not projects_dir.exists():
        return None

    if project_cwd:
        sanitized = sanitize_project_path(project_cwd)
        target_dir = projects_dir / sanitized
        if target_dir.exists():
            candidates = list(target_dir.glob("*.jsonl"))
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return candidates[0]

    # Fallback: scan all project directories for the latest session
    all_sessions = list(projects_dir.glob("*/*.jsonl"))
    if not all_sessions:
        return None

    all_sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return all_sessions[0]


def clean_claude_content(raw_text: str, max_chars: int = 2000) -> str:
    """
    Cleans internal Claude Code terminal caveats, command artifacts, and retry loops.
    Protects token budget with deterministic length capping.
    """
    if not raw_text:
        return ""

    cleaned = raw_text

    # 1. Remove local command caveats & command tags
    cleaned = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<local-command-stdout>.*?</local-command-stdout>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<command-name>.*?</command-name>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<command-message>.*?</command-message>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<command-args>.*?</command-args>", "", cleaned, flags=re.DOTALL)

    # 2. Filter internal error retry echoes
    cleaned = re.sub(r"\[Your previous response had no visible output.*?\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[Request interrupted by user\]", "", cleaned, flags=re.IGNORECASE)

    # 3. Strip whitespace and enforce character ceiling
    cleaned = cleaned.strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "... [truncated]"
    return cleaned


def parse_claude_line(line_str: str, session_id: str | None = None) ->dict[str, Any] | None:
    """
    Parses a single JSON line from a Claude Code session JSONL file.
    
    Extracts 'user' and 'assistant' turns. Handles assistant multi-block content 
    (text and tool_use). Returns a normalized turn dict or None.
    """
    line_str = line_str.strip()
    if not line_str:
        return None

    try:
        data = json.loads(line_str)
    except json.JSONDecodeError:
        return None

    msg_type = data.get("type")
    if msg_type not in ("user", "assistant"):
        return None

    message = data.get("message", {})
    role = message.get("role") or msg_type
    content_raw = message.get("content")

    # Extract text from string or multi-block list
    if isinstance(content_raw, list):
        text_parts = []
        for block in content_raw:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    text_parts.append(f"[Tool Call: {tool_name}]")
        raw_text = "\n".join(text_parts)
    elif isinstance(content_raw, str):
        raw_text = content_raw
    else:
        return None

    cleaned = clean_claude_content(raw_text)
    if not cleaned:
        return None

    actual_session_id = data.get("sessionId") or session_id or "default"
    turn_uuid = data.get("uuid") or f"{actual_session_id}_{data.get('timestamp', '')}"
    turn_id = f"claude_code:{actual_session_id}:{turn_uuid}"

    return {
        "turn_id": turn_id,
        "source": "claude_code",
        "session_id": actual_session_id,
        "role": role,
        "content": cleaned,
        "timestamp": data.get("timestamp"),
    }


def harvest_claude_code(
    session_path: Path | None = None,
    project_cwd: Path | str | None = None,
    db_path: Path | None = None,
) -> int:
    """
    Harvests new conversation turns from a Claude Code session JSONL file
    into the Project-M SQLite WAL database.
    
    Returns the count of newly inserted turns.
    """
    target = session_path or find_active_claude_session(project_cwd=project_cwd)
    if not target or not target.exists():
        return 0

    session_id = target.stem  # e.g., '3e00e84c-3162-4297-bb05-8a5a1c4b2b9a'
    new_turns = 0

    with open(target, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            turn = parse_claude_line(line, session_id=session_id)
            if not turn:
                continue
            inserted = insert_turn(
                turn_id=turn["turn_id"],
                source=turn["source"],
                session_id=turn["session_id"],
                role=turn["role"],
                content=turn["content"],
                timestamp=turn["timestamp"],
                db_path=db_path,
            )
            if inserted:
                new_turns += 1

    return new_turns