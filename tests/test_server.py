"""
Unit tests for the Project-M FastMCP Server.
Verifies all 7 MCP tools exposed over the protocol.
"""

from pathlib import Path
import pytest

from project_m.server import create_server
from project_m.storage.db import get_board, get_decisions, get_tasks, insert_turn


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Fixture providing an isolated SQLite database path for the MCP server."""
    return tmp_path / "test_mcp.db"


@pytest.mark.asyncio
async def test_server_tool_registration(test_db: Path):
    """Verifies that all 7 required MCP tools are registered on the server."""
    server = create_server(db_path=test_db)
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "get_project_board",
        "get_project_summary",
        "record_decision",
        "publish_context",
        "update_task",
        "get_recent_context",
        "get_turn",
    }
    assert expected_tools.issubset(tool_names)
    assert len(tools) == 7


@pytest.mark.asyncio
async def test_publish_context_tool(test_db: Path):
    """Verifies publishing metadata and constraints to the project board."""
    server = create_server(db_path=test_db)
    result = await server.call_tool("publish_context", {"key": "goal", "value": "Test Project Goal"})
    assert result.is_error is False
    assert "Successfully updated project board key 'goal'" in result.content[0].text

    # Verify state in SQLite
    board = get_board(db_path=test_db)
    assert board["goal"] == "Test Project Goal"


@pytest.mark.asyncio
async def test_record_decision_tool(test_db: Path):
    """Verifies recording an Architectural Decision Record (ADR) into Tier 2."""
    server = create_server(db_path=test_db)
    result = await server.call_tool(
        "record_decision",
        {
            "decision_id": "ADR-001",
            "title": "SQLite WAL Concurrency",
            "rationale": "PRAGMA journal_mode=WAL and busy_timeout=5000",
            "decided_by": "claude",
            "status": "accepted",
        },
    )
    assert result.is_error is False
    assert "[ADR-001]" in result.content[0].text
    assert "accepted" in result.content[0].text

    # Verify in SQLite
    decisions = get_decisions(db_path=test_db)
    assert len(decisions) == 1
    assert decisions[0]["id"] == "ADR-001"
    assert decisions[0]["decided_by"] == "claude"


@pytest.mark.asyncio
async def test_update_task_tool_lifecycle(test_db: Path):
    """Verifies task creation, owner handoff baton, and verified completion."""
    server = create_server(db_path=test_db)

    # 1. Start task with owner baton
    r1 = await server.call_tool(
        "update_task",
        {
            "task_id": "task-01",
            "title": "Implement FastMCP server",
            "status": "in_progress",
            "assigned_to": "codex",
            "notes": "Writing routes",
        },
    )
    assert r1.is_error is False
    assert "in_progress" in r1.content[0].text
    assert "@codex" in r1.content[0].text

    # 2. Hand off task to Antigravity
    r2 = await server.call_tool(
        "update_task",
        {
            "task_id": "task-01",
            "status": "in_progress",
            "assigned_to": "antigravity",
            "notes": "Running unit tests",
        },
    )
    assert r2.is_error is False
    assert "@antigravity" in r2.content[0].text

    # 3. Mark completed with validation notes
    r3 = await server.call_tool(
        "update_task",
        {
            "task_id": "task-01",
            "status": "completed",
            "notes": "All tests passed in 0.25s",
        },
    )
    assert r3.is_error is False
    assert "completed" in r3.content[0].text

    tasks = get_tasks(db_path=test_db)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["assigned_to"] == "antigravity"
    assert tasks[0]["notes"] == "All tests passed in 0.25s"


@pytest.mark.asyncio
async def test_get_project_board_tool(test_db: Path):
    """Verifies compiling and retrieving the Tier 1 State Card."""
    server = create_server(db_path=test_db)
    await server.call_tool("publish_context", {"key": "goal", "value": "Verify Board Compiler"})
    await server.call_tool(
        "record_decision",
        {
            "decision_id": "ADR-002",
            "title": "Strict Typing",
            "rationale": "Python 3.14 strict types",
            "decided_by": "antigravity",
        },
    )

    result = await server.call_tool("get_project_board", {"target_tokens": 450})
    assert result.is_error is False
    card_text = result.content[0].text
    assert "# Project-M: Living Project Board" in card_text
    assert "Verify Board Compiler" in card_text
    assert "[ADR-002] Strict Typing" in card_text


@pytest.mark.asyncio
async def test_get_project_summary_tool(test_db: Path):
    """Verifies programmatic health diagnostics dictionary."""
    server = create_server(db_path=test_db)
    await server.call_tool("publish_context", {"key": "goal", "value": "Health Check Goal"})
    await server.call_tool("publish_context", {"key": "current_milestone", "value": "Phase 4"})

    result = await server.call_tool("get_project_summary", {})
    assert result.is_error is False
    summary = result.structured_content
    assert summary["goal"] == "Health Check Goal"
    assert summary["current_milestone"] == "Phase 4"
    assert summary["is_healthy"] is True


@pytest.mark.asyncio
async def test_get_recent_context_tool(test_db: Path):
    """Verifies fetching ambient conversation turns across clients."""
    insert_turn("turn-1", "antigravity", "sess-1", None, "user", "Hello server", None, db_path=test_db)
    insert_turn("turn-2", "codex", "sess-2", None, "assistant", "Hi there", None, db_path=test_db)

    server = create_server(db_path=test_db)
    result = await server.call_tool("get_recent_context", {"limit": 5})
    assert result.is_error is False
    turns = result.structured_content["result"]
    assert len(turns) == 2
    assert turns[0]["id"] == "turn-1"
    assert turns[1]["id"] == "turn-2"


@pytest.mark.asyncio
async def test_get_turn_tool_lossless(test_db: Path):
    """Verifies retrieving an exact uncompressed raw turn by its ID."""
    insert_turn(
        "turn-lossless",
        "antigravity",
        "session-xyz",
        "/path/to/repo",
        "user",
        "Exact verbatim content with flags: --verbose --force",
        "2026-11-16T10:00:00",
        db_path=test_db,
    )

    server = create_server(db_path=test_db)

    # 1. Lookup existing turn
    result = await server.call_tool("get_turn", {"turn_id": "turn-lossless"})
    assert result.is_error is False
    turn_data = result.structured_content["result"]
    assert turn_data["id"] == "turn-lossless"
    assert turn_data["content"] == "Exact verbatim content with flags: --verbose --force"
    assert turn_data["source"] == "antigravity"

    # 2. Lookup non-existent turn
    not_found = await server.call_tool("get_turn", {"turn_id": "nonexistent-id"})
    assert not_found.is_error is False
    assert "not found" in not_found.content[0].text
