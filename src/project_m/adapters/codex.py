"""
Codex Harvester Adapter.

Reads OpenAI Codex / ChatGPT Desktop session rollouts via read-only SQLite inspection,
parses UserMessage and AgentMessage items, and ingests clean conversation turns
into Project-M SQLite WAL storage.
"""

import json
from pathlib import Path
import sqlite3
from typing import Any, Optional

from project_m.storage.db import insert_turn


def get_codex_db_path(custom_path: Optional[Path] = None) -> Path:
    """Returns the default path to Codex's state database."""
    return custom_path or (Path.home() / ".codex" / "state_5.sqlite")


def find_active_codex_rollout(
    project_cwd: Optional[str] = None,
    codex_db_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Finds the active session rollout JSONL file using Codex's state database in read-only mode.
    
    1. If project_cwd is provided, finds the newest thread for that directory.
    2. Otherwise, finds the newest thread across all projects.
    """
    db_file = get_codex_db_path(codex_db_path)
    if not db_file.exists():
        return None

    # Connect in read-only URI mode to guarantee zero locks on Codex
    uri = f"file:{db_file.resolve()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError:
        return None

    try:
        with conn:
            if project_cwd:
                query = """
                SELECT rollout_path FROM threads 
                WHERE cwd = ? AND archived = 0 
                ORDER BY updated_at DESC LIMIT 1;
                """
                row = conn.execute(query, (str(project_cwd),)).fetchone()
            else:
                query = """
                SELECT rollout_path FROM threads 
                WHERE archived = 0 
                ORDER BY updated_at DESC LIMIT 1;
                """
                row = conn.execute(query).fetchone()

        if row and row["rollout_path"]:
            p = Path(row["rollout_path"])
            return p if p.exists() else None
        return None
    except Exception:
        return None
    finally:
        conn.close()


def parse_codex_line(line_str: str) -> Optional[dict[str, Any]]:
    """
    Parses a single line from a Codex rollout.jsonl file.
    
    Extracts UserMessage and AgentMessage items when an item is completed.
    Returns a normalized turn dict or None.
    """
    line_str = line_str.strip()
    if not line_str:
        return None

    try:
        data = json.loads(line_str)
    except json.JSONDecodeError:
        return None

    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None

    # Only process completed items
    if payload.get("type") != "item_completed":
        return None

    item = payload.get("item")
    if not isinstance(item, dict):
        return None

    item_type = item.get("type")
    if item_type == "UserMessage":
        role = "user"
    elif item_type == "AgentMessage":
        role = "assistant"
    else:
        # Ignore tool calls, reasoning, or command executions
        return None

    # Extract text from content array
    content_list = item.get("content", [])
    extracted_texts = []
    for elem in content_list:
        if isinstance(elem, dict) and "text" in elem:
            text = elem["text"].strip()
            if text:
                extracted_texts.append(text)

    if not extracted_texts:
        return None

    content = "\n\n".join(extracted_texts)
    item_id = item.get("id") or data.get("timestamp")
    thread_id = payload.get("thread_id", "default")
    timestamp = data.get("timestamp")

    turn_id = f"codex:{item_id}"

    return {
        "turn_id": turn_id,
        "source": "codex",
        "session_id": thread_id,
        "role": role,
        "content": content,
        "timestamp": timestamp,
    }


def harvest_codex(
    rollout_path: Optional[Path] = None,
    project_cwd: Optional[str] = None,
    codex_db_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Reads a Codex rollout JSONL file and ingests new turns into Project-M.
    
    Returns the count of newly inserted turns.
    """
    target = rollout_path or find_active_codex_rollout(project_cwd, codex_db_path)
    if not target or not target.exists():
        return 0

    new_turns_count = 0
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            turn = parse_codex_line(line)
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
                new_turns_count += 1

    return new_turns_count