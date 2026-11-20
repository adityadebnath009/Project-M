<div align="center">

<img src="assets/logo.png" alt="Project-M Logo" width="220" />

# Project-M

### The Ambient, Local-First Context Engine & Blackboard for AI Agents

Switch between **Claude Desktop**, **OpenAI Codex**, and **Google Antigravity** without losing state.<br/>
Deterministic 4-tier context compilation. Sub-2ms latency. Zero cloud dependencies.

<br/>

[![Tests](https://img.shields.io/badge/tests-183%20passed-10B981?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/adityadebnath009/Project-M)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-F59E0B?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Protocol](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-EA580C?style=for-the-badge&logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![Storage](https://img.shields.io/badge/storage-SQLite%20WAL%20(Local)-3B82F6?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Latency](https://img.shields.io/badge/compile-<2ms%20briefing-8B5CF6?style=for-the-badge)](https://github.com/adityadebnath009/Project-M)
[![License](https://img.shields.io/badge/license-MIT-gray?style=for-the-badge)](LICENSE)

[![Reviewed by HOL Guard](https://img.shields.io/badge/HOL_Guard%20|%20project_m-2E5AAC?logo=shield&logoColor=white)](https://hol.org/guard/extensions/mcp.project-m)
[![mcp-project-m MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/adityadebnath009/Project-M/badges/score.svg)](https://glama.ai/mcp/servers/adityadebnath009/Project-M)
[![M8ven Score](https://m8ven.ai/badge/mcp/adityadebnath009-project-m-177ur4?v=c5dbde172e8a36a3f855037e0982192b)](https://m8ven.ai/mcp/adityadebnath009-project-m-177ur4?s=readme)

<br/>

[Overview](#-overview) •
[Architecture](#-architecture) •
[Interactive REPL & CLI](#-developer-cli--interactive-repl) •
[FastMCP Tools](#-fastmcp-tools-reference) •
[Quickstart](#-quickstart) •
[Verification](#-verification--tests)

---

</div>

## 📌 Overview

Frontier software engineering in 2026 relies on a multi-agent stack:
* **Google Antigravity** for whole-repo refactoring, test harness execution, and deep agentic planning.
* **Anthropic Claude Desktop** for high-level architectural brainstorming, formal reasoning, and PR reviews.
* **OpenAI Codex / ChatGPT** for fast terminal scratchpads, bash script verification, and quick iterations.

### The Problem: Context Amnesia
Every time you switch between these assistants, **your context breaks**. Decisions agreed upon in Claude Desktop are invisible to Antigravity. Tasks started in Antigravity are unknown to Codex. Developers waste thousands of tokens and manual hours copy-pasting diffs, status updates, and architectural constraints across disconnected chat windows.

### The Solution: Project-M
**Project-M** is a local-first Model Context Protocol (MCP) server and verified project-state compiler. It passively harvests session turns, maintains an immutable ledger of Architectural Decision Records (ADRs), synchronizes task batons, and serves a deterministic **Tier 1 Briefing Card (< 450 tokens)** to any requesting AI agent in **under 2 milliseconds**.

* **100% Local**: Runs on SQLite WAL mode on your machine. No accounts, no telemetry, no cloud lock-in.
* **Zero API Costs**: No paid embedding syncs or third-party vector databases.
* **Lossless Telemetry**: Raw conversation logs are preserved permanently in Tier 4 cold storage while models only consume compressed, high-density state cards.
* **Clean Stdio Isolation**: MCP JSON-RPC 2.0 communication runs unpolluted over `stdout`, while branded status cards route safely to `stderr`.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph AI Clients ["Frontier AI Clients"]
        A["Google Antigravity<br/>(IDE & Workspace)"]
        B["Anthropic Claude Desktop<br/>(Architectural Planner)"]
        C["OpenAI Codex / ChatGPT<br/>(Terminal & CLI)"]
    end

    subgraph Harvesters ["Ambient Log Harvesters"]
        H1["Antigravity Harvester<br/>JSONL Stream Reader"]
        H2["Codex Harvester<br/>Read-Only SQLite (?mode=ro)"]
    end

    subgraph Core ["Project-M Core Engine"]
        DB[("Storage Layer<br/>SQLite WAL Mode<br/>(.project-m/state.db)")]
        COMP["State Compiler<br/>(Lossless 4-Tier Blackboard)"]
        SERVER["FastMCP Server<br/>(JSON-RPC 2.0 over stdio)"]
    end

    A -. writes transcript .-> H1 -->|deduplicated turns| DB
    C -. writes session .-> H2 -->|deduplicated turns| DB
    DB <--> COMP
    COMP <--> SERVER
    SERVER <==>|MCP Tools & Resources| B
    SERVER <==>|MCP Tools & Resources| A
    SERVER <==>|MCP Tools & Resources| C
```

### The 4-Tier Memory Hierarchy

| Tier | Name | Target Size | Latency | Purpose & Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Living State Card** | `< 450 tokens` | `< 2 ms` | Deterministic markdown briefing compiled via `tiktoken`. Injected automatically into every agent turn. Contains active goal, active stack, in-progress tasks, and recent ADRs. |
| **Tier 2** | **ADR Ledger** | `< 1,200 tokens` | `< 5 ms` | Immutable record of architectural decisions (`id`, `title`, `rationale`, `status`, `decided_by`). Prevents agents from reversing past architectural decisions. |
| **Tier 3** | **Task Baton Graph** | Dynamic | `< 5 ms` | Cross-agent task ownership (`task_id`, `status`, `assigned_to`, `notes`). Coordinates handoffs between `@claude`, `@antigravity`, and `@codex`. |
| **Tier 4** | **Lossless Cold Storage** | Unlimited | Indexed | Exact raw session transcripts (`transcript.jsonl` and session databases) preserved permanently with content hashes. Never sent to models directly; inspected on-demand via `get_turn()`. |

### ⚡ Lexical Search with SQLite FTS5 (BM25 Ranking)

Instead of relying on expensive third-party vector databases or paid embedding APIs, Project-M uses SQLite's native **FTS5 (Full-Text Search 5)** virtual table engine with **BM25 probabilistic relevance ranking**:

* **Porter Stemming (`tokenize = 'porter unicode61'`)**: Automatically matches word inflections (e.g. searching `"connecting"` matches `"connect"`, `"connected"`, and `"connection"`).
* **Okapi BM25 Ranking (`ORDER BY rank`)**: Scores results based on term frequency and document length saturation, returning the most relevant historical turns in **sub-3 milliseconds**.
* **Zero-Lag Database Triggers**: Automatically updates the `conversation_turns_fts` index via C-level SQLite triggers (`AFTER INSERT`, `AFTER DELETE`) as turns arrive from Antigravity, Codex, or Claude.
* **100% Offline & Free**: Instant semantic discovery over tens of thousands of past turns with zero token expenditure.

---

## 💻 Developer CLI & Interactive REPL

Project-M features a Claude-Code-inspired terminal interface with the official **Brutalist Chevron Monogram Logo**, live hardware specs, and a rich interactive REPL.

```
   ██████╗         ██████╗       adityadebnath@Project-M(MCP)  ● REPL ACTIVE
   ████████╗     ████████║       ──────────────────────────────────────────────
   ██╔══████╗   ████╔══██║       Engine:     4-Tier Lossless State Compiler
   ██║  ╚████╗ ████╔╝  ██║       Storage:    SQLite WAL (.project-m/state.db)
   ██║   ╚████████╔╝   ██║       Clients:    Claude Desktop • Codex • Antigravity
   ██║    ╚═══════╝    ██║       ADRs:       5 Accepted (Tier 2 Ledger)
   ██║                 ██║       Tasks:      1 in progress (Owner: @claude)
   ╚═╝                 ╚═╝       Telemetry:  424 raw turns recorded (Tier 4)
                                 Invariant:  100% Local • Zero Paid APIs
                                 Compile:    1.2ms latency (167/450 tokens)

                                 ● ● ● ● ● ● ● ●
  Type /help for commands  •  Press Tab to autocomplete  •  /exit to quit

project-m ❯ 
```

### REPL Slash Commands

Launch the interactive shell anytime with `uv run project-m` or `uv run project-m shell`:

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/board` | `[--target-tokens 450]` | Renders the compiled Tier 1 State Card in real time. |
| `/status` | — | Displays database size, WAL status, schema integrity, and active warnings. |
| `/tasks` | — | Displays the live task backlog with owner badges. |
| `/task` | `<id> <status> <@owner> <notes>` | Adds or updates a task baton (e.g. `/task auth-1 in_progress @claude "OAuth2"`). |
| `/decisions` | — | Lists all accepted Architectural Decision Records (ADRs). |
| `/decide` | `<id> <title> <rationale>` | Records a binding ADR (e.g. `/decide ADR-004 "Use SQLite WAL" "Zero locks"`). |
| `/fetch` | — | Displays the signature Neofetch-style system and compiler specifications. |
| `/export` | `[filename.md]` | Exports the living project state card to a portable Markdown document. |
| `/setup` | `[all \| claude \| codex]` | Runs the automated one-click client installer. |
| `/clear` | — | Clears the terminal screen. |
| `/exit` | — | Exits the shell cleanly. |

---

## ⚡ FastMCP Tools Reference

Project-M exposes 8 standard tools over Model Context Protocol:

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_project_board` | `target_tokens: int = 450` | Returns the deterministic Tier 1 Living State Card (< 450 tokens) containing current goal, tech stack, active tasks, and recent ADRs. |
| `record_decision` | `id, title, rationale, decided_by, status` | Posts a new Architectural Decision Record (ADR) to Tier 2. Prevents conflicting implementation paths. |
| `update_task` | `task_id, status, assigned_to, notes` | Updates or creates a task baton in Tier 3 (`pending`, `in_progress`, `completed`). |
| `publish_context` | `key, value, updated_by` | Updates blackboard key-values (`current_goal`, `active_stack`, `milestone`). |
| `get_recent_context` | `limit: int = 10` | Returns recent conversation turns across all clients (Tier 4 summary). |
| `get_turn` | `turn_id: int` | Fetches the full uncompressed raw prompt and completion payload for a specific turn. |
| `get_project_summary` | — | Returns diagnostic telemetry: database size, decision count, task counts, and turns. |
| `search_context` | `query: str, limit: int = 5, role: str, source: str` | Performs sub-3ms lexical search using SQLite FTS5 with Porter stemming and BM25 ranking across all historical turns. |

---

## 🚀 Quickstart

### Prerequisites
* **macOS / Linux / Windows**
* **Python 3.12+** (Tested up to Python 3.14.7)
* [`uv`](https://github.com/astral-sh/uv) (Extremely fast Python package runner)

If you don't have `uv` installed yet:
```bash
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

### Option A: The Fastest Way (Zero-Install / Run Instantly)

You don’t even need to clone the repository. Run this single command inside **any project directory**:

```bash
uvx --from git+https://github.com/adityadebnath009/Project-M.git project-m
```

`uvx` fetches Project-M into an isolated environment, renders the **copper Brutalist Chevron logo**, displays live project telemetry, and immediately drops you into the interactive shell:
```
project-m ❯ 
```
Type `/board` to view the living context card, or `/help` for all commands!

---

### Option B: The Complete Setup (Clone & Connect to Claude / Antigravity / Codex)

If you want Project-M permanently linked with your local AI desktop assistants:

```bash
# 1. Clone repository & sync dependencies
git clone https://github.com/adityadebnath009/Project-M.git
cd Project-M
uv sync

# 2. Run the 1-Click Auto-Installer
uv run project-m setup all
```

**What `project-m setup all` automatically does:**
1. Detects **Claude Desktop** (`claude_desktop_config.json`), **Google Antigravity** (`mcp_config.json`), and **Codex** (`config.toml`).
2. Creates timestamped safety backups (`.bak`) of your existing configs.
3. Injects the **Project-M FastMCP Server** over stdio.
4. Automatically installs the **Project-M Agent Skill** (`SKILL.md`) into your global agent directories (`~/.claude/skills`, `~/.gemini/antigravity/skills`, `~/.codex/skills`).

*Restart Claude Desktop or Antigravity and check the tools (🔨) menu—Project-M with all 8 tools will be active!*

You can also target a specific client:
```bash
uv run project-m setup -c claude
uv run project-m setup -c antigravity
uv run project-m setup -c codex
```

---

### Option C: Install Globally as a Native Terminal Command

If you want `project-m` permanently available in your shell like `git` or `docker`:

```bash
uv tool install git+https://github.com/adityadebnath009/Project-M.git
```

Now navigate to **any repository** on your computer and simply run:

```bash
project-m          # Launch interactive Claude-Code-style REPL
project-m board    # Inspect compiled Tier 1 State Card (< 450 tokens)
project-m status   # View context health & active warnings
project-m fetch    # Render Neofetch specs screen
```

---

#### Manual Claude Desktop Configuration
If you prefer manual configuration, add Project-M to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "project-m": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/Project-M",
        "project-m",
        "run"
      ]
    }
  }
}
```

---

## 🧪 Verification & Tests

Project-M includes an automated test suite verifying SQLite WAL concurrency, token ceiling constraints, JSONL stream parsers, FastMCP tool execution, and CLI command coverage:

```bash
uv run pytest -v
```

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/adityadebnath/Projects/Project-M(MCP)
configfile: pyproject.toml
plugins: anyio-4.16.0, asyncio-1.4.1.post1
collected 102 items

tests/test_adapters.py ...........                                       [ 10%]
tests/test_blackboard.py ..........                                      [ 20%]
tests/test_claude_code.py .........                                      [ 29%]
tests/test_cli.py ...........                                            [ 40%]
tests/test_fts5_search.py .....                                          [ 45%]
tests/test_multi_agent_e2e.py ......................                     [ 66%]
tests/test_server.py .........                                           [ 75%]
tests/test_storage.py .........................                          [100%]

============================= 102 passed in 3.02s ==============================
```

---

<div align="center">

### Built with care for multi-agent workflows.
**Project-M** is open-source under the [MIT License](LICENSE).

</div>
