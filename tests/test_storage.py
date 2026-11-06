"""Automated tests for Project-M SQLite WAL storage layer."""

import sqlite3
from pathlib import Path
import pytest

from project_m.storage.db import (
    add_decision,
    add_task,
    get_board,
    get_connection,
    get_decisions,
    get_recent_turns,
    get_tasks,
    init_db,
    insert_turn,
    resolve_db_path,
    set_board_value,
    update_task_status,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary database path for each test."""
    db_file = tmp_path / "test_state.db"
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# Base Tests (1 - 5)
# -----------------------------------------------------------------------------

def test_init_db_and_wal_mode(test_db: Path):
    """1. Verify that tables are created and WAL mode is active."""
    conn = get_connection(test_db)
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    ]
    assert "project_board" in tables
    assert "decisions" in tables
    assert "tasks" in tables
    assert "conversation_turns" in tables
    conn.close()


def test_project_board_upsert(test_db: Path):
    """2. Verify living project board sets and updates values cleanly."""
    set_board_value("goal", "Build rate limiter", db_path=test_db)
    board = get_board(db_path=test_db)
    assert board["goal"] == "Build rate limiter"

    set_board_value("goal", "Build rate limiter with Decimal", db_path=test_db)
    updated_board = get_board(db_path=test_db)
    assert updated_board["goal"] == "Build rate limiter with Decimal"
    assert len(updated_board) == 1


def test_decisions_ordering(test_db: Path):
    """3. Verify decisions are recorded and returned chronologically."""
    add_decision("dec_1", "Use SQLite", "Zero cloud bills", "claude", db_path=test_db)
    add_decision("dec_2", "Use WAL Mode", "Concurrent reads", "antigravity", db_path=test_db)

    decisions = get_decisions(db_path=test_db)
    assert len(decisions) == 2
    assert decisions[0]["id"] == "dec_1"
    assert decisions[1]["id"] == "dec_2"


def test_tasks_lifecycle(test_db: Path):
    """4. Verify task addition, status updates, and filtering."""
    add_task("task_1", "Write schema", status="pending", db_path=test_db)
    updated = update_task_status("task_1", status="completed", notes="All good", db_path=test_db)
    assert updated is True

    completed = get_tasks(status="completed", db_path=test_db)
    assert len(completed) == 1
    assert completed[0]["title"] == "Write schema"
    assert completed[0]["notes"] == "All good"

    assert update_task_status("missing_task", status="completed", db_path=test_db) is False


def test_turns_deduplication(test_db: Path):
    """5. Verify that identical turns are safely deduplicated without crashing."""
    inserted_first = insert_turn(
        turn_id="antigravity:conv1:step1",
        source="antigravity",
        session_id="conv1",
        project_path="/test",
        role="user",
        content="Hello Antigravity",
        db_path=test_db,
    )
    assert inserted_first is True

    inserted_second = insert_turn(
        turn_id="antigravity:conv1:step1",
        source="antigravity",
        session_id="conv1",
        project_path="/test",
        role="user",
        content="Hello Antigravity",
        db_path=test_db,
    )
    assert inserted_second is False

    turns = get_recent_turns(db_path=test_db)
    assert len(turns) == 1


# -----------------------------------------------------------------------------
# Additional 20 Stress & Edge-Case Tests (6 - 25)
# -----------------------------------------------------------------------------

def test_init_db_idempotency(test_db: Path):
    """6. Calling init_db multiple times on existing DB preserves data without crashing."""
    set_board_value("version", "1.0.0", db_path=test_db)
    # Re-initialize DB
    init_db(test_db)
    init_db(test_db)
    board = get_board(db_path=test_db)
    assert board["version"] == "1.0.0"


def test_custom_db_path_resolution(tmp_path: Path):
    """7. Custom DB paths are resolved and parent directories created automatically."""
    custom_dir = tmp_path / "deep" / "nested" / "dir"
    custom_file = custom_dir / "custom.db"
    resolved = resolve_db_path(str(custom_file))
    assert resolved == custom_file.resolve()
    assert custom_dir.exists()


def test_board_empty_initially(test_db: Path):
    """8. Empty project board returns an empty dictionary."""
    board = get_board(db_path=test_db)
    assert board == {}


def test_board_multiple_distinct_keys(test_db: Path):
    """9. Setting multiple distinct keys stores all of them independently."""
    set_board_value("goal", "Build MCP server", db_path=test_db)
    set_board_value("stack", "Python 3.14 + SQLite WAL", db_path=test_db)
    set_board_value("auth", "Local only", db_path=test_db)

    board = get_board(db_path=test_db)
    assert len(board) == 3
    assert board["goal"] == "Build MCP server"
    assert board["stack"] == "Python 3.14 + SQLite WAL"
    assert board["auth"] == "Local only"


def test_board_special_characters_and_json(test_db: Path):
    """10. Stores JSON strings, emojis, newlines, and quotes in board."""
    json_val = '{"features": ["wal", "sync"], "emoji": "🚀", "quote": "It\'s fine"}'
    set_board_value("config_json", json_val, db_path=test_db)
    board = get_board(db_path=test_db)
    assert board["config_json"] == json_val


def test_decisions_empty_initially(test_db: Path):
    """11. An empty decisions table returns an empty list."""
    decisions = get_decisions(db_path=test_db)
    assert decisions == []


def test_decisions_limit(test_db: Path):
    """12. Decisions limit parameter strictly bounds the number of returned items."""
    for i in range(5):
        add_decision(f"dec_{i}", f"Decision {i}", "Rationale", "claude", db_path=test_db)
    
    limited = get_decisions(limit=2, db_path=test_db)
    assert len(limited) == 2
    assert limited[0]["id"] == "dec_0"
    assert limited[1]["id"] == "dec_1"


def test_decisions_upsert_update(test_db: Path):
    """13. Re-adding a decision updates title, rationale, and status."""
    add_decision("arch_1", "Use MySQL", "Easy setup", "antigravity", status="proposed", db_path=test_db)
    # Pivot decision to SQLite
    add_decision("arch_1", "Use SQLite WAL", "Zero cloud bills & portable", "claude", status="accepted", db_path=test_db)

    decisions = get_decisions(db_path=test_db)
    assert len(decisions) == 1
    assert decisions[0]["title"] == "Use SQLite WAL"
    assert decisions[0]["status"] == "accepted"
    assert decisions[0]["decided_by"] == "claude"


def test_tasks_multiple_statuses_filtering(test_db: Path):
    """14. Filtering tasks by pending, in_progress, and completed returns exact subsets."""
    add_task("t1", "Task 1", status="pending", db_path=test_db)
    add_task("t2", "Task 2", status="in_progress", db_path=test_db)
    add_task("t3", "Task 3", status="completed", db_path=test_db)
    add_task("t4", "Task 4", status="completed", db_path=test_db)

    assert len(get_tasks(status="pending", db_path=test_db)) == 1
    assert len(get_tasks(status="in_progress", db_path=test_db)) == 1
    assert len(get_tasks(status="completed", db_path=test_db)) == 2


def test_tasks_get_all_unfiltered(test_db: Path):
    """15. Retrieving tasks without filter returns all tasks."""
    add_task("t1", "Task 1", status="pending", db_path=test_db)
    add_task("t2", "Task 2", status="in_progress", db_path=test_db)
    all_tasks = get_tasks(db_path=test_db)
    assert len(all_tasks) == 2


def test_tasks_upsert_replaces_fields(test_db: Path):
    """16. Calling add_task with existing ID cleanly updates fields."""
    add_task("t1", "Task 1", status="pending", assigned_to="codex", notes="initial", db_path=test_db)
    add_task("t1", "Task 1 Renamed", status="in_progress", assigned_to="claude", notes="revised", db_path=test_db)

    tasks = get_tasks(db_path=test_db)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Task 1 Renamed"
    assert tasks[0]["status"] == "in_progress"
    assert tasks[0]["assigned_to"] == "claude"
    assert tasks[0]["notes"] == "revised"


def test_tasks_update_without_notes_leaves_previous_notes(test_db: Path):
    """17. Updating task status with notes=None keeps previous notes intact."""
    add_task("t1", "Task 1", notes="Crucial note", db_path=test_db)
    update_task_status("t1", status="completed", notes=None, db_path=test_db)

    task = get_tasks(status="completed", db_path=test_db)[0]
    assert task["notes"] == "Crucial note"


def test_tasks_update_nonexistent_returns_false(test_db: Path):
    """18. Attempting to update a non-existent task returns False."""
    success = update_task_status("nonexistent_uuid", status="completed", db_path=test_db)
    assert success is False


def test_turns_filter_by_source_antigravity(test_db: Path):
    """19. Filtering turns by 'antigravity' ignores turns from other clients."""
    insert_turn("ag:1", "antigravity", "s1", "/p", "user", "Hello AG", db_path=test_db)
    insert_turn("cx:1", "codex", "s2", "/p", "user", "Hello Codex", db_path=test_db)

    ag_turns = get_recent_turns(source="antigravity", db_path=test_db)
    assert len(ag_turns) == 1
    assert ag_turns[0]["id"] == "ag:1"
    assert ag_turns[0]["source"] == "antigravity"


def test_turns_filter_by_source_codex(test_db: Path):
    """20. Filtering turns by 'codex' ignores turns from other clients."""
    insert_turn("ag:1", "antigravity", "s1", "/p", "user", "Hello AG", db_path=test_db)
    insert_turn("cx:1", "codex", "s2", "/p", "user", "Hello Codex", db_path=test_db)

    cx_turns = get_recent_turns(source="codex", db_path=test_db)
    assert len(cx_turns) == 1
    assert cx_turns[0]["id"] == "cx:1"
    assert cx_turns[0]["source"] == "codex"


def test_turns_filter_all_returns_every_client(test_db: Path):
    """21. Passing source='all' or source=None returns turns across all clients."""
    insert_turn("ag:1", "antigravity", "s1", "/p", "user", "msg1", db_path=test_db)
    insert_turn("cx:1", "codex", "s2", "/p", "assistant", "msg2", db_path=test_db)
    insert_turn("cl:1", "claude", "s3", "/p", "user", "msg3", db_path=test_db)

    all_explicit = get_recent_turns(source="all", db_path=test_db)
    all_none = get_recent_turns(source=None, db_path=test_db)
    assert len(all_explicit) == 3
    assert len(all_none) == 3


def test_turns_limit_and_chronological_order(test_db: Path):
    """22. Verify limit returns the N newest turns, ordered oldest-to-newest."""
    for i in range(10):
        insert_turn(f"turn:{i}", "claude", "s1", "/p", "user", f"Content {i}", db_path=test_db)

    recent = get_recent_turns(limit=3, db_path=test_db)
    assert len(recent) == 3
    # Should be the last 3 inserted (turn:7, turn:8, turn:9) in chronological sequence
    assert recent[0]["id"] == "turn:7"
    assert recent[1]["id"] == "turn:8"
    assert recent[2]["id"] == "turn:9"


def test_turns_large_payload(test_db: Path):
    """23. Storing large payloads (e.g. 100KB of code or logs) succeeds cleanly."""
    huge_payload = "def process(): pass\n" * 5000  # ~100 KB
    success = insert_turn("huge:1", "antigravity", "s1", "/p", "assistant", huge_payload, db_path=test_db)
    assert success is True

    turns = get_recent_turns(limit=1, db_path=test_db)
    assert len(turns) == 1
    assert turns[0]["content"] == huge_payload


def test_turns_sql_injection_resilience(test_db: Path):
    """24. SQL injection attempts are treated as literal text and do not execute."""
    injection_id = "turn'; DROP TABLE conversation_turns; --"
    injection_content = "Robert'); DROP TABLE tasks; --"
    success = insert_turn(injection_id, "claude", "s1", "/p", "user", injection_content, db_path=test_db)
    assert success is True

    # Confirm tables still exist and data was safely parameterized
    conn = get_connection(test_db)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    conn.close()
    assert "conversation_turns" in tables
    assert "tasks" in tables

    stored = get_recent_turns(db_path=test_db)
    assert stored[0]["id"] == injection_id
    assert stored[0]["content"] == injection_content


def test_concurrent_readers_in_wal_mode(test_db: Path):
    """25. Multiple simultaneous connections can read without table lock contention."""
    conn1 = get_connection(test_db)
    conn2 = get_connection(test_db)

    set_board_value("status", "operational", db_path=test_db)

    val1 = conn1.execute("SELECT value FROM project_board WHERE key='status';").fetchone()[0]
    val2 = conn2.execute("SELECT value FROM project_board WHERE key='status';").fetchone()[0]

    assert val1 == "operational"
    assert val2 == "operational"

    conn1.close()
    conn2.close()
