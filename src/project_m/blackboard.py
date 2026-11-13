"""
The Living Blackboard & Context Compiler for Project-M.

Compiles project state, binding architectural constraints, active task handoffs,
and recent ambient turns into a dense, verified Tier 1 briefing card (< 500 tokens).
Zero fuzzy paraphrasing: preserves exact parameters, file paths, and provenance IDs.
Uses tiktoken (cl100k_base) for exact token budgeting.
"""

import functools
from pathlib import Path
from typing import Any

import tiktoken

from project_m.adapters.antigravity import harvest_antigravity
from project_m.adapters.codex import harvest_codex
from project_m.storage.db import (
    get_board,
    get_decisions,
    get_recent_turns,
    get_tasks,
)


@functools.lru_cache(maxsize=1)
def _get_encoding() -> tiktoken.Encoding:
    """Caches the BPE tokenizer for sub-millisecond reuse across compiler runs."""
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """
    Accurately counts tokens using the cl100k_base BPE tokenizer.
    Falls back gracefully to heuristic if tokenizer initialization fails.
    """
    if not text:
        return 0
    try:
        encoding = _get_encoding()
        return len(encoding.encode(text))
    except Exception:
        return max(1, int(len(text) / 3.8))


def compile_briefing_card(
    db_path: Path | None = None,
    max_turns: int = 2,
    max_decisions: int = 5,
    target_tokens: int = 450,
) -> str:
    """
    Compiles the deterministic Tier 1 State Card.
    
    Structure:
    - 🎯 Goal & Binding Invariants (Lossless constraints)
    - 🏛️ Accepted Decisions (Verbatim parameters + provenance)
    - 📋 Active Tasks & Handoff Baton (Owners + completed summary)
    - ⚠️ Attention Required (Health alerts: unowned tasks, unverified completions)
    - 🔄 Ambient Context (Recent turns, budget-permitting)
    """
    board = get_board(db_path)
    decisions = get_decisions(limit=max_decisions, status="accepted", newest_first=True, db_path=db_path)
    in_progress_tasks = get_tasks(status="in_progress", db_path=db_path)
    pending_tasks = get_tasks(status="pending", db_path=db_path)
    completed_tasks = get_tasks(status="completed", db_path=db_path)

    sections: list[str] = []

    # 1. Header & Project Goal
    sections.append("# Project-M: Living Project Board")
    goal = board.get("goal", "Define project goals in project_board ('goal').")
    sections.append(f"**Goal**: {goal}")

    # 2. Binding Constraints (Verbatim technical parameters)
    constraints_raw = board.get("constraints", "")
    if constraints_raw:
        c_lines = ["### 🔒 Binding Constraints"]
        for line in constraints_raw.split("\n"):
            line = line.strip()
            if line:
                if not line.startswith("-") and not line.startswith("*"):
                    c_lines.append(f"- {line}")
                else:
                    c_lines.append(line)
        sections.append("\n".join(c_lines))

    # 3. Accepted Decisions (ADR Ledger with Provenance)
    if decisions:
        d_lines = ["### 🏛️ Active Decisions (Accepted)"]
        for d in decisions:
            decided_by = d.get("decided_by", "unknown")
            created_at = d.get("created_at", "")[:10]
            d_lines.append(
                f"- **[{d['id']}] {d['title']}**: {d['rationale']} "
                f"*(Recorded by {decided_by}, {created_at})*"
            )
        sections.append("\n".join(d_lines))

    # 4. Active Tasks & Handoff Baton
    if in_progress_tasks or pending_tasks or completed_tasks:
        t_lines = ["### 📋 Active Tasks"]
        for t in in_progress_tasks:
            owner = t.get("assigned_to") or "UNASSIGNED"
            notes = f" — *{t['notes']}*" if t.get("notes") else ""
            t_lines.append(f"- **[IN PROGRESS]** `{t['id']}`: {t['title']} (Owner: @{owner}){notes}")

        for t in pending_tasks:
            owner = f" (Assigned: @{t['assigned_to']})" if t.get("assigned_to") else ""
            t_lines.append(f"- **[PENDING]** `{t['id']}`: {t['title']}{owner}")

        if completed_tasks:
            t_lines.append(f"- *Completed ({len(completed_tasks)} tasks)*")
        sections.append("\n".join(t_lines))

    # 5. State Health & Governance Warnings (⚠️ Attention Required)
    warnings: list[str] = []
    for t in in_progress_tasks:
        if not t.get("assigned_to"):
            warnings.append(f"Unowned active task: `{t['id']}` has no assigned owner.")
    
    for t in completed_tasks:
        if not t.get("notes") or not t["notes"].strip():
            warnings.append(f"Unverified completion: `{t['id']}` completed without validation notes.")

    if not board.get("current_milestone"):
        warnings.append("No active milestone defined on project board ('current_milestone').")

    if warnings:
        w_lines = ["### ⚠️ Attention Required"]
        for w in warnings:
            w_lines.append(f"- {w}")
        sections.append("\n".join(w_lines))

    # Preliminary card text before ambient turns
    card_text = "\n\n".join(sections)
    current_tokens = count_tokens(card_text)

    # 6. Ambient Recent Turns (Tier 4 Snippets - budget permitting)
    if current_tokens < target_tokens and max_turns > 0:
        recent_turns = get_recent_turns(limit=max_turns, db_path=db_path)
        if recent_turns:
            turn_lines: list[str] = ["### 🔄 Recent Activity"]
            for turn in recent_turns:
                source = turn.get("source", "agent")
                role = turn.get("role", "message")
                content = turn.get("content", "").replace("\n", " ").strip()
                if len(content) > 120:
                    content = content[:117] + "..."
                turn_lines.append(f"- **{source}** ({role}): {content}")
            
            candidate_card = card_text + "\n\n" + "\n".join(turn_lines)
            if count_tokens(candidate_card) <= target_tokens + 50:
                card_text = candidate_card

    return card_text


def get_project_summary(db_path: Path | None = None) -> dict[str, Any]:
    """
    Returns a structured health and diagnostics snapshot of the project.
    Used by MCP tools and terminal dashboards for fast status verification.
    """
    board = get_board(db_path)
    decisions = get_decisions(limit=100, db_path=db_path)
    in_progress = get_tasks(status="in_progress", db_path=db_path)
    pending = get_tasks(status="pending", db_path=db_path)
    completed = get_tasks(status="completed", db_path=db_path)
    recent_turns = get_recent_turns(limit=1000, db_path=db_path)

    unowned = [t["id"] for t in in_progress if not t.get("assigned_to")]
    unverified = [t["id"] for t in completed if not (t.get("notes") or "").strip()]

    warnings: list[str] = []
    if unowned:
        warnings.append(f"{len(unowned)} in-progress task(s) unassigned.")
    if unverified:
        warnings.append(f"{len(unverified)} completed task(s) missing validation notes.")
    if not board.get("current_milestone"):
        warnings.append("No active milestone defined.")

    return {
        "goal": board.get("goal", ""),
        "current_milestone": board.get("current_milestone", ""),
        "total_decisions": len(decisions),
        "in_progress_tasks": len(in_progress),
        "pending_tasks": len(pending),
        "completed_tasks": len(completed),
        "total_turns": len(recent_turns),
        "is_healthy": len(unowned) == 0 and len(unverified) == 0,
        "warnings": warnings,
        "unowned_active_tasks": unowned,
        "unverified_completions": unverified,
    }


def sync_and_compile(
    project_cwd: Path | str | None = None,
    db_path: Path | None = None,
    target_tokens: int = 450,
) -> str:
    """
    Synchronizes fresh turns from local client transcripts (Antigravity & Codex)
    and returns the freshly compiled Tier 1 State Card.
    """
    harvest_antigravity(db_path=db_path)
    harvest_codex(project_cwd=project_cwd, db_path=db_path)
    return compile_briefing_card(db_path=db_path, target_tokens=target_tokens)


def export_project_state_md(
    output_path: Path,
    db_path: Path | None = None,
) -> Path:
    """
    Opt-in utility to export the compiled briefing card to a static Markdown file
    (e.g., PROJECT_STATE.md or .project-m/STATE.md).
    """
    card = compile_briefing_card(db_path=db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(card, encoding="utf-8")
    return output_path