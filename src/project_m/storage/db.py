import sqlite3
from pathlib import Path
from typing import Any, Optional

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def resolve_db_path(custom_path: str | None = None) -> Path:
    """
    Resolves the SQLite database path with project-first priority.
    
    1. If custom_path is provided, use it directly.
    2. If in a project folder, use <current_dir>/.project-m/state.db.
    3. Fallback to ~/.project-m/global.db.
    """
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    cwd = Path.cwd().resolve()
    target_dir = cwd / ".project-m"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "state.db"
    except OSError:
        home_target = Path.home() / ".project-m"
        home_target.mkdir(parents=True, exist_ok=True)
        return home_target / "global.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Creates an SQLite connection with WAL mode and row factory enabled."""
    target = db_path or resolve_db_path()
    conn = sqlite3.connect(str(target), timeout=10.0)
    conn.row_factory = sqlite3.Row

    with conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")

    return conn


def init_db(db_path: Path | None = None) -> None:
    """Idempotently initializes database tables from schema.sql."""
    conn = get_connection(db_path)
    with conn, open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.close()


# --- Project Board Operations ---

def set_board_value(key: str, value: str, db_path: Path | None = None) -> None:
    """Sets or updates a key-value pair on the living project board."""
    init_db(db_path)
    conn = get_connection(db_path)
    query = """
    INSERT INTO project_board (key, value, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP;
    """
    with conn:
        conn.execute(query, (key, value))
    conn.close()


def get_board(db_path: Path | None = None) -> dict[str, str]:
    """Retrieves all key-value pairs from the project board."""
    init_db(db_path)
    conn = get_connection(db_path)
    rows = conn.execute("SELECT key, value FROM project_board;").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


# --- Architectural Decisions Operations ---

def add_decision(
    decision_id: str,
    title: str,
    rationale: str,
    decided_by: str,
    status: str = "accepted",
    db_path: Path | None = None,
) -> None:
    """Records an architectural decision using an atomic upsert."""
    init_db(db_path)
    conn = get_connection(db_path)
    query = """
    INSERT INTO decisions (id, title, rationale, status, decided_by, created_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        rationale = excluded.rationale,
        decided_by = excluded.decided_by,
        status = excluded.status;
    """
    with conn:
        conn.execute(query, (decision_id, title, rationale, status, decided_by))
    conn.close()


def get_decisions(
    limit: int = 10, 
    status:str | None = None,
    newest_first: bool = False,
    db_path: Path | None = None
) -> list[dict[str, Any]]:

    """
    Retrieves decisions from the ADR ledger.
    
    - If status is provided, filters by that status (e.g. 'accepted').
    - If newest_first is True, orders by created_at DESC (latest first).
    - If newest_first is False (default), orders chronologically (oldest first).
    """
    init_db(db_path)
    conn = get_connection(db_path)

    order = "DESC" if newest_first else "ASC"

    if status:
        query = f" SELECT * FROM decisions WHERE status = ? ORDER BY created_at {order}, id {order} LIMIT ?;"
        rows = conn.execute(query, (status, limit)).fetchall()
    else:
        query = f"SELECT * FROM decisions ORDER BY created_at {order}, id {order} LIMIT ?;"
        rows = conn.execute(query, (limit,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# --- Tasks Operations ---

def add_task(
    task_id: str,
    title: str,
    status: str = "pending",
    assigned_to: str | None = None,
    notes: str = "",
    db_path: Path | None = None,
) -> None:
    """Adds or updates a task on the living project board."""
    init_db(db_path)
    conn = get_connection(db_path)
    query = """
    INSERT INTO tasks (id, title, status, assigned_to, notes, updated_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        status = excluded.status,
        assigned_to = excluded.assigned_to,
        notes = excluded.notes,
        updated_at = CURRENT_TIMESTAMP;
    """
    with conn:
        conn.execute(query, (task_id, title, status, assigned_to, notes))
    conn.close()


def update_task_status(
    task_id: str,
    status: str,
    notes: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Updates the status and optional notes of an existing task.
    Returns True if the task was found and updated, False otherwise.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    if notes is not None:
        query = "UPDATE tasks SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;"
        params = (status, notes, task_id)
    else:
        query = "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;"
        params = (status, task_id)

    with conn:
        cursor = conn.execute(query, params)
        updated = cursor.rowcount > 0
    conn.close()
    return updated


def get_tasks(
    status: str | None = None, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Retrieves tasks, optionally filtered by status ('pending', 'in_progress', 'completed')."""
    init_db(db_path)
    conn = get_connection(db_path)
    if status:
        query = "SELECT * FROM tasks WHERE status = ? ORDER BY updated_at DESC;"
        rows = conn.execute(query, (status,)).fetchall()
    else:
        query = "SELECT * FROM tasks ORDER BY updated_at DESC;"
        rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Conversation Turns Operations ---

def insert_turn(
    turn_id: str,
    source: str,
    session_id: str,
    project_path: str | None = None,
    role: str = "user",
    content: str = "",
    timestamp: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Inserts a raw conversation turn.
    Returns True if inserted, False if it was a duplicate (deduplication).
    """
    init_db(db_path)
    conn = get_connection(db_path)
    query = """
    INSERT OR IGNORE INTO conversation_turns (
        id, source, session_id, project_path, role, content, timestamp
    ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    with conn:
        cursor = conn.execute(
            query,
            (turn_id, source, session_id, project_path, role, content, timestamp),
        )
        inserted = cursor.rowcount > 0
    conn.close()
    return inserted


def get_recent_turns(
    source: str | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Fetches recent conversation turns across all clients or filtered by source.
    Returns them in chronological order.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    if source and source != "all":
        query = """
        SELECT id, source, session_id, project_path, role, content, timestamp, created_at
        FROM conversation_turns
        WHERE source = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?;
        """
        rows = conn.execute(query, (source, limit)).fetchall()
    else:
        query = """
        SELECT id, source, session_id, project_path, role, content, timestamp, created_at
        FROM conversation_turns
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?;
        """
        rows = conn.execute(query, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_turn(
    turn_id: str,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """
    Retrieves a single uncompressed conversation turn by its deterministic turn_id.
    Guarantees zero loss of detail for Progressive Disclosure (Tier 4).
    """
    init_db(db_path)
    conn = get_connection(db_path)
    query = "SELECT * FROM conversation_turns WHERE id = ?;"
    row = conn.execute(query, (turn_id,)).fetchone()
    conn.close()
    return dict(row) if row else None