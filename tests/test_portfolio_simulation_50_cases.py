"""
50 Comprehensive End-to-End Test Cases simulating the complete lifecycle of a Developer Portfolio Project.
Includes 20 back-and-forth messaging turns across Claude, Antigravity, and Codex, with ADRs, task handoffs, FTS5 search, and board verification.
"""

from pathlib import Path
import pytest

from project_m.server import create_server
from project_m.storage.db import init_db, insert_turn, get_board, get_decisions, get_tasks


PORTFOLIO_TURNS = [
    ("turn-p01", "claude", "sess-portfolio-1", "user", "I want to build a modern personal portfolio website for my software engineering projects."),
    ("turn-p02", "claude", "sess-portfolio-1", "assistant", "Great idea! Let us use Vanilla CSS for full control and lightweight load times, featuring a brutalist minimal design."),
    ("turn-p03", "claude", "sess-portfolio-1", "user", "Agreed. Let us record that we should not use heavy CSS frameworks like Tailwind."),
    ("turn-p04", "claude", "sess-portfolio-1", "assistant", "Recorded ADR-PORT-01: Use Vanilla CSS and CSS Grid instead of Tailwind."),
    ("turn-p05", "antigravity", "sess-portfolio-2", "user", "Now let us design the hero section with a dynamic canvas background."),
    ("turn-p06", "antigravity", "sess-portfolio-2", "assistant", "I am claiming TASK-HERO. Writing a zero-dependency HTML5 Canvas particle animation."),
    ("turn-p07", "antigravity", "sess-portfolio-2", "user", "Make sure the canvas pauses when the browser tab is hidden to save battery."),
    ("turn-p08", "antigravity", "sess-portfolio-2", "assistant", "Added visibility change listener. Hero section is completed and responsive."),
    ("turn-p09", "codex", "sess-portfolio-3", "user", "We need a Project Showcase grid that shows live demos and GitHub badges."),
    ("turn-p10", "codex", "sess-portfolio-3", "assistant", "Claiming TASK-PROJECT-GRID. Setting up responsive CSS grid with 300px minmax columns."),
    ("turn-p11", "codex", "sess-portfolio-3", "user", "Let us add Project-M as the featured case study on the top card."),
    ("turn-p12", "codex", "sess-portfolio-3", "assistant", "Featured card updated with Project-M architecture badge and 102 test pass indicator."),
    ("turn-p13", "claude", "sess-portfolio-4", "user", "How should we handle contact submissions without running a heavy backend?"),
    ("turn-p14", "claude", "sess-portfolio-4", "assistant", "Recorded ADR-PORT-02: Use Web3Forms or static email webhook endpoint with client-side regex validation."),
    ("turn-p15", "claude", "sess-portfolio-4", "user", "Start building the contact form modal."),
    ("turn-p16", "claude", "sess-portfolio-4", "assistant", "Started TASK-CONTACT with accessible dialog element and focus trapping."),
    ("turn-p17", "antigravity", "sess-portfolio-5", "user", "Let us audit performance. We need 100/100 on Google Lighthouse."),
    ("turn-p18", "antigravity", "sess-portfolio-5", "assistant", "Recorded ADR-PORT-03: Preload Google Fonts and optimize SVGs inline to avoid render blocking."),
    ("turn-p19", "codex", "sess-portfolio-6", "user", "Add SEO meta tags, OpenGraph previews, and Twitter cards."),
    ("turn-p20", "codex", "sess-portfolio-6", "assistant", "Added JSON-LD schema, canonical URLs, and dynamic Twitter card previews. Ready for deployment.")
]


@pytest.fixture
def portfolio_env(tmp_path: Path):
    db_path = tmp_path / "portfolio.db"
    init_db(db_path)
    server = create_server(db_path=db_path, project_cwd=tmp_path)
    return {"db": db_path, "server": server}


# --- GROUP 1: Ingesting 20 Individual Turns (Tests 1 to 20) ---

@pytest.mark.parametrize("turn_data", PORTFOLIO_TURNS)
def test_ingest_turn(portfolio_env, turn_data):
    turn_id, source, sess, role, content = turn_data
    inserted = insert_turn(turn_id, source, sess, "/projects/portfolio", role, content, None, db_path=portfolio_env["db"])
    assert inserted is True


# --- MASTER FIXTURE FOR ALL 20 TURNS + ADRS + TASKS + METADATA ---

@pytest.fixture
def full_portfolio(portfolio_env):
    db = portfolio_env["db"]
    server = portfolio_env["server"]

    # 1. Ingest all 20 turns
    for turn_id, source, sess, role, content in PORTFOLIO_TURNS:
        insert_turn(turn_id, source, sess, "/projects/portfolio", role, content, None, db_path=db)

    # 2. Metadata
    from project_m.storage.db import set_board_value, add_decision, add_task
    set_board_value("goal", "Build a zero-dependency high performance developer portfolio", db_path=db)
    set_board_value("current_milestone", "Milestone 2: Polish & Audit", db_path=db)
    set_board_value("tech_stack", "HTML5, Vanilla CSS, Canvas API, SQLite", db_path=db)
    set_board_value("deploy_target", "Cloudflare Pages", db_path=db)

    # 3. ADRs (3 accepted, 1 rejected)
    add_decision("ADR-PORT-01", "Use Vanilla CSS instead of Tailwind", "Keeps asset size under 15kb with zero build-step overhead", decided_by="claude", status="accepted", db_path=db)
    add_decision("ADR-PORT-02", "Web3Forms Static Webhook", "Serverless contact delivery without managing backend APIs", decided_by="claude", status="accepted", db_path=db)
    add_decision("ADR-PORT-03", "Preload Google Fonts and Inline SVGs", "Guarantees First Contentful Paint < 0.4s for Lighthouse 100", decided_by="antigravity", status="accepted", db_path=db)
    add_decision("ADR-PORT-04", "Google Analytics Tracker", "Rejected due to GDPR cookies and 45kb script bloat", decided_by="aditya", status="rejected", db_path=db)

    # 4. Tasks (3 completed, 1 in progress, 1 pending)
    add_task("TASK-HERO", "Build Hero Section with Canvas Particle Animation", status="completed", assigned_to="antigravity", notes="Completed with VisibilityChange API listener", db_path=db)
    add_task("TASK-PROJECT-GRID", "Implement Responsive Projects Grid", status="completed", assigned_to="codex", notes="Featuring Project-M with live link and badges", db_path=db)
    add_task("TASK-CONTACT", "Contact Form Modal", status="completed", assigned_to="codex", notes="Form verified with client regex", db_path=db)
    add_task("TASK-AUDIT", "Run Google Lighthouse Performance Audit", status="in_progress", assigned_to="claude", notes="Targeting 100 on Performance, Accessibility, and SEO", db_path=db)
    add_task("TASK-DOMAIN", "Configure Custom Domain on Cloudflare", status="pending", notes="Waiting on DNS propagation", db_path=db)

    return portfolio_env


# --- GROUP 2: Lossless Conversation Retrieval (Tests 21 to 25) ---

@pytest.mark.asyncio
async def test_21_verify_total_turns_count(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_recent_context", {"limit": 50})
    turns = res.structured_content["result"]
    assert len(turns) == 20


@pytest.mark.asyncio
async def test_22_get_exact_hero_turn(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_turn", {"turn_id": "turn-p06"})
    data = res.structured_content["result"]
    assert "TASK-HERO" in data["content"]
    assert data["source"] == "antigravity"


@pytest.mark.asyncio
async def test_23_get_exact_seo_turn(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_turn", {"turn_id": "turn-p20"})
    data = res.structured_content["result"]
    assert "JSON-LD schema" in data["content"]
    assert data["source"] == "codex"


@pytest.mark.asyncio
async def test_24_filter_turns_by_claude(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_recent_context", {"source": "claude", "limit": 20})
    turns = res.structured_content["result"]
    assert len(turns) == 8
    assert all(t["source"] == "claude" for t in turns)


@pytest.mark.asyncio
async def test_25_filter_turns_by_antigravity(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_recent_context", {"source": "antigravity", "limit": 20})
    turns = res.structured_content["result"]
    assert len(turns) == 6
    assert all(t["source"] == "antigravity" for t in turns)


# --- GROUP 3: Project Metadata & Governance Configuration (Tests 26 to 30) ---

@pytest.mark.asyncio
async def test_26_publish_portfolio_goal(full_portfolio):
    board = get_board(db_path=full_portfolio["db"])
    assert board["goal"] == "Build a zero-dependency high performance developer portfolio"


@pytest.mark.asyncio
async def test_27_publish_portfolio_milestone(full_portfolio):
    board = get_board(db_path=full_portfolio["db"])
    assert board["current_milestone"] == "Milestone 2: Polish & Audit"


@pytest.mark.asyncio
async def test_28_publish_portfolio_tech_stack(full_portfolio):
    board = get_board(db_path=full_portfolio["db"])
    assert "Canvas API" in board["tech_stack"]


@pytest.mark.asyncio
async def test_29_publish_portfolio_deployment_target(full_portfolio):
    board = get_board(db_path=full_portfolio["db"])
    assert board["deploy_target"] == "Cloudflare Pages"


@pytest.mark.asyncio
async def test_30_publish_context_overwrite_milestone(full_portfolio):
    server = full_portfolio["server"]
    await server.call_tool("publish_context", {"key": "current_milestone", "value": "Milestone 3: Final Launch"})
    assert get_board(db_path=full_portfolio["db"])["current_milestone"] == "Milestone 3: Final Launch"


# --- GROUP 4: Architectural Decisions (ADRs) (Tests 31 to 35) ---

@pytest.mark.asyncio
async def test_31_record_adr_vanilla_css(full_portfolio):
    decisions = get_decisions(db_path=full_portfolio["db"])
    d = [x for x in decisions if x["id"] == "ADR-PORT-01"][0]
    assert "Vanilla CSS" in d["title"]
    assert d["status"] == "accepted"


@pytest.mark.asyncio
async def test_32_record_adr_contact_form(full_portfolio):
    decisions = get_decisions(db_path=full_portfolio["db"])
    d = [x for x in decisions if x["id"] == "ADR-PORT-02"][0]
    assert "Web3Forms" in d["title"]
    assert d["status"] == "accepted"


@pytest.mark.asyncio
async def test_33_record_adr_font_preloading(full_portfolio):
    decisions = get_decisions(db_path=full_portfolio["db"])
    d = [x for x in decisions if x["id"] == "ADR-PORT-03"][0]
    assert "Preload Google Fonts" in d["title"]
    assert d["decided_by"] == "antigravity"


@pytest.mark.asyncio
async def test_34_record_adr_rejected_analytics(full_portfolio):
    server = full_portfolio["server"]
    board = await server.call_tool("get_project_board", {})
    # Rejected ADRs must NOT be in the active briefing card
    assert "Google Analytics Tracker" not in board.content[0].text


@pytest.mark.asyncio
async def test_35_verify_accepted_adrs_count(full_portfolio):
    decisions = get_decisions(db_path=full_portfolio["db"])
    accepted = [d for d in decisions if d["status"] == "accepted"]
    assert len(accepted) == 3


# --- GROUP 5: Tasks Lifecycle & Multi-Agent Baton Relay (Tests 36 to 40) ---

@pytest.mark.asyncio
async def test_36_verify_completed_task_hero(full_portfolio):
    tasks = get_tasks(db_path=full_portfolio["db"])
    t = [x for x in tasks if x["id"] == "TASK-HERO"][0]
    assert t["status"] == "completed"
    assert t["assigned_to"] == "antigravity"


@pytest.mark.asyncio
async def test_37_verify_completed_task_project_grid(full_portfolio):
    tasks = get_tasks(db_path=full_portfolio["db"])
    t = [x for x in tasks if x["id"] == "TASK-PROJECT-GRID"][0]
    assert t["status"] == "completed"
    assert "Project-M" in t["notes"]


@pytest.mark.asyncio
async def test_38_verify_completed_task_contact(full_portfolio):
    tasks = get_tasks(db_path=full_portfolio["db"])
    t = [x for x in tasks if x["id"] == "TASK-CONTACT"][0]
    assert t["status"] == "completed"
    assert t["assigned_to"] == "codex"


@pytest.mark.asyncio
async def test_39_verify_active_in_progress_task(full_portfolio):
    tasks = get_tasks(db_path=full_portfolio["db"])
    t = [x for x in tasks if x["id"] == "TASK-AUDIT"][0]
    assert t["status"] == "in_progress"
    assert t["assigned_to"] == "claude"


@pytest.mark.asyncio
async def test_40_verify_pending_future_task(full_portfolio):
    tasks = get_tasks(db_path=full_portfolio["db"])
    t = [x for x in tasks if x["id"] == "TASK-DOMAIN"][0]
    assert t["status"] == "pending"


# --- GROUP 6: FTS5 Full-Text Search across Portfolio Turns (Tests 41 to 45) ---

@pytest.mark.asyncio
async def test_41_search_canvas_particle(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("search_historical_context", {"query": "particle"})
    assert "Found 1 historical turn(s)" in res.content[0].text
    assert "HTML5 Canvas particle animation" in res.content[0].text


@pytest.mark.asyncio
async def test_42_search_tailwind_discussion(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("search_historical_context", {"query": "Tailwind"})
    assert "Found 2 historical turn(s)" in res.content[0].text
    assert "ADR-PORT-01" in res.content[0].text


@pytest.mark.asyncio
async def test_43_search_with_porter_stemming_visibility(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("search_historical_context", {"query": "visibility"})
    assert "Found 1 historical turn(s)" in res.content[0].text
    assert "visibility change listener" in res.content[0].text


@pytest.mark.asyncio
async def test_44_search_project_m_mention(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("search_historical_context", {"query": "Project-M"})
    assert "Found 2 historical turn(s)" in res.content[0].text
    assert "top card" in res.content[0].text


@pytest.mark.asyncio
async def test_45_search_filtered_by_codex(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("search_historical_context", {"query": "schema", "source": "codex"})
    assert "Found 1 historical turn(s)" in res.content[0].text
    assert "JSON-LD" in res.content[0].text


# --- GROUP 7: State Card Compilation, Token Budgeting & Summary (Tests 46 to 50) ---

@pytest.mark.asyncio
async def test_46_state_card_contains_all_active_portfolio_data(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_project_board", {})
    text = res.content[0].text
    assert "# Project-M: Living Project Board" in text
    assert "zero-dependency high performance developer portfolio" in text
    assert "[ADR-PORT-01]" in text
    assert "[ADR-PORT-02]" in text
    assert "[ADR-PORT-03]" in text
    assert "TASK-AUDIT" in text
    assert "@claude" in text


@pytest.mark.asyncio
async def test_47_state_card_under_450_tokens(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_project_board", {"target_tokens": 450})
    text = res.content[0].text
    from project_m.blackboard import count_tokens
    tokens = count_tokens(text)
    assert tokens <= 450


@pytest.mark.asyncio
async def test_48_project_summary_diagnostics(full_portfolio):
    server = full_portfolio["server"]
    res = await server.call_tool("get_project_summary", {})
    summary = res.structured_content
    assert summary["goal"] == "Build a zero-dependency high performance developer portfolio"
    assert "Milestone" in summary["current_milestone"]
    assert summary["total_decisions"] == 4
    assert summary["in_progress_tasks"] == 1
    assert summary["completed_tasks"] == 3
    assert summary["pending_tasks"] == 1
    assert summary["total_turns"] == 20
    assert summary["is_healthy"] is True


@pytest.mark.asyncio
async def test_49_project_summary_unhealthy_alert_trigger(full_portfolio):
    server = full_portfolio["server"]
    await server.call_tool("update_task", {"task_id": "ORPHAN-TASK", "title": "Unowned audit", "status": "in_progress", "assigned_to": None})
    res = await server.call_tool("get_project_summary", {})
    summary = res.structured_content
    assert summary["is_healthy"] is False
    assert "ORPHAN-TASK" in summary["unowned_active_tasks"]


@pytest.mark.asyncio
async def test_50_end_to_end_roundtrip_new_session_awareness(full_portfolio):
    server = full_portfolio["server"]
    board_res = await server.call_tool("get_project_board", {})
    board = board_res.content[0].text
    
    # New agent knows what stack to use without asking user:
    assert "Vanilla CSS instead of Tailwind" in board
    # New agent knows what work is active:
    assert "TASK-AUDIT" in board
    # New agent knows who owns it:
    assert "@claude" in board
