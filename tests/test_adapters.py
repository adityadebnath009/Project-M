"""Automated tests for Project-M Harvester Adapters."""

import json
from pathlib import Path
import pytest

from project_m.adapters.antigravity import (
    clean_turn_content,
    find_active_transcript_path,
    harvest_antigravity,
    parse_transcript_line,
)
from project_m.adapters.codex import (
    find_active_codex_rollout,
    harvest_codex,
    parse_codex_line,
)
from project_m.storage.db import get_recent_turns, init_db


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Isolated temporary SQLite database for adapter tests."""
    db_file = tmp_path / "test_adapters.db"
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# Context Engineering (Cleaning & Noise Reduction)
# -----------------------------------------------------------------------------

def test_clean_turn_content_strips_metadata_and_tags():
    """Verify XML wrapper tags and metadata blocks are completely removed."""
    raw = (
        "<USER_REQUEST>\n"
        "Please fix the bug in auth.py\n"
        "</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>\n"
        "timestamp=2026-11-10T12:00:00Z\n"
        "</ADDITIONAL_METADATA>\n"
        "<SYSTEM_MESSAGE>Server restarted</SYSTEM_MESSAGE>"
    )
    cleaned = clean_turn_content(raw)
    assert cleaned == "Please fix the bug in auth.py"
    assert "<USER_REQUEST>" not in cleaned
    assert "<ADDITIONAL_METADATA>" not in cleaned
    assert "<SYSTEM_MESSAGE>" not in cleaned


def test_clean_turn_content_length_capping():
    """Verify long inputs are capped to protect LLM context windows."""
    long_text = "A" * 3000
    cleaned = clean_turn_content(long_text, max_chars=100)
    assert len(cleaned) == 100 + len("... [truncated]")
    assert cleaned.endswith("... [truncated]")


# -----------------------------------------------------------------------------
# Line Parsing & Deduplication Keys
# -----------------------------------------------------------------------------

def test_parse_transcript_line_user_input():
    """Verify parsing a user turn with clean role and deterministic turn_id."""
    raw_line = json.dumps({
        "step_index": 42,
        "source": "USER_EXPLICIT",
        "type": "USER_INPUT",
        "content": "<USER_REQUEST>Build rate limiter</USER_REQUEST>",
        "created_at": "2026-11-10T12:00:00Z",
    })
    turn = parse_transcript_line(raw_line, session_id="conv_abc")
    assert turn is not None
    assert turn["role"] == "user"
    assert turn["turn_id"] == "antigravity:conv_abc:42"
    assert turn["content"] == "Build rate limiter"
    assert turn["source"] == "antigravity"


def test_parse_transcript_line_assistant_response():
    """Verify parsing an assistant turn, ignoring thinking and tool calls."""
    raw_line = json.dumps({
        "step_index": 43,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "content": "I implemented the TokenBucket algorithm in Python.",
        "thinking": "Secret internal reasoning that should be stripped...",
        "tool_calls": [{"name": "run_command", "args": {}}],
        "created_at": "2026-11-10T12:01:00Z",
    })
    turn = parse_transcript_line(raw_line, session_id="conv_abc")
    assert turn is not None
    assert turn["role"] == "assistant"
    assert turn["turn_id"] == "antigravity:conv_abc:43"
    assert turn["content"] == "I implemented the TokenBucket algorithm in Python."


def test_parse_transcript_line_ignores_invalid_and_telemetry():
    """Verify that corrupt JSON, empty lines, and non-conversation steps return None."""
    assert parse_transcript_line("", "conv_1") is None
    assert parse_transcript_line("corrupted { json", "conv_1") is None

    # System telemetry step (not a conversation message)
    telemetry_line = json.dumps({"step_index": 1, "type": "SYSTEM_NOTIFICATION"})
    assert parse_transcript_line(telemetry_line, "conv_1") is None


# -----------------------------------------------------------------------------
# Active Transcript Resolution
# -----------------------------------------------------------------------------

def test_find_active_transcript_path_finds_newest(tmp_path: Path):
    """Verify glob correctly sorts and returns the most recently updated transcript."""
    brain = tmp_path / "brain"
    
    # Old conversation
    old_log = brain / "conv_old" / ".system_generated" / "logs" / "transcript.jsonl"
    old_log.parent.mkdir(parents=True)
    old_log.write_text("old")

    # New conversation
    new_log = brain / "conv_new" / ".system_generated" / "logs" / "transcript.jsonl"
    new_log.parent.mkdir(parents=True)
    new_log.write_text("new")

    found = find_active_transcript_path(base_dir=brain)
    assert found is not None
    assert "conv_new" in str(found)


# -----------------------------------------------------------------------------
# Full End-to-End Ingestion & Deduplication
# -----------------------------------------------------------------------------

def test_harvest_antigravity_e2e_and_deduplication(tmp_path: Path, test_db: Path):
    """Verify reading a transcript file, ingesting turns, and deduplicating on second run."""
    log_file = tmp_path / "conv_123" / ".system_generated" / "logs" / "transcript.jsonl"
    log_file.parent.mkdir(parents=True)

    # Write 2 transcript lines
    lines = [
        json.dumps({
            "step_index": 1,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "content": "Hello Antigravity!",
            "created_at": "2026-11-10T10:00:00Z",
        }),
        json.dumps({
            "step_index": 2,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "content": "Hello Aditya! Ready to pair program.",
            "created_at": "2026-11-10T10:00:05Z",
        }),
    ]
    log_file.write_text("\n".join(lines) + "\n")

    # First harvest: should insert 2 turns
    count1 = harvest_antigravity(transcript_path=log_file, db_path=test_db)
    assert count1 == 2

    turns = get_recent_turns(db_path=test_db)
    assert len(turns) == 2
    assert turns[0]["content"] == "Hello Antigravity!"
    assert turns[1]["content"] == "Hello Aditya! Ready to pair program."

    # Second harvest on the exact same file: should insert 0 (Deduplication!)
    count2 = harvest_antigravity(transcript_path=log_file, db_path=test_db)
    assert count2 == 0


# -----------------------------------------------------------------------------
# Codex Harvester Tests
# -----------------------------------------------------------------------------

def test_parse_codex_line_user_message():
    """Verify parsing a Codex UserMessage item."""
    line = json.dumps({
        "timestamp": "2026-11-08T06:32:27.312Z",
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": "thread_abc123",
            "item": {
                "type": "UserMessage",
                "id": "item_user_1",
                "content": [{"type": "text", "text": "Analyze the backend schema"}],
            },
        },
    })
    turn = parse_codex_line(line)
    assert turn is not None
    assert turn["role"] == "user"
    assert turn["turn_id"] == "codex:item_user_1"
    assert turn["source"] == "codex"
    assert turn["content"] == "Analyze the backend schema"
    assert turn["session_id"] == "thread_abc123"


def test_parse_codex_line_agent_message():
    """Verify parsing a Codex AgentMessage item."""
    line = json.dumps({
        "timestamp": "2026-11-08T06:32:30.252Z",
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": "thread_abc123",
            "item": {
                "type": "AgentMessage",
                "id": "msg_agent_99",
                "content": [{"type": "Text", "text": "I examined the database schema."}],
            },
        },
    })
    turn = parse_codex_line(line)
    assert turn is not None
    assert turn["role"] == "assistant"
    assert turn["turn_id"] == "codex:msg_agent_99"
    assert turn["content"] == "I examined the database schema."


def test_parse_codex_line_ignores_non_messages():
    """Verify reasoning, commands, and session metadata lines are ignored."""
    meta_line = json.dumps({"type": "session_meta", "payload": {}})
    reasoning_line = json.dumps({
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {"type": "Reasoning", "content": [{"text": "thinking..."}]},
        },
    })
    assert parse_codex_line(meta_line) is None
    assert parse_codex_line(reasoning_line) is None


def test_harvest_codex_e2e_and_deduplication(tmp_path: Path, test_db: Path):
    """Verify reading a Codex rollout, ingesting turns, and deduplication."""
    rollout_file = tmp_path / "rollout-test.jsonl"
    lines = [
        json.dumps({
            "timestamp": "2026-11-08T06:32:27.000Z",
            "payload": {
                "type": "item_completed",
                "thread_id": "thread_1",
                "item": {
                    "type": "UserMessage",
                    "id": "msg_1",
                    "content": [{"type": "text", "text": "First user prompt"}],
                },
            },
        }),
        json.dumps({
            "timestamp": "2026-11-08T06:32:30.000Z",
            "payload": {
                "type": "item_completed",
                "thread_id": "thread_1",
                "item": {
                    "type": "AgentMessage",
                    "id": "msg_2",
                    "content": [{"type": "Text", "text": "First assistant response"}],
                },
            },
        }),
    ]
    rollout_file.write_text("\n".join(lines) + "\n")

    # Ingest turns
    count1 = harvest_codex(rollout_path=rollout_file, db_path=test_db)
    assert count1 == 2

    stored = get_recent_turns(db_path=test_db)
    assert len(stored) == 2
    assert stored[0]["source"] == "codex"
    assert stored[0]["content"] == "First user prompt"
    assert stored[1]["content"] == "First assistant response"

    # Second run deduplicates cleanly
    count2 = harvest_codex(rollout_path=rollout_file, db_path=test_db)
    assert count2 == 0
