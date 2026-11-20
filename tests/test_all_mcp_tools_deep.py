"""
Comprehensive deep verification suite for all 8 Project-M MCP server tools.
Tests edge cases, parameter boundaries, data consistency, and round-tripping directly through server.call_tool.
"""

from pathlib import Path
import pytest

from project_m.server import create_server
from project_m.storage.db import init_db, insert_turn, get_board, get_decisions, get_tasks


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db = tmp_path / "deep_mcp.db"
    init_db(db)
    return db


# ==============================================================================
# TOOL 1: publish_context (4 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_publish_context_basic(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("publish_context", {"key": "goal", "value": "Build local memory"})
    assert res.is_error is False
    assert "Successfully updated project board key 'goal'" in res.content[0].text
    assert get_board(db_path=test_db)["goal"] == "Build local memory"


@pytest.mark.asyncio
async def test_tool_publish_context_overwrite(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("publish_context", {"key": "milestone", "value": "Phase 1"})
    res = await server.call_tool("publish_context", {"key": "milestone", "value": "Phase 2"})
    assert res.is_error is False
    assert get_board(db_path=test_db)["milestone"] == "Phase 2"


@pytest.mark.asyncio
async def test_tool_publish_context_special_characters(test_db: Path):
    server = create_server(db_path=test_db)
    special_str = "Tech: Python 🚀 & SQLite WAL ⚡ / 日本語 / Quotes: 'single' and \"double\""
    res = await server.call_tool("publish_context", {"key": "stack", "value": special_str})
    assert res.is_error is False
    assert get_board(db_path=test_db)["stack"] == special_str


@pytest.mark.asyncio
async def test_tool_publish_context_large_payload(test_db: Path):
    server = create_server(db_path=test_db)
    large_payload = "Config line\n" * 500
    res = await server.call_tool("publish_context", {"key": "spec", "value": large_payload})
    assert res.is_error is False
    assert get_board(db_path=test_db)["spec"] == large_payload


# ==============================================================================
# TOOL 2: record_decision (5 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_record_decision_accepted(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool(
        "record_decision",
        {
            "decision_id": "ADR-001",
            "title": "Use SQLite WAL",
            "rationale": "High throughput concurrent readers",
            "decided_by": "aditya",
            "status": "accepted",
        },
    )
    assert res.is_error is False
    assert "[ADR-001]" in res.content[0].text
    assert "accepted" in res.content[0].text
    decisions = get_decisions(db_path=test_db)
    assert len(decisions) == 1
    assert decisions[0]["title"] == "Use SQLite WAL"


@pytest.mark.asyncio
async def test_tool_record_decision_update_existing(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("record_decision", {"decision_id": "ADR-001", "title": "Old Title", "rationale": "Old", "decided_by": "Agent"})
    await server.call_tool("record_decision", {"decision_id": "ADR-001", "title": "New Title", "rationale": "Revised", "decided_by": "Human"})
    decisions = get_decisions(db_path=test_db)
    assert len(decisions) == 1
    assert decisions[0]["title"] == "New Title"
    assert decisions[0]["rationale"] == "Revised"


@pytest.mark.asyncio
async def test_tool_record_decision_superseded_status(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("record_decision", {"decision_id": "ADR-OLD", "title": "Use Redis", "rationale": "Cloud cache", "status": "superseded", "decided_by": "Agent"})
    assert res.is_error is False
    assert "superseded" in res.content[0].text
    board_res = await server.call_tool("get_project_board", {})
    assert "Use Redis" not in board_res.content[0].text


@pytest.mark.asyncio
async def test_tool_record_decision_rejected_status(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("record_decision", {"decision_id": "ADR-REJ", "title": "Use Cloud Pinecone", "rationale": "Too costly", "status": "rejected", "decided_by": "Aditya"})
    assert res.is_error is False
    assert "rejected" in res.content[0].text
    board_res = await server.call_tool("get_project_board", {})
    assert "Use Cloud Pinecone" not in board_res.content[0].text


@pytest.mark.asyncio
async def test_tool_record_decision_with_markdown_rationale(test_db: Path):
    server = create_server(db_path=test_db)
    markdown_rationale = "1. Point one\n2. Point two\n`code block`"
    res = await server.call_tool("record_decision", {"decision_id": "ADR-MD", "title": "Markdown Test", "rationale": markdown_rationale, "decided_by": "Claude"})
    assert res.is_error is False
    decisions = get_decisions(db_path=test_db)
    assert decisions[0]["rationale"] == markdown_rationale


# ==============================================================================
# TOOL 3: update_task (5 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_update_task_create_pending(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("update_task", {"task_id": "task-auth", "title": "Implement Auth", "status": "pending"})
    assert res.is_error is False
    assert "pending" in res.content[0].text
    tasks = get_tasks(db_path=test_db)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_tool_update_task_in_progress_with_owner(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("update_task", {"task_id": "task-auth", "title": "Implement Auth", "status": "in_progress", "assigned_to": "claude", "notes": "Working on PKCE"})
    assert res.is_error is False
    assert "@claude" in res.content[0].text
    assert "in_progress" in res.content[0].text


@pytest.mark.asyncio
async def test_tool_update_task_baton_handoff(test_db: Path):
    server = create_server(db_path=test_db)
    # Agent A starts
    await server.call_tool("update_task", {"task_id": "task-1", "title": "Schema Migration", "status": "in_progress", "assigned_to": "codex"})
    # Agent A hands off to Agent B
    res = await server.call_tool("update_task", {"task_id": "task-1", "status": "in_progress", "assigned_to": "antigravity", "notes": "Handoff to Antigravity for tests"})
    assert res.is_error is False
    assert "@antigravity" in res.content[0].text
    tasks = get_tasks(db_path=test_db)
    assert tasks[0]["assigned_to"] == "antigravity"
    assert "Handoff to Antigravity for tests" in tasks[0]["notes"]


@pytest.mark.asyncio
async def test_tool_update_task_completed(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("update_task", {"task_id": "task-1", "title": "Init DB", "status": "completed", "notes": "Done verified"})
    tasks = get_tasks(db_path=test_db)
    assert tasks[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_tool_update_task_preserves_notes_on_blank_update(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("update_task", {"task_id": "task-notes", "title": "Title A", "status": "pending", "notes": "Keep this note safe"})
    await server.call_tool("update_task", {"task_id": "task-notes", "status": "in_progress", "assigned_to": "claude"})
    tasks = get_tasks(db_path=test_db)
    assert tasks[0]["notes"] == "Keep this note safe"


# ==============================================================================
# TOOL 4: get_project_board (4 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_project_board_empty(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_project_board", {})
    assert res.is_error is False
    assert "# Project-M: Living Project Board" in res.content[0].text


@pytest.mark.asyncio
async def test_tool_get_project_board_populated(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("publish_context", {"key": "goal", "value": "Ship v0.1.2"})
    await server.call_tool("record_decision", {"decision_id": "ADR-001", "title": "FastAPI Core", "rationale": "Speed", "decided_by": "Aditya"})
    await server.call_tool("update_task", {"task_id": "T-01", "title": "Route Tests", "status": "in_progress", "assigned_to": "claude"})
    res = await server.call_tool("get_project_board", {})
    text = res.content[0].text
    assert "Ship v0.1.2" in text
    assert "[ADR-001] FastAPI Core" in text
    assert "Route Tests" in text
    assert "@claude" in text


@pytest.mark.asyncio
async def test_tool_get_project_board_token_ceiling(test_db: Path):
    server = create_server(db_path=test_db)
    for i in range(15):
        await server.call_tool("record_decision", {"decision_id": f"ADR-{i}", "title": f"Decision {i}", "rationale": f"Rationale for decision {i}", "decided_by": "Agent"})
    res = await server.call_tool("get_project_board", {"target_tokens": 300})
    assert res.is_error is False
    assert len(res.content[0].text) > 0


@pytest.mark.asyncio
async def test_tool_get_project_board_health_alerts(test_db: Path):
    server = create_server(db_path=test_db)
    # in-progress task with no owner triggers warning
    await server.call_tool("update_task", {"task_id": "T-UNOWNED", "title": "Floating Work", "status": "in_progress", "assigned_to": None})
    res = await server.call_tool("get_project_board", {})
    text = res.content[0].text
    assert "Attention Required" in text
    assert "Unowned active task" in text


# ==============================================================================
# TOOL 5: get_project_summary (3 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_project_summary_clean(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("publish_context", {"key": "goal", "value": "Clean Project"})
    await server.call_tool("publish_context", {"key": "current_milestone", "value": "M1"})
    res = await server.call_tool("get_project_summary", {})
    assert res.is_error is False
    summary = res.structured_content
    assert summary["goal"] == "Clean Project"
    assert summary["current_milestone"] == "M1"
    assert summary["is_healthy"] is True


@pytest.mark.asyncio
async def test_tool_get_project_summary_counts(test_db: Path):
    server = create_server(db_path=test_db)
    await server.call_tool("record_decision", {"decision_id": "ADR-1", "title": "D1", "rationale": "R1", "decided_by": "user"})
    await server.call_tool("update_task", {"task_id": "T1", "title": "Task 1", "status": "in_progress", "assigned_to": "codex"})
    res = await server.call_tool("get_project_summary", {})
    summary = res.structured_content
    assert summary["total_decisions"] == 1
    assert summary["in_progress_tasks"] == 1


@pytest.mark.asyncio
async def test_tool_get_project_summary_unhealthy_on_unowned_task(test_db: Path):
    server = create_server(db_path=test_db)
    # in-progress task with no owner triggers unhealthiness
    await server.call_tool("update_task", {"task_id": "T-FLOAT", "title": "Unowned", "status": "in_progress", "assigned_to": None})
    res = await server.call_tool("get_project_summary", {})
    summary = res.structured_content
    assert summary["is_healthy"] is False
    assert "T-FLOAT" in summary["unowned_active_tasks"]


# ==============================================================================
# TOOL 6: get_recent_context (3 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_recent_context_empty(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_recent_context", {"limit": 5})
    assert res.is_error is False
    assert len(res.structured_content["result"]) == 0


@pytest.mark.asyncio
async def test_tool_get_recent_context_retrieval(test_db: Path):
    insert_turn("turn-1", "claude", "sess-1", "/repo", "user", "Hello server", None, db_path=test_db)
    insert_turn("turn-2", "claude", "sess-1", "/repo", "assistant", "Server ready", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_recent_context", {"limit": 10})
    assert res.is_error is False
    turns = res.structured_content["result"]
    assert len(turns) == 2
    assert turns[0]["id"] == "turn-1"
    assert turns[1]["id"] == "turn-2"


@pytest.mark.asyncio
async def test_tool_get_recent_context_source_filtering(test_db: Path):
    insert_turn("turn-a", "antigravity", "sess-1", "/repo", "user", "From Antigravity", None, db_path=test_db)
    insert_turn("turn-b", "codex", "sess-2", "/repo", "user", "From Codex", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_recent_context", {"source": "antigravity"})
    assert res.is_error is False
    turns = res.structured_content["result"]
    assert len(turns) == 1
    assert turns[0]["id"] == "turn-a"


# ==============================================================================
# TOOL 7: get_turn (3 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_turn_existing(test_db: Path):
    insert_turn("turn-exact", "claude", "sess-1", "/repo", "user", "Exact uncompressed string with flag --all", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_turn", {"turn_id": "turn-exact"})
    assert res.is_error is False
    turn = res.structured_content["result"]
    assert turn["id"] == "turn-exact"
    assert turn["content"] == "Exact uncompressed string with flag --all"


@pytest.mark.asyncio
async def test_tool_get_turn_not_found(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_turn", {"turn_id": "missing-id-999"})
    assert res.is_error is False
    assert "not found" in res.content[0].text


@pytest.mark.asyncio
async def test_tool_get_turn_preserves_multiline_and_indentation(test_db: Path):
    code = "def test():\n    x = 10\n    return x * 2\n"
    insert_turn("turn-code", "codex", "s1", None, "assistant", code, None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("get_turn", {"turn_id": "turn-code"})
    assert res.is_error is False
    assert res.structured_content["result"]["content"] == code


# ==============================================================================
# TOOL 8: search_historical_context (4 tests)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_search_historical_context_match(test_db: Path):
    insert_turn("turn-fts-1", "claude_code", "s1", "/repo", "user", "Implement OAuth2 PKCE security flow", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("search_historical_context", {"query": "OAuth2"})
    assert res.is_error is False
    text = res.content[0].text
    assert "Found 1 historical turn(s)" in text
    assert "OAuth2 PKCE security flow" in text


@pytest.mark.asyncio
async def test_tool_search_historical_context_porter_stemming(test_db: Path):
    insert_turn("turn-fts-stem", "antigravity", "s1", "/repo", "user", "We are connecting to the database server", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("search_historical_context", {"query": "connection"})
    assert res.is_error is False
    assert "Found 1 historical turn(s)" in res.content[0].text


@pytest.mark.asyncio
async def test_tool_search_historical_context_no_match(test_db: Path):
    server = create_server(db_path=test_db)
    res = await server.call_tool("search_historical_context", {"query": "nonexistentterm12345"})
    assert res.is_error is False
    assert "No historical turns matched query" in res.content[0].text


@pytest.mark.asyncio
async def test_tool_search_historical_context_filtered_by_source(test_db: Path):
    insert_turn("turn-c1", "claude_code", "s1", None, "assistant", "Fixed issue in parser", None, db_path=test_db)
    insert_turn("turn-c2", "codex", "s2", None, "assistant", "Fixed issue in parser", None, db_path=test_db)
    server = create_server(db_path=test_db)
    res = await server.call_tool("search_historical_context", {"query": "parser", "source": "claude_code"})
    assert res.is_error is False
    assert "Found 1 historical turn(s)" in res.content[0].text
    assert "CLAUDE_CODE" in res.content[0].text
