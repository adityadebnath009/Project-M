import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
def resolve_db_path(custom_path: Optional[str] = None) -> Path:
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
    # Default: project-scoped directory (.project-m/)
    cwd = Path.cwd().resolve()
    target_dir = cwd / ".project-m"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "state.db"
    except OSError:
        # Fallback if current directory is read-only
        home_target = Path.home() / ".project-m"
        home_target.mkdir(parents=True, exist_ok=True)
        return home_target / "global.db"



def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Creates an SQLite connection with WAL mode and row factory enabled.
    """
    target = db_path or resolve_db_path()
    conn = sqlite3.connect(str(target), timeout=10.0)
    conn.row_factory = sqlite3.Row

    # Concurrency and performance settings
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