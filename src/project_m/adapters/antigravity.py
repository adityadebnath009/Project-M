import json
import re
from pathlib import Path
from typing import Any, Optional

from rich.json import JSON

from project_m.storage.db import insert_turn


def find_active_transcript_path(
        conversation_id:str | None = None,
        base_dir: Path | None = None

) -> Path | None:
    
    
    brain_root = base_dir or (Path.home()/".gemini"/"antigravity"/"brain")
    if not brain_root.exists():
        return None
    if conversation_id:
        target = brain_root / conversation_id / ".system_generated"/"logs"/"transcript.jsonl"
        return target if target.exists() else None

    candidates = list(brain_root.glob("*/.system_generated/logs/transcript.jsonl"))

    if not candidates:
        return None

    candidates.sort(key = lambda p: p.stat().st_mtime, reverse  = True)

    return candidates[0]



def clean_turn_content(raw_text: str, max_chars: int = 2000) -> str:

    if not raw_text:
        return ""
    # Remove additional metadata blocks
    cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", raw_text, flags=re.DOTALL)
    # Remove system message blocks
    cleaned = re.sub(r"<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>", "", cleaned, flags=re.DOTALL)
    # Strip user request tags
    cleaned = cleaned.replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "")
    
    cleaned = cleaned.strip()
    # Length capping to protect token limits
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "... [truncated]"
    return cleaned

def parse_transcript_line(line_str: str, session_id: str) -> dict[str, Any] | None:
    line_str = line_str.strip()
    if not line_str:
        return None

    try:
        data = json.loads(line_str)
    except json.JSONDecodeError:
        return None


    step_index = data.get("step_index")
    source = data.get("source")
    step_type = data.get("type")


    if step_type=="USER_INPUT" or source=="USER_EXPLICIT":
        role = "user"
    elif step_type=="PLANNER_RESPONSE" or source == "MODEL":
        role = "assistant"

    else:
        return None

    raw_content = data.get("content")

    if not raw_content or not isinstance(raw_content, str):
        return None

    cleaned_content = clean_turn_content(raw_content)

    if not cleaned_content:
        return None

    timestamp = data.get("created_at")
    turn_id = f"antigravity:{session_id}:{step_index}"
    return {
        "turn_id": turn_id,
        "source": "antigravity",
        "session_id": session_id,
        "role": role,
        "content": cleaned_content,
        "timestamp": timestamp,
    }

def harvest_antigravity(
        transcript_path: Path | None = None,
        session_id: str | None = None,
        db_path: Path | None = None
):
    target_path = transcript_path or find_active_transcript_path(session_id)
    if not target_path or not target_path.exists():
        return 0

    if session_id:
        actual_session_id = session_id
    else:
    # Try to extract the conversation folder name, fallback to 'default' if shallow
        try:
            folder_name = target_path.parent.parent.parent.name
            actual_session_id = folder_name if folder_name else "default"
        except (IndexError, AttributeError):
            actual_session_id = "default"

    new_turns_count = 0
    with open(target_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            turn = parse_transcript_line(line, actual_session_id)
            if not turn:
                continue
            inserted = insert_turn(
                turn_id=turn["turn_id"],
                source=turn["source"],
                session_id=turn["session_id"],
                role=turn["role"],
                content=turn["content"],
                timestamp=turn["timestamp"],
                db_path=db_path,
            )
            if inserted:
                new_turns_count += 1
    return new_turns_count