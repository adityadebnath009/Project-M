"""
Interactive REPL Shell for Project-M.

Provides a Claude-Code-inspired interactive terminal session with tab-completion,
slash commands, live project state inspection, and task/decision management.
"""

import getpass
from pathlib import Path
import readline
import shlex
import sys
import time
from typing import Any

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_m.blackboard import (
    compile_briefing_card,
    count_tokens,
    export_project_state_md,
    get_project_summary,
)
from project_m.cli import MONOGRAM_LINES
from project_m.setup import run_setup
from project_m.storage.db import (
    add_decision,
    add_task,
    get_board,
    get_decisions,
    get_tasks,
    resolve_db_path,
    set_board_value,
)

console = Console()

SLASH_COMMANDS = [
    "/board",
    "/status",
    "/tasks",
    "/task",
    "/decisions",
    "/decide",
    "/fetch",
    "/export",
    "/setup",
    "/clear",
    "/help",
    "/exit",
    "/quit",
]


def _setup_completer() -> None:
    """Configures readline tab completion for slash commands."""
    def completer(text: str, state: int) -> str | None:
        options = [cmd for cmd in SLASH_COMMANDS if cmd.startswith(text)]
        # Also support commands without leading slash
        if not text.startswith("/"):
            options.extend([cmd[1:] for cmd in SLASH_COMMANDS if cmd[1:].startswith(text)])
        if state < len(options):
            return options[state]
        return None

    readline.set_completer(completer)
    # Enable tab completion on macOS and Linux
    if "libedit" in readline.__doc__:  # type: ignore[operator]
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


def _print_shell_banner() -> None:
    """Prints the Claude-Code-inspired welcome banner with logo on top left."""
    start_time = time.perf_counter()
    summary = get_project_summary()
    card = compile_briefing_card(target_tokens=450)
    tokens = count_tokens(card)
    compile_ms = (time.perf_counter() - start_time) * 1000

    username = getpass.getuser()
    repo_name = Path.cwd().name
    db_path = resolve_db_path()
    try:
        rel_db = db_path.relative_to(Path.cwd())
    except ValueError:
        rel_db = db_path

    # Active task info
    active_tasks = get_tasks(status="in_progress")
    if active_tasks:
        t = active_tasks[0]
        owner = f"@{t['assigned_to']}" if t.get("assigned_to") else "UNASSIGNED"
        task_str = f"{t['id']} (Owner: {owner})"
    else:
        task_str = f"{summary['in_progress_tasks']} active, {summary['pending_tasks']} pending"

    stats = [
        f"[bold #F59E0B]{username}@{repo_name}[/bold #F59E0B]  [bold #10B981]● REPL ACTIVE[/bold #10B981]",
        "[dim]─────────────────────────────────────────────────[/dim]",
        "[bold white]Engine:[/bold white]     4-Tier Lossless State Compiler",
        f"[bold white]Storage:[/bold white]    SQLite WAL ({rel_db})",
        "[bold white]Clients:[/bold white]    Claude Desktop • Codex • Antigravity",
        f"[bold white]ADRs:[/bold white]       [cyan]{summary['total_decisions']}[/cyan] Accepted (Tier 2 Ledger)",
        f"[bold white]Tasks:[/bold white]      {task_str}",
        f"[bold white]Telemetry:[/bold white]  [white]{summary['total_turns']}[/white] raw turns recorded (Tier 4)",
        "[bold white]Invariant:[/bold white]  100% Local • Zero Paid APIs",
        f"[bold white]Compile:[/bold white]    {compile_ms:.1f}ms latency ({tokens}/450 tokens)",
        "",
        "[#F59E0B]●[/#F59E0B] [#F97316]●[/#F97316] [#EF4444]●[/#EF4444] [#EC4899]●[/#EC4899] [#8B5CF6]●[/#8B5CF6] [#3B82F6]●[/#3B82F6] [#10B981]●[/#10B981] [#FFFFFF]●[/#FFFFFF]",
    ]

    art = list(MONOGRAM_LINES)
    while len(art) < len(stats):
        art.append("")
    while len(stats) < len(art):
        stats.append("")

    grid = Table.grid(padding=(0, 4))
    grid.add_column(justify="left", no_wrap=True)
    grid.add_column(justify="left")
    grid.add_row("\n".join(art), "\n".join(stats))

    console.print()
    console.print(grid)
    console.print("[dim]  Type [cyan]/help[/cyan] for commands  •  Press [cyan]Tab[/cyan] to autocomplete  •  [cyan]/exit[/cyan] to quit[/dim]\n")


def _handle_help() -> None:
    """Displays the command cheat sheet."""
    table = Table(title="Project-M Shell Commands", box=box.ROUNDED, border_style="#F59E0B")
    table.add_column("Command", style="bold cyan", width=22)
    table.add_column("Description", style="white")
    table.add_column("Example Usage", style="dim")

    table.add_row("/board", "View living Tier 1 state card", "/board")
    table.add_row("/status", "View repository health & alerts", "/status")
    table.add_row("/tasks", "List task graph & owners", "/tasks")
    table.add_row("/task", "Add or update a task baton", '/task task-05 in_progress @codex "Notes"')
    table.add_row("/decisions", "List architectural decision records", "/decisions")
    table.add_row("/decide", "Record a new binding ADR", '/decide ADR-003 "Title" "Rationale"')
    table.add_row("/fetch", "Display Neofetch specs screen", "/fetch")
    table.add_row("/export", "Export state card to Markdown", "/export [filename]")
    table.add_row("/setup", "One-click configure AI clients", "/setup [all|claude|codex]")
    table.add_row("/clear", "Clear terminal screen", "/clear")
    table.add_row("/exit", "Exit the interactive shell", "/exit")

    console.print(table)


def _handle_tasks_list() -> None:
    """Displays tasks organized by status."""
    in_progress = get_tasks(status="in_progress")
    pending = get_tasks(status="pending")
    completed = get_tasks(status="completed")

    table = Table(title="Task Graph & Handoff Batons", box=box.SIMPLE_HEAD, border_style="dim", expand=True)
    table.add_column("Status", width=14)
    table.add_column("ID", style="bold cyan", width=12)
    table.add_column("Title", style="white")
    table.add_column("Owner", style="bold #F59E0B", width=16)
    table.add_column("Notes", style="dim")

    for t in in_progress:
        owner = f"@{t['assigned_to']}" if t.get("assigned_to") else "UNASSIGNED"
        table.add_row("[bold yellow]IN PROGRESS[/bold yellow]", t["id"], t["title"], owner, t.get("notes", ""))

    for t in pending:
        owner = f"@{t['assigned_to']}" if t.get("assigned_to") else "[dim]none[/dim]"
        table.add_row("[dim]PENDING[/dim]", t["id"], t["title"], owner, t.get("notes", ""))

    for t in completed:
        owner = f"@{t['assigned_to']}" if t.get("assigned_to") else "[dim]none[/dim]"
        table.add_row("[bold green]COMPLETED[/bold green]", t["id"], t["title"], owner, t.get("notes", ""))

    console.print(table)


def _handle_task_update(args: list[str]) -> None:
    """
    Parses and updates a task:
    /task <id> <status> [owner] [notes]
    """
    if len(args) < 2:
        console.print("[bold yellow]Usage:[/bold yellow] /task <id> <pending|in_progress|completed> [owner] [notes]")
        console.print('Example: /task task-05 in_progress @claude "Writing test suite"\n')
        return

    task_id = args[0]
    status = args[1].lower()
    owner = args[2].lstrip("@") if len(args) > 2 else None
    notes = " ".join(args[3:]) if len(args) > 3 else ""

    existing = [t for t in get_tasks() if t["id"] == task_id]
    title = existing[0]["title"] if existing else task_id
    if not owner and existing:
        owner = existing[0].get("assigned_to")

    add_task(
        task_id=task_id,
        title=title,
        status=status,
        assigned_to=owner,
        notes=notes,
    )
    owner_str = f" (Owner: @{owner})" if owner else ""
    console.print(f"  [bold #10B981]✓[/bold #10B981] Updated task [bold cyan]{task_id}[/bold cyan] → [yellow]{status}[/yellow]{owner_str}")


def _handle_decisions_list() -> None:
    """Lists architectural decisions."""
    decisions = get_decisions(limit=50)
    if not decisions:
        console.print("[dim]No architectural decisions recorded yet. Use /decide to add one.[/dim]")
        return

    table = Table(title="Architectural Decision Records (ADRs)", box=box.SIMPLE_HEAD, border_style="dim", expand=True)
    table.add_column("ID", style="bold cyan", width=12)
    table.add_column("Title", style="bold white", width=26)
    table.add_column("Status", width=12)
    table.add_column("Decided By", style="#F59E0B", width=14)
    table.add_column("Rationale", style="dim")

    for d in decisions:
        status_styled = f"[green]{d['status']}[/green]" if d["status"] == "accepted" else f"[dim]{d['status']}[/dim]"
        table.add_row(d["id"], d["title"], status_styled, f"@{d.get('decided_by', 'agent')}", d.get("rationale", ""))

    console.print(table)


def _handle_decide(args: list[str]) -> None:
    """
    Records an architectural decision:
    /decide <id> "<title>" "<rationale>" [status]
    """
    if len(args) < 3:
        console.print('[bold yellow]Usage:[/bold yellow] /decide <decision_id> "<title>" "<rationale>" [status]')
        console.print('Example: /decide ADR-003 "Pydantic v2" "Strict data validation across boundaries" accepted\n')
        return

    d_id = args[0]
    title = args[1]
    rationale = args[2]
    status = args[3] if len(args) > 3 else "accepted"

    add_decision(
        decision_id=d_id,
        title=title,
        rationale=rationale,
        decided_by="human",
        status=status,
    )
    console.print(f"  [bold #10B981]✓[/bold #10B981] Recorded decision [bold cyan][{d_id}][/bold cyan]: '{title}' ({status})")


def start_shell() -> None:
    """Launches the interactive REPL shell loop."""
    _setup_completer()
    _print_shell_banner()

    # Import fetch helper from cli module dynamically
    from project_m.cli import render_fetch_screen

    while True:
        try:
            prompt_str = console.input("[bold #F59E0B]project-m[/bold #F59E0B] [dim]❯[/dim] ").strip()
            if not prompt_str:
                continue

            try:
                tokens = shlex.split(prompt_str)
            except ValueError:
                tokens = prompt_str.split()

            if not tokens:
                continue

            cmd = tokens[0].lower()
            args = tokens[1:]

            # Normalize command without leading slash
            base_cmd = cmd[1:] if cmd.startswith("/") else cmd

            if base_cmd in ("exit", "quit", "q"):
                console.print("\n[dim]Goodbye! Exiting Project-M shell.[/dim]\n")
                break

            elif base_cmd in ("help", "?"):
                _handle_help()

            elif base_cmd == "board":
                tokens_target = int(args[0]) if args and args[0].isdigit() else 450
                card = compile_briefing_card(target_tokens=tokens_target)
                used = count_tokens(card)
                console.print(Panel(Markdown(card), title=f"[bold #F59E0B]Living State Card[/bold #F59E0B] • [cyan]{used}/{tokens_target} tokens[/cyan]", box=box.ROUNDED, border_style="#38BDF8"))

            elif base_cmd == "status":
                from project_m.cli import status as status_cmd
                # Execute status logic cleanly
                summary = get_project_summary()
                status_str = "[bold #10B981]● SYSTEM HEALTHY[/bold #10B981]" if summary["is_healthy"] else "[bold #F59E0B]▲ ATTENTION REQUIRED[/bold #F59E0B]"
                console.print(f"  Status: {status_str}  •  Goal: {summary.get('goal') or 'Not set'}")
                if summary["warnings"]:
                    for w in summary["warnings"]:
                        console.print(f"  [yellow]•[/yellow] {w}")

            elif base_cmd == "tasks":
                _handle_tasks_list()

            elif base_cmd == "task":
                _handle_task_update(args)

            elif base_cmd == "decisions":
                _handle_decisions_list()

            elif base_cmd == "decide":
                _handle_decide(args)

            elif base_cmd == "fetch":
                render_fetch_screen()

            elif base_cmd == "export":
                out = args[0] if args else "PROJECT_STATE.md"
                p = export_project_state_md(output_path=Path(out))
                console.print(f"  [bold #10B981]✓[/bold #10B981] Exported state card to [cyan]{p}[/cyan]")

            elif base_cmd == "setup":
                client = args[0] if args else "all"
                results = run_setup(clients=["claude", "antigravity", "codex"] if client == "all" else [client])
                for c, (ok, msg) in results.items():
                    mark = "[bold #10B981]✓[/bold #10B981]" if ok else "[bold #F59E0B]▲[/bold #F59E0B]"
                    console.print(f"  {mark} {c}: {msg}")

            elif base_cmd in ("clear", "cls"):
                console.clear()
                _print_shell_banner()

            else:
                console.print(f"[dim]Unknown command '{cmd}'. Type [cyan]/help[/cyan] for available commands.[/dim]")

            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]Use /exit or Ctrl+D to quit.[/dim]\n")
        except EOFError:
            console.print("\n[dim]Goodbye! Exiting Project-M shell.[/dim]\n")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}\n")
