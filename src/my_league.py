"""My League dashboard — roster, injuries, byes, depth, waivers."""

from __future__ import annotations

from dataclasses import dataclass

from src.adp import lookup_adp
from src.analysis import CORE_POSITIONS

# 2025 NFL regular-season bye weeks (team abbr -> week)
NFL_BYE_WEEKS: dict[str, int] = {
    "ARI": 8, "ATL": 5, "BAL": 7, "BUF": 7, "CAR": 11, "CHI": 5,
    "CIN": 10, "CLE": 9, "DAL": 10, "DEN": 12, "DET": 8, "GB": 5,
    "HOU": 6, "IND": 12, "JAX": 8, "KC": 10, "LAC": 12, "LAR": 8,
    "LV": 8, "MIA": 12, "MIN": 6, "NE": 11, "NO": 12, "NYG": 11,
    "NYJ": 9, "PHI": 9, "PIT": 5, "SEA": 8, "SF": 11, "TB": 9,
    "TEN": 10, "WAS": 12,
}


@dataclass
class LeagueDashboard:
    league_name: str
    season: str
    format_label: str
    num_teams: int
    username: str
    team_name: str
    record: str
    rank: int
    total_teams: int
    fpts: float
    status: str


def _format_label(config: dict) -> str:
    starters = config.get("starters") or {}
    if starters.get("SUPERFLEX", 0):
        return "Superflex"
    if starters.get("QB", 1) >= 2:
        return "2QB"
    return "1QB"


def _bye_week(nfl_team: str) -> int | None:
    if not nfl_team:
        return None
    return NFL_BYE_WEEKS.get(nfl_team.upper())


def _status_label(p: dict) -> str:
    if p.get("is_ir"):
        return "IR"
    if p.get("is_taxi"):
        return "Taxi"
    if p.get("is_starter"):
        return "Starter"
    return "Bench"


def build_dashboard(snapshot: dict, my_team: dict, config: dict) -> LeagueDashboard:
    league = snapshot.get("league") or {}
    teams = snapshot.get("teams") or []
    settings = (league.get("settings") or {})
    num_teams = settings.get("num_teams") or len(teams)

    ranked = sorted(
        teams,
        key=lambda t: float((t.get("fpts") or 0)),
        reverse=True,
    )
    rank = next((i + 1 for i, t in enumerate(ranked) if t.get("is_mine")), len(teams))

    wins = my_team.get("wins", 0)
    losses = my_team.get("losses", 0)
    draft = snapshot.get("draft") or {}
    status = draft.get("status") or league.get("status") or "preseason"
    if status in ("pre_draft", "drafting"):
        status = "preseason"

    return LeagueDashboard(
        league_name=league.get("name") or config.get("league_name") or "My League",
        season=str(league.get("season") or ""),
        format_label=_format_label(config),
        num_teams=int(num_teams),
        username=config.get("username") or "",
        team_name=my_team.get("team_name") or my_team.get("owner_name") or "My Team",
        record=f"{wins}-{losses}",
        rank=rank,
        total_teams=len(teams),
        fpts=float(my_team.get("fpts") or 0),
        status=str(status),
    )


def build_roster_rows(my_team: dict, intel, adp_map, grades: list[dict]) -> list[dict]:
    grade_map = {g["name"]: g["grade"] for g in grades}
    rows = []
    for p in my_team.get("players") or []:
        if p.get("position") not in CORE_POSITIONS and p.get("position") not in ("K", "DEF"):
            continue
        name = p.get("name") or ""
        pos = p.get("position") or ""
        ctx = intel.get(name, pos) if intel else None
        adp_entry = lookup_adp(name, adp_map)
        rows.append({
            "name": name,
            "position": pos,
            "nfl_team": p.get("team") or "",
            "age": p.get("age"),
            "adp": adp_entry.adp if adp_entry else None,
            "grade": grade_map.get(name, "—"),
            "starter": p.get("is_starter", False),
            "status": _status_label(p),
            "injury": p.get("injury_status") or "",
            "bye_week": _bye_week(p.get("team") or ""),
            "depth_order": p.get("depth_chart_order"),
            "depth_role": p.get("depth_chart_position") or pos,
            "upside": round(ctx.upside_score, 0) if ctx else None,
            "news": ctx.news_headline[:60] if ctx and ctx.news_headline else "",
        })
    rows.sort(key=lambda r: (not r["starter"], r["adp"] or 999))
    return rows


def injury_report(roster_rows: list[dict]) -> list[dict]:
    flagged = [
        r for r in roster_rows
        if r.get("injury") and r["injury"].lower() not in ("healthy", "active", "")
    ]
    flagged.sort(key=lambda r: r["name"])
    return flagged


def bye_week_board(roster_rows: list[dict]) -> list[dict]:
    rows = [r for r in roster_rows if r.get("bye_week")]
    rows.sort(key=lambda r: (r["bye_week"], r["name"]))
    return rows


def depth_chart_rows(roster_rows: list[dict]) -> list[dict]:
    rows = [r for r in roster_rows if r["position"] in CORE_POSITIONS]
    rows.sort(key=lambda r: (
        {"QB": 0, "RB": 1, "WR": 2, "TE": 3}.get(r["position"], 9),
        r.get("depth_order") or 99,
        r["adp"] or 999,
    ))
    return rows


def bench_ledger(roster_rows: list[dict]) -> list[dict]:
    bench = [r for r in roster_rows if r["status"] == "Bench" and r["position"] in CORE_POSITIONS]
    bench.sort(key=lambda r: r["adp"] or 999)
    return bench


def waiver_wire_snapshot(snapshot: dict) -> dict:
    trending = snapshot.get("trending") or {}
    adds = trending.get("adds") or []
    drops = trending.get("drops") or []
    players = snapshot.get("_all_players") or {}
    if not players:
        from pathlib import Path
        import json
        cache = Path(__file__).resolve().parents[1] / "data" / "cache" / "sleeper_players.json"
        if cache.exists():
            players = json.loads(cache.read_text(encoding="utf-8"))

    def enrich(items: list) -> list[dict]:
        out = []
        for item in items[:25]:
            pid = str(item.get("player_id", ""))
            sp = players.get(pid, {})
            out.append({
                "player": sp.get("full_name") or pid,
                "position": sp.get("position", ""),
                "team": sp.get("team", ""),
                "adds": item.get("count", 0),
            })
        return out

    return {
        "adds": enrich(adds),
        "drops": enrich(drops),
        "add_count_30d": len(adds),
    }


def section_counts(roster_rows: list[dict], snapshot: dict, waiver_targets: list) -> dict:
    wire = waiver_wire_snapshot(snapshot)
    return {
        "roster": len(roster_rows),
        "injuries": len(injury_report(roster_rows)),
        "depth": len([r for r in roster_rows if r["position"] in CORE_POSITIONS]),
        "bench": len(bench_ledger(roster_rows)),
        "waiver_adds": wire["add_count_30d"],
        "replacements": len(waiver_targets),
    }
