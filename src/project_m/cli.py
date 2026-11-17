"""
Project-M Command Line Interface.

A sleek, Claude-Code-inspired terminal interface for managing local-first
project context, inspecting living state cards, and launching the FastMCP server.
"""

import getpass
from pathlib import Path
import sys
import time
import click
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
from project_m.server import server
from project_m.setup import run_setup
from project_m.storage.db import get_tasks, resolve_db_path

console = Console()
err_console = Console(stderr=True)


def create_branded_header(title: str, subtitle: str, status_badge: str | None = None) -> Panel:
    """Creates a Claude-Code-style rounded header banner."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="right")

    left = Text()
    left.append("  ◆ PROJECT-M ", style="bold #F59E0B")
    left.append("v0.1.1", style="dim")
    left.append(f"  •  {title}", style="bold white")
    if subtitle:
        left.append(f"\n    {subtitle}", style="dim")

    right = Text()
    if status_badge:
        right.append_text(Text.from_markup(f"{status_badge}  "))

    grid.add_row(left, right)
    return Panel(grid, box=box.ROUNDED, border_style="#F59E0B", padding=(0, 1))


MONOGRAM_LINES = [
    "[bold #F59E0B]   ██████╗         ██████╗   [/bold #F59E0B]",
    "[bold #F59E0B]   ████████╗     ████████║   [/bold #F59E0B]",
    "[bold #D97706]   ██╔══████╗   ████╔══██║   [/bold #D97706]",
    "[bold #D97706]   ██║  ╚████╗ ████╔╝  ██║   [/bold #D97706]",
    "[bold #EA580C]   ██║   ╚████████╔╝   ██║   [/bold #EA580C]",
    "[bold #C2410C]   ██║    ╚═══════╝    ██║   [/bold #C2410C]",
    "[bold #9A3412]   ██║                 ██║   [/bold #9A3412]",
    "[bold #7C2D12]   ╚═╝                 ╚═╝   [/bold #7C2D12]",
]


def render_fetch_screen() -> None:
    """Renders the signature Fastfetch/Neofetch screen with live project specs."""
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
        f"[bold #F59E0B]{username}@{repo_name}[/bold #F59E0B]",
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
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_row("\n".join(art), "\n".join(stats))

    console.print()
    console.print(grid)
    console.print()


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.1", prog_name="project-m")
def main(ctx: click.Context) -> None:
    """◆ Project-M: Deterministic local-first context engine for AI agents."""
    if ctx.invoked_subcommand is None:
        from project_m.shell import start_shell
        start_shell()


@main.command()
def shell() -> None:
    """Launches the interactive Claude-Code-style REPL shell."""
    from project_m.shell import start_shell
    start_shell()


@main.command()
def fetch() -> None:
    """Displays the signature Fastfetch-style project screen."""
    render_fetch_screen()


@main.command()
def run() -> None:
    """Starts the Project-M FastMCP server over stdio for AI clients."""
    # Print boot card to stderr so it never interferes with Claude's stdio JSON-RPC pipe
    db_path = resolve_db_path()
    try:
        rel_db = db_path.relative_to(Path.cwd())
    except ValueError:
        rel_db = db_path

    server_stats = [
        "[bold #F59E0B]PROJECT-M FAST-MCP SERVER[/bold #F59E0B]  [bold #10B981]● LISTENING[/bold #10B981]",
        "[dim]─────────────────────────────────────────────────[/dim]",
        "[bold white]Transport:[/bold white]   stdio (JSON-RPC 2.0)",
        f"[bold white]Storage:[/bold white]     SQLite WAL ({rel_db})",
        "[bold white]Clients:[/bold white]     Claude Desktop • Codex • Antigravity",
        "[bold white]Tools:[/bold white]       7 Registered (Tier 1–4 Context)",
        "[bold white]Invariant:[/bold white]   100% Local • Zero Paid APIs",
        "",
        "[dim]Ready for incoming agent requests...[/dim]",
        "",
        "[#F59E0B]●[/#F59E0B] [#F97316]●[/#F97316] [#EF4444]●[/#EF4444] [#EC4899]●[/#EC4899] [#8B5CF6]●[/#8B5CF6] [#3B82F6]●[/#3B82F6] [#10B981]●[/#10B981] [#FFFFFF]●[/#FFFFFF]",
    ]

    art = list(MONOGRAM_LINES)
    while len(art) < len(server_stats):
        art.append("")
    while len(server_stats) < len(art):
        server_stats.append("")

    grid = Table.grid(padding=(0, 4))
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_row("\n".join(art), "\n".join(server_stats))

    err_console.print()
    err_console.print(grid)
    err_console.print()
    server.run()


@main.command()
@click.option(
    "--target-tokens",
    default=450,
    help="Target token ceiling for the compiled briefing card.",
)
def board(target_tokens: int) -> None:
    """Renders the living Tier 1 State Card in the terminal."""
    card = compile_briefing_card(target_tokens=target_tokens)
    used_tokens = count_tokens(card)

    token_pill = f"[{used_tokens}/{target_tokens} tokens]"
    header = create_branded_header(
        title="Living State Card",
        subtitle=f"Deterministic context contract for active AI agents  •  {token_pill}",
        status_badge="● TIER 1 ACTIVE",
    )
    console.print(header)
    console.print(
        Panel(
            Markdown(card),
            box=box.ROUNDED,
            border_style="#38BDF8",
            padding=(1, 2),
        )
    )
    console.print(
        "[dim]  Tip: AI agents read this exact card automatically on every turn via [cyan]get_project_board()[/cyan].[/dim]\n"
    )


@main.command()
def status() -> None:
    """Displays a Claude-Code-inspired health and state diagnostics dashboard."""
    summary = get_project_summary()
    db_path = resolve_db_path()
    active_tasks = get_tasks(status="in_progress")

    # Status Badge
    if summary["is_healthy"]:
        status_badge = "[bold #10B981]● SYSTEM HEALTHY[/bold #10B981]"
    else:
        status_badge = "[bold #F59E0B]▲ ATTENTION REQUIRED[/bold #F59E0B]"

    # Top Banner
    header = create_branded_header(
        title="Context & Repository Health",
        subtitle=f"Database: {db_path}",
        status_badge=status_badge,
    )
    console.print(header)

    # Core Metrics Table
    table = Table(box=box.SIMPLE_HEAD, border_style="dim", expand=True)
    table.add_column("METRIC", style="bold #94A3B8", width=26)
    table.add_column("STATE / VALUE", style="white")
    table.add_column("NOTES", style="dim")

    goal = summary.get("goal") or "Define project goal via publish_context('goal', ...)"
    milestone = summary.get("current_milestone") or "No milestone set"

    table.add_row("Project Goal", goal, "Active scope")
    table.add_row("Current Milestone", milestone, "Current phase")
    table.add_row(
        "Architectural Decisions",
        f"[bold cyan]{summary['total_decisions']}[/bold cyan] accepted",
        "Tier 2 ADR ledger",
    )
    table.add_row(
        "Active Task Graph",
        f"[bold yellow]{summary['in_progress_tasks']}[/bold yellow] in progress, "
        f"[dim]{summary['pending_tasks']} pending[/dim], "
        f"[bold green]{summary['completed_tasks']}[/bold green] done",
        "Tier 3 Task Baton",
    )
    table.add_row(
        "Conversation Telemetry",
        f"[bold white]{summary['total_turns']}[/bold white] turns ingested",
        "Tier 4 Raw Turn Ledger",
    )

    console.print(table)

    # Active Task Baton Section (if any in progress)
    if active_tasks:
        console.print("[bold white]Active Task Baton:[/bold white]")
        for t in active_tasks:
            owner = f"@{t['assigned_to']}" if t.get("assigned_to") else "UNASSIGNED"
            notes = f" — [dim]{t['notes']}[/dim]" if t.get("notes") else ""
            console.print(f"  [yellow]❯[/yellow] [bold cyan]{t['id']}[/bold cyan]: {t['title']} [bold #F59E0B]({owner})[/bold #F59E0B]{notes}")
        console.print()

    # Warnings Section
    if summary["warnings"]:
        warn_panel = Text()
        warn_panel.append("⚠️  Attention Required:\n", style="bold #F59E0B")
        for w in summary["warnings"]:
            warn_panel.append(f"  • {w}\n", style="#F59E0B")
        console.print(Panel(warn_panel, box=box.ROUNDED, border_style="#F59E0B", padding=(0, 1)))

    console.print(
        "[dim]  Run [cyan]project-m board[/cyan] to view full state card  •  Run [cyan]project-m export[/cyan] to write to markdown[/dim]\n"
    )


@main.command()
@click.option(
    "--output",
    "-o",
    default="PROJECT_STATE.md",
    help="Target Markdown file path.",
)
def export(output: str) -> None:
    """Exports the compiled state card to a static Markdown file."""
    out_path = Path(output)
    result = export_project_state_md(output_path=out_path)
    console.print(
        f"\n  [bold #10B981]✓[/bold #10B981] Exported living state contract to [bold cyan]{result}[/bold cyan]\n"
    )


@main.command()
@click.option(
    "--client",
    "-c",
    type=click.Choice(["all", "claude", "antigravity", "codex"]),
    default="all",
    help="Target AI client to configure.",
)
def setup(client: str) -> None:
    """One-click setup: Configures Claude Desktop, Antigravity, and Codex."""
    clients_to_run = ["claude", "antigravity", "codex"] if client == "all" else [client]

    header = create_branded_header(
        title="One-Click Client Setup",
        subtitle="Configuring local AI clients to use Project-M via stdio",
        status_badge="● AUTO-INSTALLER",
    )
    console.print(header)

    results = run_setup(clients=clients_to_run)

    for client_name, (success, message) in results.items():
        if client_name.endswith("_skill"):
            base = client_name.replace("_skill", "")
            client_display = {
                "claude": "Claude Skill",
                "antigravity": "Antigravity Skill",
                "codex": "Codex Skill",
            }.get(base, f"{base.capitalize()} Skill")
        else:
            client_display = {
                "claude": "Claude Desktop",
                "antigravity": "Google Antigravity",
                "codex": "OpenAI Codex",
            }.get(client_name, client_name)

        if success:
            console.print(f"  [bold #10B981]✓[/bold #10B981] [bold white]{client_display}[/bold white]: {message}")
        else:
            console.print(f"  [bold #F59E0B]▲[/bold #F59E0B] [bold white]{client_display}[/bold white]: [yellow]{message}[/yellow]")

    console.print("\n[dim]  Restart your AI client (e.g., Claude Desktop) to connect to Project-M.[/dim]\n")


if __name__ == "__main__":
    main()
