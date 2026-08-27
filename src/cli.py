#!/usr/bin/env python3
"""Dynasty Fantasy Football Analyst CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.analyst import DynastyAnalyst, load_config, refresh_adp

app = typer.Typer(
    name="dynasty",
    help="AI-powered dynasty fantasy football analyst with live league + news data.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def setup():
    """Interactive setup for league connection."""
    config_path = Path(__file__).resolve().parents[1] / "config" / "league.json"
    example = Path(__file__).resolve().parents[1] / "config" / "league.example.json"

    console.print(Panel(
        "[bold]Dynasty Analyst Setup[/bold]\n\n"
        "1. Find your Sleeper league ID in the URL: sleeper.com/leagues/[ID]\n"
        "2. Enter your Sleeper username (display name)\n"
        "3. Optionally set ANTHROPIC_API_KEY in .env for AI chat",
        title="Welcome",
    ))

    league_id = typer.prompt("Sleeper League ID")
    username = typer.prompt("Your Sleeper username")

    config = json.loads(example.read_text(encoding="utf-8"))
    config["league_id"] = league_id
    config["username"] = username
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    console.print(f"[green]Saved config to {config_path}[/green]")
    console.print("Run [bold]python -m src.cli sync[/bold] to pull your league.")


@app.command()
def refresh_adp_cmd():
    """Refresh ADP data from 4for4 markdown source."""
    count = refresh_adp()
    console.print(f"[green]Loaded {count} players into data/adp.json[/green]")


@app.command()
def sync():
    """Sync league rosters from Sleeper."""
    analyst = DynastyAnalyst()
    with console.status("Syncing league from Sleeper..."):
        snapshot = analyst.sync()
    teams = len(snapshot["teams"])
    mine = next((t for t in snapshot["teams"] if t.get("is_mine")), None)
    if mine:
        console.print(
            f"[green]Synced {teams} teams. Your team: {mine['team_name']} "
            f"({len(mine['players'])} players)[/green]"
        )
    else:
        console.print(f"[green]Synced {teams} teams in {analyst.config.get('league_name', 'league')}.[/green]")
        console.print("[yellow]Run: python -m src.cli set-team YOUR_USERNAME[/yellow]")


@app.command()
def teams():
    """List all teams in the league (use to find your username)."""
    analyst = DynastyAnalyst()
    with console.status("Syncing league..."):
        snapshot = analyst.sync()
    table = Table(title=f"Teams in {analyst.config.get('league_name', 'League')}")
    table.add_column("#", justify="right")
    table.add_column("Manager", style="cyan")
    table.add_column("Team Name")
    table.add_column("Players", justify="right")

    for i, team in enumerate(snapshot["teams"], 1):
        table.add_row(
            str(i),
            team["owner_name"],
            team["team_name"],
            str(len(team["players"])),
        )
    console.print(table)
    console.print("\nThen run: [bold]python -m src.cli set-team YOUR_USERNAME[/bold]")


@app.command("set-team")
def set_team(username: str = typer.Argument(..., help="Your Sleeper display name")):
    """Set your team by Sleeper username."""
    config_path = Path(__file__).resolve().parents[1] / "config" / "league.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["username"] = username
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    env_path = Path(__file__).resolve().parents[1] / ".env"
    env_path.write_text(
        f"SLEEPER_LEAGUE_ID={config['league_id']}\nSLEEPER_USERNAME={username}\n",
        encoding="utf-8",
    )
    analyst = DynastyAnalyst(config)
    with console.status("Syncing your team..."):
        analyst.sync()
    _, my_team = analyst._ensure_loaded()
    console.print(f"[green]Set to {username} — team: {my_team['team_name']}[/green]")


@app.command()
def overview():
    """League-wide needs analysis — who is desperate at what."""
    analyst = DynastyAnalyst()
    data = analyst.league_overview()

    table = Table(title="League Manager Profiles")
    table.add_column("Manager", style="cyan")
    table.add_column("Team")
    table.add_column("QB", justify="center")
    table.add_column("RB", justify="center")
    table.add_column("WR", justify="center")
    table.add_column("TE", justify="center")
    table.add_column("Desperate For", style="red")
    table.add_column("Overloaded", style="yellow")

    for team in data["all_teams"]:
        c = team["counts"]
        table.add_row(
            team["manager"],
            team["team"],
            str(c.get("QB", 0)),
            str(c.get("RB", 0)),
            str(c.get("WR", 0)),
            str(c.get("TE", 0)),
            ", ".join(team["desperate_for"]) or "—",
            ", ".join(team["overloaded_at"]) or "—",
        )

    console.print(table)
    my = data.get("my_needs")
    if my and analyst.config.get("username"):
        console.print(Panel(
            f"Desperate for: {', '.join(my.desperate_for) or 'None'}\n"
            f"Surplus: {my.surplus or 'None'}",
            title=f"Your Team: {data['my_team']}",
        ))
    elif not analyst.config.get("username"):
        console.print("[yellow]Run: python -m src.cli set-team YOUR_USERNAME[/yellow]")


@app.command()
def grades():
    """Grade your roster vs ADP + live news."""
    analyst = DynastyAnalyst()
    roster_grades = analyst.grade_my_roster()

    table = Table(title="Roster Grades")
    table.add_column("Player", style="bold")
    table.add_column("Pos")
    table.add_column("ADP", justify="right")
    table.add_column("Age", justify="right")
    table.add_column("Grade", style="green")
    table.add_column("Notes")

    for g in roster_grades:
        grade_style = "green" if g["grade"].startswith("A") else "yellow" if g["grade"].startswith("B") else "red"
        table.add_row(
            g["name"],
            g["position"],
            str(g["adp"] or "—"),
            str(g["age"] or "—"),
            f"[{grade_style}]{g['grade']}[/{grade_style}]",
            "; ".join(g["notes"][:2]),
        )

    console.print(table)


@app.command()
def sell():
    """Players to sell before value drops."""
    analyst = DynastyAnalyst()
    candidates = analyst.sell_candidates()

    if not candidates:
        console.print("[green]No urgent sell candidates identified.[/green]")
        return

    table = Table(title="Sell Candidates")
    table.add_column("Urgency")
    table.add_column("Player", style="bold")
    table.add_column("Pos")
    table.add_column("ADP", justify="right")
    table.add_column("Reason")

    urgency_colors = {"high": "red", "medium": "yellow", "low": "white"}
    for c in candidates:
        color = urgency_colors.get(c.urgency, "white")
        table.add_row(
            f"[{color}]{c.urgency.upper()}[/{color}]",
            c.player,
            c.position,
            str(c.adp or "—"),
            c.reason,
        )

    console.print(table)


@app.command()
def trades():
    """Manager-specific trade targets based on league needs."""
    analyst = DynastyAnalyst()
    matches = analyst.trade_targets()

    if not matches:
        console.print("[yellow]No strong trade matches found. Try syncing first.[/yellow]")
        return

    for i, t in enumerate(matches[:10], 1):
        console.print(Panel(
            f"[bold]Send:[/bold] {', '.join(t.you_give)}\n"
            f"[bold]Get:[/bold] {', '.join(t.you_get)}\n\n"
            f"{t.rationale}",
            title=f"#{i} — {t.target_manager} ({t.target_team}) | Leverage: {t.leverage_score:.1f}",
            border_style="cyan",
        ))


@app.command()
def waivers():
    """Waiver wire pickups tailored to your roster holes."""
    analyst = DynastyAnalyst()
    targets = analyst.waiver_targets()

    table = Table(title="Waiver Targets For Your Situation")
    table.add_column("#", justify="right")
    table.add_column("Player", style="bold")
    table.add_column("Pos")
    table.add_column("ADP", justify="right")
    table.add_column("Why")

    for i, w in enumerate(targets[:15], 1):
        table.add_row(str(i), w.player, w.position, str(w.adp or "—"), w.reason)

    console.print(table)


@app.command()
def context():
    """Print full analysis context (for Claude Code / Cursor chat)."""
    analyst = DynastyAnalyst()
    console.print(analyst.build_context())


@app.command()
def ask(question: str = typer.Argument(..., help="Your question for the AI analyst")):
    """Ask the AI analyst a natural language question."""
    analyst = DynastyAnalyst()
    with console.status("Analyzing with Claude..."):
        answer = analyst.ask(question)
    console.print(Panel(answer, title="Dynasty Analyst", border_style="green"))


@app.command()
def news():
    """Live fantasy news from @RotoWireNFL."""
    from src.news import get_news_client

    client = get_news_client()
    try:
        by_source = client.get_news_by_source()
    finally:
        client.close()

    items = by_source.get("rotowire", [])
    console.print(Panel(f"{len(items)} headlines", title="@RotoWireNFL", border_style="cyan"))
    for n in items[:12]:
        headline = n["headline"].encode("ascii", "replace").decode("ascii")
        console.print(f"  - {headline}")
        if n.get("link"):
            console.print(f"    [dim]{n['link']}[/dim]")


@app.command()
def report():
    """Full dynasty report: overview, grades, sells, trades, waivers."""
    analyst = DynastyAnalyst()
    console.print(Panel(analyst.build_context(), title="Full Dynasty Report", border_style="blue"))


def main():
    app()


if __name__ == "__main__":
    main()
