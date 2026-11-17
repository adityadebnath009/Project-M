"""Automated tests for Claude Code CLI Harvester Adapter."""

import json
from pathlib import Path
import pytest

from project_m.adapters.claude_code import (
    clean_claude_content,
    find_active_claude_session,
    harvest_claude_code,
    parse_claude_line,
    sanitize_project_path,
)
from project_m.storage.db import get_recent_turns, init_db


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Isolated temporary SQLite database for Claude Code adapter tests."""
    db_file = tmp_path / "test_claude_code.db"
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# 1. Project Path Sanitization
# -----------------------------------------------------------------------------

def test_sanitize_project_path():
    """Verify paths are converted using Claude Code's hyphen notation."""
    p = Path("/Users/adityadebnath/Projects/ai-redemption")
    sanitized = sanitize_project_path(p)
    assert sanitized == "-Users-adityadebnath-Projects-ai-redemption"


# -----------------------------------------------------------------------------
# 2. Noise & Command Artifact Cleaning
# -----------------------------------------------------------------------------

def test_clean_claude_content_strips_caveats_and_command_tags():
    """Verify internal terminal caveats and command XML tags are removed."""
    raw = (
        "<local-command-caveat>The command below was run directly in Claude Code...</local-command-caveat>\n"
        "<command-name>/focus</command-name>\n"
        "<command-message>focus</command-message>\n"
        "<command-args>In the repo</command-args>\n"
        "Please implement the authentication controller."
    )
    cleaned = clean_claude_content(raw)
    assert cleaned == "Please implement the authentication controller."
    assert "<local-command-caveat>" not in cleaned
    assert "<command-name>" not in cleaned


def test_clean_claude_content_strips_retry_loops():
    """Verify internal error loops and user interruptions are removed."""
    raw = (
        "[Your previous response had no visible output. Please continue and produce a user-visible response.]\n"
        "Let us review the database schema."
    )
    cleaned = clean_claude_content(raw)
    assert cleaned == "Let us review the database schema."
    assert "[Your previous response" not in cleaned


def test_clean_claude_content_length_capping():
    """Verify excessive text is truncated to protect token budgets."""
    long_text = "B" * 3000
    cleaned = clean_claude_content(long_text, max_chars=100)
    assert len(cleaned) == 100 + len("... [truncated]")
    assert cleaned.endswith("... [truncated]")


# -----------------------------------------------------------------------------
# 3. Line Parsing (User, Assistant & Ignore Types)
# -----------------------------------------------------------------------------

def test_parse_claude_line_user():
    """Verify parsing a valid user prompt line."""
    payload = json.dumps({
        "type": "user",
        "sessionId": "sess-123",
        "uuid": "u-001",
        "timestamp": "2026-11-17T10:00:00Z",
        "message": {
            "role": "user",
            "content": "Analyze the repository structure."
        }
    })
    turn = parse_claude_line(payload)
    assert turn is not None
    assert turn["source"] == "claude_code"
    assert turn["role"] == "user"
    assert turn["content"] == "Analyze the repository structure."
    assert turn["turn_id"] == "claude_code:sess-123:u-001"


def test_parse_claude_line_assistant_multiblock():
    """Verify parsing an assistant response with text and tool calls."""
    payload = json.dumps({
        "type": "assistant",
        "sessionId": "sess-123",
        "uuid": "a-001",
        "timestamp": "2026-11-17T10:00:05Z",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will inspect the files now."},
                {"type": "tool_use", "name": "read_file", "input": {"path": "README.md"}}
            ]
        }
    })
    turn = parse_claude_line(payload)
    assert turn is not None
    assert turn["source"] == "claude_code"
    assert turn["role"] == "assistant"
    assert "I will inspect the files now." in turn["content"]
    assert "[Tool Call: read_file]" in turn["content"]


def test_parse_claude_line_ignores_non_turns():
    """Verify non-turn operations (queue, attachment, atis) are skipped."""
    assert parse_claude_line('{"type": "queue-operation", "operation": "enqueue"}') is None
    assert parse_claude_line('{"type": "attachment", "file": "data.txt"}') is None
    assert parse_claude_line('') is None
    assert parse_claude_line('not valid json') is None


# -----------------------------------------------------------------------------
# 4. Session Finding & Harvesting with Deduplication
# -----------------------------------------------------------------------------

def test_find_active_claude_session(tmp_path: Path):
    """Verify session discovery correctly selects the newest session in the target project."""
    claude_home = tmp_path / ".claude"
    proj_dir = claude_home / "projects" / "-Users-test-my-app"
    proj_dir.mkdir(parents=True)

    old_sess = proj_dir / "old-session.jsonl"
    old_sess.write_text('{"type": "user"}\n', encoding="utf-8")

    new_sess = proj_dir / "new-session.jsonl"
    new_sess.write_text('{"type": "user"}\n', encoding="utf-8")

    found = find_active_claude_session(project_cwd="/Users/test/my-app", claude_dir=claude_home)
    assert found is not None
    assert found.name == "new-session.jsonl"


def test_harvest_claude_code_and_deduplication(tmp_path: Path, test_db: Path):
    """Verify ingestion of turns and guarantee of idempotent deduplication."""
    session_file = tmp_path / "test-session.jsonl"
    lines = [
        json.dumps({
            "type": "user",
            "sessionId": "test-session",
            "uuid": "u-1",
            "timestamp": "2026-11-17T10:00:00Z",
            "message": {"role": "user", "content": "First user message."}
        }),
        json.dumps({
            "type": "assistant",
            "sessionId": "test-session",
            "uuid": "a-1",
            "timestamp": "2026-11-17T10:00:02Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "First assistant reply."}]}
        }),
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # First harvest: 2 new turns inserted
    inserted_first = harvest_claude_code(session_path=session_file, db_path=test_db)
    assert inserted_first == 2

    # Verify turns stored in SQLite (chronological order)
    stored_turns = get_recent_turns(source="claude_code", limit=10, db_path=test_db)
    assert len(stored_turns) == 2
    assert stored_turns[0]["content"] == "First user message."
    assert stored_turns[1]["content"] == "First assistant reply."

    # Second harvest: should be idempotent (0 new turns inserted)
    inserted_second = harvest_claude_code(session_path=session_file, db_path=test_db)
    assert inserted_second == 0
