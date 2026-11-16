from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from project_m.blackboard import (
    sync_and_compile,
    get_project_summary as fetch_project_summary
    )
from project_m.storage.db import (
    add_decision,
    add_task,
    get_recent_turns,
    get_tasks,
    set_board_value,
)
from project_m.storage.db import (
    get_turn as db_get_turn,
)


def create_server(db_path: Path | None = None,
                  project_cwd: Path | str | None = None) -> MCPServer:
    """
    Factory function creating an MCPServer instance with all Project-M tools registered.
    Accepts optional db_path and project_cwd for test isolation.
    """
    app = MCPServer("project_m")

    @app.tool()
    def get_project_board(target_tokens: int = 450) -> str:
        """
        Retrieves the living Tier 1 Project State Card (< 500 tokens).
        Call this tool at the beginning of a session or whenever you need situational 
        awareness of the project. It synchronizes recent turns from local client transcripts 
        (Antigravity and Codex) and compiles a high-density, deterministic markdown card.
        Contains:
          - 🎯 Project Goal & Scope
          - 🔒 Binding Invariants (lossless constraints, exact PRAGMAs, paths, versions)
          - 🏛️ Active Architectural Decisions (ADR IDs, titles, rationale, author, date)
          - 📋 Active Tasks & Handoff Baton (in-progress items with @owner, pending tasks)
          - ⚠️ Attention Required (health alerts: unowned tasks, unverified completions)
          - 🔄 Recent Ambient Activity (recent client messages, budget permitting)
        Args:
            target_tokens: Desired token budget ceiling for the briefing card (default: 450).
                           Enforced accurately via the BPE tokenizer.
        Returns:
            str: Clean Markdown-formatted Tier 1 State Card ready to be placed directly 
                 into your context window without prompt bloat.
        """
        return sync_and_compile(
            project_cwd=project_cwd,
            db_path=db_path,
            target_tokens=target_tokens,
        )
    @app.tool()
    def record_decision(
        decision_id: str,
        title: str,
        rationale: str,
        decided_by: str = "agent",
        status: str = "accepted",
    ) -> str:
        """
        Records or updates an Architectural Decision Record (ADR) in Tier 2.

        Call this tool whenever you establish a technical rule, make an architectural 
        choice, or change an existing convention. Prevents decision drift and ensures 
        subsequent agents (Claude, Codex, Antigravity) follow the agreed specification.

        Lifecycle:
          - 'accepted': Active binding decision (automatically visible on Tier 1 State Card).
          - 'proposed': Under review or draft; not yet binding.
          - 'superseded': Replaced by a newer ADR; archived in Tier 2 history.
          - 'rejected': Proposed but explicitly abandoned with reason in rationale.

        Formatting Rule:
          Preserve exact technical tokens in 'rationale' (e.g. file paths, PRAGMA flags,
          error codes, function signatures). Avoid fuzzy narrative paraphrasing.

        Args:
            decision_id: Unique identifier string (e.g., 'ADR-001', 'ADR-STORAGE-WAL').
            title: Short, descriptive title of the decision.
            rationale: Verbatim technical justification, constraints, and parameters.
            decided_by: Name or identity of the decider (e.g., 'claude', 'codex', 'human').
            status: Decision status ('accepted', 'proposed', 'superseded', 'rejected').

        Returns:
            str: Confirmation message with the recorded decision ID and status.
        """
        add_decision(
            decision_id=decision_id,
            title=title,
            rationale=rationale,
            decided_by=decided_by,
            status=status,
            db_path=db_path,
        )
        return f"Successfully recorded decision [{decision_id}]: '{title}' with status '{status}'."

    @app.tool()
    def publish_context(
        key: str,
        value: str,
    ) -> str:
        """
        Publishes or updates a key-value pair on the living project board.

        Call this tool to record persistent high-level metadata that all agents need 
        to see, such as project goals, active milestones, or shared environment variables.

        Standard Keys:
          - 'goal': The primary objective of the repository/project.
          - 'current_milestone': The current phase or sprint objective (e.g., 'Phase 4: FastMCP').
          - 'constraints': Line-delimited or bulleted technical invariants.

        Args:
            key: The configuration or metadata key (e.g., 'current_milestone', 'constraints').
            value: The string value to store. If storing constraints, use newline-separated 
                   bullet points with exact technical parameters.

        Returns:
            str: Confirmation message acknowledging the stored key-value pair.
        """
        set_board_value(key=key, value=value, db_path=db_path)
        return f"Successfully updated project board key '{key}'."


    @app.tool()
    def update_task(
        task_id: str,
        status: str,
        title: str | None = None,
        assigned_to: str | None = None,
        notes: str | None = None,
    ) -> str:
        """
        Updates the status, owner, or validation notes of a task in the Tier 3 Task Graph.

        Call this tool to claim work, hand off responsibility to another agent, or mark 
        work as completed with proof of verification.

        Status Conventions:
          - 'pending': Queued task waiting to be started.
          - 'in_progress': Currently being worked on. MUST have an 'assigned_to' owner 
                           to avoid triggering '⚠️ Attention Required' health warnings.
          - 'completed': Finished work. MUST include validation notes (e.g., test results, 
                         verification commands) for audit trail compliance.

        Args:
            task_id: Unique task identifier (e.g., 'task-04', 'FEAT-BLACKBOARD').
            status: Target status ('pending', 'in_progress', 'completed').
            title: Optional updated title if creating or renaming the task.
            assigned_to: Agent or user claiming the baton (e.g., 'claude', 'antigravity', 'human').
            notes: Progress updates or verification proof (e.g., '46/46 tests passed in 0.41s').

        Returns:
            str: Confirmation message reflecting the updated task state.
        """
        # Check if the task already exists to preserve existing fields
        existing_tasks = [t for t in get_tasks(db_path=db_path) if t["id"] == task_id]
        if existing_tasks:
            existing = existing_tasks[0]
            new_title = title if title is not None else existing["title"]
            new_owner = assigned_to if assigned_to is not None else existing.get("assigned_to")
            new_notes = notes if notes is not None else existing.get("notes", "")
            add_task(
                task_id=task_id,
                title=new_title,
                status=status,
                assigned_to=new_owner,
                notes=new_notes,
                db_path=db_path,
            )
        else:
            add_task(
                task_id=task_id,
                title=title or task_id,
                status=status,
                assigned_to=assigned_to,
                notes=notes or "",
                db_path=db_path,
            )

        owner_info = f", Owner: @{assigned_to}" if assigned_to else ""
        return f"Successfully updated task [{task_id}] (Status: {status}{owner_info})."


    @app.tool()
    def get_recent_context(
        limit: int = 10,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieves recent conversation turns across all local AI clients.

        Call this tool when you need ambient historical context from previous chat sessions 
        without leaving the MCP workflow. Reads from the unified SQLite conversation ledger.

        Args:
            limit: Maximum number of chronological turns to return (default: 10).
            source: Optional client filter: 'antigravity', 'codex', or None (for all clients).

        Returns:
            list[dict[str, Any]]: Chronologically ordered list of turn dictionaries, each containing:
                                  - 'id': Deterministic turn ID (e.g., 'antigravity:caa4cbcc:447')
                                  - 'source': Originating client ('antigravity', 'codex')
                                  - 'session_id': Session or thread identifier
                                  - 'role': Message sender ('user', 'assistant')
                                  - 'content': Raw turn text
                                  - 'timestamp': ISO 8601 creation time
        """
        return get_recent_turns(source=source, limit=limit, db_path=db_path)

    @app.tool()
    def get_turn(
        turn_id: str,
    ) -> dict[str, Any] | str:
        """
        Retrieves a single uncompressed, un-summarized conversation turn by its exact ID (Tier 4).

        This is the core of Project-M's Lossless Provenance Engine. When an ADR or task 
        references a source anchor (e.g., 'turn:antigravity:caa4cbcc:447'), call this tool 
        to retrieve the 100% complete, unedited historical message.

        Guarantees:
          - Zero detail loss: Full terminal outputs, code snippets, and error tracebacks.
          - Zero hallucination: Exact raw payload as ingested from the local client transcript.

        Args:
            turn_id: Deterministic turn identifier (e.g., 'antigravity:caa4cbcc:447' or 'codex:msg-982').

        Returns:
            dict[str, Any]: Complete turn record with source, role, timestamp, and uncompressed content.
            str: Not-found message if the ID does not exist in the database.
        """
        turn = db_get_turn(turn_id=turn_id, db_path=db_path)
        if not turn:
            return f"Turn '{turn_id}' not found in local project ledger."
        return turn

    
    @app.tool()
    def get_project_summary() -> dict[str, Any]:
        """
        Retrieves a structured diagnostics and health summary of the project.

        Call this tool for automated programmatic verification of repository state health.
        Returns exact counts and validation warnings without requiring Markdown parsing.

        Returns:
            dict[str, Any]: Diagnostic record containing:
                - 'goal': Active project goal
                - 'current_milestone': Current milestone
                - 'total_decisions': Total recorded ADRs
                - 'in_progress_tasks': Count of active tasks
                - 'pending_tasks': Count of queued tasks
                - 'completed_tasks': Count of finished tasks
                - 'total_turns': Total recorded chat turns
                - 'is_healthy': True if zero unowned active tasks and zero unverified completions
                - 'warnings': List of active governance warnings
                - 'unowned_active_tasks': List of task IDs missing an assigned owner
                - 'unverified_completions': List of task IDs completed without notes
        """
        return fetch_project_summary(db_path=db_path)
    
    return app

    



server = create_server()

def main() -> None:
    """CLI entrypoint for running the MCP server over stdio."""
    server.run()

if __name__ == "__main__":
    main()
