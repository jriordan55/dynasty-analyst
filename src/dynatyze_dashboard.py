"""Dynatyze-style league dashboard data — storyline, faces, power order."""

from __future__ import annotations

from dataclasses import dataclass

from src.fantasycalc import FantasyCalcClient
from src.my_league import injury_report, build_roster_rows, section_counts
from src.platform import portfolio_managers

POS_COLORS = {"QB": "#6366f1", "RB": "#14b8a6", "WR": "#a855f7", "TE": "#ec4899"}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _fmt_value(value: int) -> str:
    if value >= 1000:
        text = f"{value / 1000:.1f}K"
        return text.replace(".0K", "K")
    return str(value)


def _headshot_url(player_id: str | None) -> str:
    if not player_id:
        return ""
    return f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"


@dataclass
class FaceCard:
    name: str
    last_name: str
    position: str
    value: int
    value_label: str
    rank: int
    headshot: str
    color: str
    player_id: str


@dataclass
class PositionPower:
    position: str
    label: str
    rank: int
    total_teams: int
    value: int
    pct: float
    color: str


@dataclass
class QuickCard:
    key: str
    title: str
    subtitle: str
    badge: str
    icon: str


@dataclass
class DynatyzeDashboard:
    storyline_kicker: str
    storyline: str
    team_name: str
    value_rank: int
    total_teams: int
    total_value: int
    total_value_label: str
    gauge_pct: float
    faces: list[FaceCard]
    positions: list[PositionPower]
    insight: str
    quick_cards: list[QuickCard]
    injury_count: int
    waiver_claim_rank: int


def _position_ranks(portfolios, my_manager: str) -> dict[str, int]:
    keys = {"QB": "qb_value", "RB": "rb_value", "WR": "wr_value", "TE": "te_value"}
    ranks: dict[str, int] = {}
    for pos, key in keys.items():
        ordered = sorted(portfolios, key=lambda t: getattr(t, key), reverse=True)
        ranks[pos] = next(
            (i + 1 for i, t in enumerate(ordered) if t.manager == my_manager),
            len(portfolios),
        )
    return ranks


def _position_values(portfolio) -> dict[str, int]:
    return {
        "QB": portfolio.qb_value,
        "RB": portfolio.rb_value,
        "WR": portfolio.wr_value,
        "TE": portfolio.te_value,
    }


def build_dynatyze_dashboard(
    snapshot: dict,
    my_team: dict,
    config: dict,
    fc: FantasyCalcClient,
    grades: list[dict],
    waiver_targets: list,
    intel,
    adp_map,
    dash,
) -> DynatyzeDashboard:
    portfolios = portfolio_managers(snapshot, fc)
    my_manager = my_team.get("owner_name") or config.get("username") or ""
    my_portfolio = next((p for p in portfolios if p.manager == my_manager), None)
    if not my_portfolio and portfolios:
        my_portfolio = next((p for p in portfolios if p.team_name == my_team.get("team_name")), portfolios[0])

    value_rank = next((i + 1 for i, p in enumerate(portfolios) if p.manager == my_manager), dash.rank)
    total_teams = len(portfolios) or dash.total_teams
    total_value = my_portfolio.total_value if my_portfolio else 0

    pos_ranks = _position_ranks(portfolios, my_manager) if my_portfolio else {}
    pos_values = _position_values(my_portfolio) if my_portfolio else {}

    best_pos = min(pos_ranks, key=pos_ranks.get) if pos_ranks else "RB"
    worst_pos = max(pos_ranks, key=pos_ranks.get) if pos_ranks else "QB"
    pos_labels = {"QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers", "TE": "tight ends"}

    status = (dash.status or "preseason").lower()
    if status in ("preseason", "pre_draft", "in_season"):
        phase = "Offseason." if status != "in_season" else "In season."
    else:
        phase = "Offseason."

    storyline = (
        f"{phase} You hold the {_ordinal(value_rank)} most valuable roster of {total_teams} — "
        f"your {pos_labels.get(best_pos, best_pos.lower())} room leads the league."
    )
    insight = (
        f"Your {pos_labels.get(best_pos, best_pos.lower())} room leads the league; "
        f"the {pos_labels.get(worst_pos, worst_pos.lower())} room sits "
        f"{_ordinal(pos_ranks.get(worst_pos, total_teams))} — the one to work."
    )

    roster = build_roster_rows(my_team, intel, adp_map, grades)
    faces: list[FaceCard] = []
    skill_players = [
        p for p in my_team.get("players") or []
        if p.get("position") in {"QB", "RB", "WR", "TE"} and p.get("name")
    ]
    skill_players.sort(
        key=lambda p: (fc.get(p["name"], p.get("id")).value if fc.get(p["name"], p.get("id")) else 0),
        reverse=True,
    )
    for i, p in enumerate(skill_players[:6], 1):
        name = p["name"]
        fc_v = fc.get(name, p.get("id"))
        val = fc_v.value if fc_v else 0
        pos = p.get("position") or "?"
        last = name.split()[-1] if name else name
        faces.append(
            FaceCard(
                name=name,
                last_name=last,
                position=pos,
                value=val,
                value_label=_fmt_value(val),
                rank=fc_v.overall_rank if fc_v else 0,
                headshot=_headshot_url(str(p.get("id") or "")),
                color=POS_COLORS.get(pos, "#64748b"),
                player_id=str(p.get("id") or ""),
            )
        )

    max_by_pos: dict[str, int] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        key = f"{pos.lower()}_value"
        max_by_pos[pos] = max((getattr(t, key, 0) for t in portfolios), default=1) or 1

    positions: list[PositionPower] = []
    for pos in ("QB", "RB", "WR", "TE"):
        val = pos_values.get(pos, 0)
        positions.append(
            PositionPower(
                position=pos,
                label=pos,
                rank=pos_ranks.get(pos, total_teams),
                total_teams=total_teams,
                value=val,
                pct=min(100.0, (val / max_by_pos.get(pos, 1)) * 100) if max_by_pos.get(pos) else 0,
                color=POS_COLORS.get(pos, "#64748b"),
            )
        )

    injuries = injury_report(roster)
    counts = section_counts(roster, snapshot, waiver_targets)

    quick_cards = [
        QuickCard("lineup", "Lineup", "Set your starters", f"{counts['injuries']} hurt" if counts["injuries"] else "Ready", "📋"),
        QuickCard("waivers", "Waivers", "Find this week's adds", f"claim #{min(value_rank, 12)}", "📡"),
        QuickCard("trades", "Trades", "Price every deal", "Open calc", "🔄"),
        QuickCard("league", "League", "Full league view", f"#{value_rank} of {total_teams}", "🏈"),
    ]

    return DynatyzeDashboard(
        storyline_kicker="THE STORYLINE",
        storyline=storyline,
        team_name=dash.team_name,
        value_rank=value_rank,
        total_teams=total_teams,
        total_value=total_value,
        total_value_label=_fmt_value(total_value),
        gauge_pct=(total_teams - value_rank + 1) / max(total_teams, 1) * 100,
        faces=faces,
        positions=positions,
        insight=insight,
        quick_cards=quick_cards,
        injury_count=len(injuries),
        waiver_claim_rank=value_rank,
    )
