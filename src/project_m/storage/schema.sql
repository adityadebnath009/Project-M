CREATE TABLE IF NOT EXISTS project_board (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    decided_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'in_progress', 'completed'
    assigned_to TEXT DEFAULT NULL,          -- client or agent name
    notes TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,                    -- e.g. 'antigravity:conv_id:step' or 'codex:item_id'
    source TEXT NOT NULL,                   -- 'antigravity', 'codex', 'claude'
    session_id TEXT NOT NULL,
    project_path TEXT,
    role TEXT NOT NULL,                     -- 'user', 'assistant'
    content TEXT NOT NULL,
    timestamp TEXT,                         -- original timestamp from the client log
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

--Indexing

CREATE INDEX IF NOT EXISTS idx_turns_source ON conversation_turns(source);
CREATE INDEX IF NOT EXISTS idx_turns_created ON conversation_turns(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);



-- Full-Text Search (FTS5) over historical conversation turns
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_turns_fts USING fts5(
    id UNINDEXED,
    source,
    session_id UNINDEXED,
    role,
    content,
    timestamp UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Real-time sync triggers
CREATE TRIGGER IF NOT EXISTS trg_turns_after_insert 
AFTER INSERT ON conversation_turns BEGIN
    INSERT INTO conversation_turns_fts (id, source, session_id, role, content, timestamp)
    VALUES (new.id, new.source, new.session_id, new.role, new.content, new.timestamp);
END;

CREATE TRIGGER IF NOT EXISTS trg_turns_after_delete 
AFTER DELETE ON conversation_turns BEGIN
    DELETE FROM conversation_turns_fts WHERE id = old.id;
END;