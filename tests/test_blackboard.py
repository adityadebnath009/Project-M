"""
Unit tests for the Living Blackboard & Context Compiler (Tier 1).
"""

from pathlib import Path
import pytest

from project_m.blackboard import (
    compile_briefing_card,
    count_tokens,
    export_project_state_md,
    get_project_summary,
)
from project_m.storage.db import (
    add_decision,
    add_task,
    insert_turn,
    set_board_value,
    update_task_status,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Fixture providing an isolated SQLite database path."""
    return tmp_path / "test_blackboard.db"


def test_count_tokens():
    """Validates the BPE token counter."""
    assert count_tokens("") == 0
    tokens = count_tokens("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;")
    assert tokens > 0
    assert isinstance(tokens, int)


def test_compile_briefing_card_empty_db(test_db: Path):
    """Verifies that compiling an uninitialized database produces a clean default card."""
    card = compile_briefing_card(db_path=test_db)
    assert "# Project-M: Living Project Board" in card
    assert "Define project goals" in card
    assert "⚠️ Attention Required" in card
    assert "No active milestone defined" in card


def test_compile_briefing_card_constraints_formatting(test_db: Path):
    """Verifies that binding constraints are parsed verbatim as bullet items."""
    set_board_value(
        "constraints",
        "SQLite WAL mode only\n- Python >= 3.11\n* Zero external cloud services",
        db_path=test_db,
    )
    card = compile_briefing_card(db_path=test_db)
    assert "### 🔒 Binding Constraints" in card
    assert "- SQLite WAL mode only" in card
    assert "- Python >= 3.11" in card
    assert "* Zero external cloud services" in card


def test_compile_briefing_card_accepted_decisions_provenance(test_db: Path):
    """Verifies that accepted ADRs are rendered with provenance and technical rationale."""
    add_decision(
        decision_id="ADR-001",
        title="SQLite WAL Concurrency",
        rationale="PRAGMA journal_mode=WAL and busy_timeout=5000",
        decided_by="claude",
        status="accepted",
        db_path=test_db,
    )
    card = compile_briefing_card(db_path=test_db)
    assert "### 🏛️ Active Decisions (Accepted)" in card
    assert "**[ADR-001] SQLite WAL Concurrency**: PRAGMA journal_mode=WAL and busy_timeout=5000" in card
    assert "*(Recorded by claude," in card


def test_compile_briefing_card_superseded_decisions_excluded(test_db: Path):
    """Verifies that superseded or proposed decisions do not leak into Tier 1 active decisions."""
    add_decision(
        decision_id="ADR-OLD",
        title="Use JSON files",
        rationale="Plain text JSON",
        decided_by="human",
        status="superseded",
        db_path=test_db,
    )
    add_decision(
        decision_id="ADR-NEW",
        title="Use SQLite",
        rationale="WAL mode",
        decided_by="claude",
        status="accepted",
        db_path=test_db,
    )
    card = compile_briefing_card(db_path=test_db)
    assert "[ADR-NEW]" in card
    assert "[ADR-OLD]" not in card


def test_compile_briefing_card_tasks_lifecycle_and_baton(test_db: Path):
    """Verifies task handoff owners, pending tasks, and compacted completed counts."""
    add_task("task-1", "Implement storage", status="completed", notes="All 36 tests passed", db_path=test_db)
    add_task("task-2", "Build blackboard", status="in_progress", assigned_to="antigravity", notes="Writing tests", db_path=test_db)
    add_task("task-3", "FastMCP server", status="pending", assigned_to="codex", db_path=test_db)

    card = compile_briefing_card(db_path=test_db)
    assert "### 📋 Active Tasks" in card
    assert "- **[IN PROGRESS]** `task-2`: Build blackboard (Owner: @antigravity) — *Writing tests*" in card
    assert "- **[PENDING]** `task-3`: FastMCP server (Assigned: @codex)" in card
    assert "- *Completed (1 tasks)*" in card


def test_compile_briefing_card_attention_warnings(test_db: Path):
    """Verifies that state health warnings are flagged under ⚠️ Attention Required."""
    # Unowned in-progress task
    add_task("task-unowned", "Orphaned work", status="in_progress", assigned_to=None, db_path=test_db)
    # Completed task without validation notes
    add_task("task-unverified", "Skipped checks", status="completed", notes="", db_path=test_db)

    card = compile_briefing_card(db_path=test_db)
    assert "### ⚠️ Attention Required" in card
    assert "Unowned active task: `task-unowned`" in card
    assert "Unverified completion: `task-unverified`" in card
    assert "No active milestone defined" in card


def test_compile_briefing_card_budget_cascade(test_db: Path):
    """Verifies that ambient turns are included when budget permits, and excluded when budget is tight."""
    insert_turn("turn-1", "antigravity", "sess-1", None, "user", "Message one", None, db_path=test_db)
    insert_turn("turn-2", "antigravity", "sess-1", None, "assistant", "Message two", None, db_path=test_db)

    # Generous budget: ambient turns should be included
    card_generous = compile_briefing_card(db_path=test_db, max_turns=2, target_tokens=1000)
    assert "### 🔄 Recent Activity" in card_generous
    assert "Message one" in card_generous

    # Strict tiny budget: ambient turns should be omitted
    card_tight = compile_briefing_card(db_path=test_db, max_turns=2, target_tokens=10)
    assert "### 🔄 Recent Activity" not in card_tight


def test_get_project_summary_diagnostics(test_db: Path):
    """Verifies that get_project_summary produces accurate health metrics."""
    set_board_value("goal", "Deliver Phase 4", db_path=test_db)
    set_board_value("current_milestone", "Milestone 4.1", db_path=test_db)
    add_task("task-1", "Owned task", status="in_progress", assigned_to="claude", db_path=test_db)
    add_task("task-2", "Completed verified", status="completed", notes="Verified ok", db_path=test_db)

    summary = get_project_summary(db_path=test_db)
    assert summary["goal"] == "Deliver Phase 4"
    assert summary["current_milestone"] == "Milestone 4.1"
    assert summary["in_progress_tasks"] == 1
    assert summary["completed_tasks"] == 1
    assert summary["is_healthy"] is True
    assert len(summary["warnings"]) == 0

    # Add an unowned task to verify health triggers
    add_task("task-3", "Unowned task", status="in_progress", assigned_to=None, db_path=test_db)
    unhealthy_summary = get_project_summary(db_path=test_db)
    assert unhealthy_summary["is_healthy"] is False
    assert "task-3" in unhealthy_summary["unowned_active_tasks"]


def test_export_project_state_md(test_db: Path, tmp_path: Path):
    """Verifies exporting the state card to a Markdown file on disk."""
    set_board_value("goal", "Export verification", db_path=test_db)
    export_file = tmp_path / "export" / "PROJECT_STATE.md"
    
    result_path = export_project_state_md(export_file, db_path=test_db)
    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")
    assert "Export verification" in content
