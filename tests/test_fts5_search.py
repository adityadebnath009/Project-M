"""Automated tests for SQLite FTS5 Lexical Search in Project-M."""

from pathlib import Path
import pytest

from project_m.storage.db import (
    get_connection,
    init_db,
    insert_turn,
    search_transcripts,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Isolated temporary SQLite database with FTS5 virtual table enabled."""
    db_file = tmp_path / "test_fts5.db"
    init_db(db_file)
    return db_file


# -----------------------------------------------------------------------------
# 1. Trigger Verification
# -----------------------------------------------------------------------------

def test_fts5_insert_trigger_automatically_populates_virtual_table(test_db: Path):
    """Verify that inserting into conversation_turns triggers FTS5 indexing."""
    insert_turn(
        turn_id="antigravity:sess-1:1",
        source="antigravity",
        session_id="sess-1",
        role="user",
        content="Please implement the token bucket rate limiter.",
        timestamp="2026-11-17T11:00:00Z",
        db_path=test_db,
    )

    # Search via FTS5
    results = search_transcripts("limiter", db_path=test_db)
    assert len(results) == 1
    assert results[0]["id"] == "antigravity:sess-1:1"
    assert results[0]["source"] == "antigravity"
    assert "token bucket rate limiter" in results[0]["content"]


# -----------------------------------------------------------------------------
# 2. Porter Stemming
# -----------------------------------------------------------------------------

def test_fts5_porter_stemming_matches_word_variations(test_db: Path):
    """Verify linguistic root matching (e.g., 'calculate' matches 'calculated')."""
    insert_turn(
        turn_id="claude:sess-2:1",
        source="claude_code",
        session_id="sess-2",
        role="assistant",
        content="We calculated all monetary values using Decimal arithmetic.",
        timestamp="2026-11-17T11:05:00Z",
        db_path=test_db,
    )

    # Search for root word 'calculate'
    results_calculate = search_transcripts("calculate", db_path=test_db)
    assert len(results_calculate) == 1
    assert results_calculate[0]["id"] == "claude:sess-2:1"

    # Search for noun 'calculation'
    results_calculation = search_transcripts("calculation", db_path=test_db)
    assert len(results_calculation) == 1


# -----------------------------------------------------------------------------
# 3. Source & Role Filtering
# -----------------------------------------------------------------------------

def test_fts5_filtering_by_source_and_role(test_db: Path):
    """Verify searches can be constrained to specific clients or roles."""
    insert_turn(
        turn_id="codex:sess-3:1",
        source="codex",
        session_id="sess-3",
        role="user",
        content="Optimize database indexing for fast recall.",
        db_path=test_db,
    )
    insert_turn(
        turn_id="antigravity:sess-3:2",
        source="antigravity",
        session_id="sess-3",
        role="assistant",
        content="Created index on database table conversation_turns.",
        db_path=test_db,
    )

    # Filter by source
    codex_only = search_transcripts("database", source="codex", db_path=test_db)
    assert len(codex_only) == 1
    assert codex_only[0]["source"] == "codex"

    # Filter by role
    assistant_only = search_transcripts("database", role="assistant", db_path=test_db)
    assert len(assistant_only) == 1
    assert assistant_only[0]["source"] == "antigravity"


# -----------------------------------------------------------------------------
# 4. Deletion Trigger
# -----------------------------------------------------------------------------

def test_fts5_delete_trigger_cleans_virtual_table(test_db: Path):
    """Verify deleting from conversation_turns removes the entry from FTS5."""
    turn_id = "codex:temp:99"
    insert_turn(
        turn_id=turn_id,
        source="codex",
        session_id="temp",
        role="user",
        content="Temporary secret credentials to delete.",
        db_path=test_db,
    )
    assert len(search_transcripts("temporary", db_path=test_db)) == 1

    # Delete turn directly from main table
    conn = get_connection(test_db)
    with conn:
        conn.execute("DELETE FROM conversation_turns WHERE id = ?;", (turn_id,))
    conn.close()

    # FTS5 index should now be empty
    assert len(search_transcripts("temporary", db_path=test_db)) == 0


# -----------------------------------------------------------------------------
# 5. Robustness & Special Character Handling
# -----------------------------------------------------------------------------

def test_fts5_handles_special_characters_without_syntax_error(test_db: Path):
    """Verify punctuation and symbols don't crash SQLite FTS5 parser."""
    assert search_transcripts("", db_path=test_db) == []
    assert search_transcripts("   ", db_path=test_db) == []
    assert search_transcripts("!@#$%^&*()_+", db_path=test_db) == []
