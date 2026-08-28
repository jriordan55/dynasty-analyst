"""Data builders for Dynatyze-style league hub pages."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis import CORE_POSITIONS
from src.fantasycalc import FantasyCalcClient
from src.my_league import bench_ledger, build_roster_rows, bye_week_board, injury_report

POS_COLORS = {"QB": "#a855f7", "RB": "#14b8a6", "WR": "#06b6d4", "TE": "#f43f5e"}


def fmt_value(value: int) -> str:
    if value >= 1000:
        t = f"{value / 1000:.1f}K"
        return t.replace(".0K", "K")
    return str(value)


def headshot_url(player_id: str | None) -> str:
    if not player_id:
        return ""
    return f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"


def weekly_projection(fc_value: int, grade: str = "C") -> float:
    """Proxy weekly pts from dynasty value + grade (pre-season fallback)."""
    base = max(4.0, fc_value / 320.0)
    bonus = {"A": 3.5, "B": 1.5, "C": 0, "D": -1.5, "F": -3}.get(grade, 0)
    return round(base + bonus, 1)


def start_tier(projection: float, rank_in_slot: int) -> tuple[str, str]:
    if rank_in_slot == 1 and projection >= 18:
        return "Must Start", "green"
    if projection >= 14:
        return "Strong Start", "green"
    if projection >= 10:
        return "Lean Start", "amber"
    return "Sit", "muted"


def injury_badge(status: str) -> tuple[str, str]:
    s = (status or "").lower()
    if s in ("ir",):
        return "IR", "ir"
    if s in ("pup",):
        return "PUP", "pup"
    if s in ("out",):
        return "Out", "out"
    if s in ("doubtful",):
        return "Doubtful", "doubtful"
    if s in ("questionable", "q"):
        return "Questionable", "questionable"
    if s in ("probable",):
        return "Probable", "probable"
    return status or "Unknown", "muted"


def signal_label(trend: int) -> str:
    if trend >= 50:
        return "BUY"
    if trend <= -50:
        return "SELL"
    return "HOLD"


def age_tier(age: int | None) -> str:
    if not age:
        return "—"
    if age <= 22:
        return f"{age} YOUTH"
    if age <= 26:
        return f"{age} PRIME"
    if age <= 30:
        return f"{age} VET"
    return f"{age} AGING"


@dataclass
class PlayerCard:
    name: str
    position: str
    team: str
    value: int
    value_label: str
    age: float | None
    player_id: str
    headshot: str
    injury: str = ""
    starter: bool = False
    projection: float = 0.0
    tier: str = ""
    tier_color: str = "muted"
    fc_rank: int | None = None
    signal: str = "HOLD"
    depth_note: str = ""


@dataclass
class StartSitPage:
    week_label: str
    optimal_projection: float
    current_projection: float
    bench_left: float
    recommended_moves: list[dict]
    lineup: list[PlayerCard]
    empty_slots: int
    alerts: list[str]


@dataclass
class DepthTeamRow:
    team_name: str
    manager: str
    slots: dict[str, PlayerCard | None]


@dataclass
class DepthChartPage:
    teams: int
    rows: list[DepthTeamRow]
    columns: list[str]


@dataclass
class InjuryPage:
    flagged: list[PlayerCard]
    bench_injured: list[PlayerCard]
    callout: str


@dataclass
class RosterRoom:
    position: str
    label: str
    color: str
    total_value: int
    pct: int
    players: list[PlayerCard]


@dataclass
class MyTeamPage:
    rooms: list[RosterRoom]
    total_value: int
    shown: int
    total_players: int


def _player_card(p: dict, fc: FantasyCalcClient, intel, grades_map: dict) -> PlayerCard:
    name = p.get("name") or ""
    fc_v = fc.get(name, p.get("id"))
    val = fc_v.value if fc_v else 0
    grade = grades_map.get(name, {}).get("grade", "C")
    ctx = intel.get(name, p.get("position", "")) if intel else None
    trend = fc_v.trend_30d if fc_v else 0
    return PlayerCard(
        name=name,
        position=p.get("position") or "?",
        team=p.get("nfl_team") or p.get("team") or "",
        value=val,
        value_label=fmt_value(val),
        age=float(p["age"]) if p.get("age") else None,
        player_id=str(p.get("id") or ""),
        headshot=headshot_url(str(p.get("id") or "")),
        injury=p.get("injury") or "",
        starter=bool(p.get("starter")),
        projection=weekly_projection(val, grade),
        fc_rank=fc_v.overall_rank if fc_v else None,
        signal=signal_label(trend),
        depth_note=p.get("depth_role") or "",
    )


def _roster_with_ids(my_team: dict, roster_rows: list[dict]) -> list[dict]:
    by_name = {p.get("name"): p for p in my_team.get("players") or []}
    out = []
    for r in roster_rows:
        src = by_name.get(r["name"], {})
        out.append({**r, "id": src.get("id"), "age": r.get("age") or src.get("age")})
    return out


def build_start_sit_page(
    my_team: dict,
    roster_rows: list[dict],
    fc: FantasyCalcClient,
    intel,
    grades: list[dict],
    config: dict,
) -> StartSitPage:
    grades_map = {g["name"]: g for g in grades}
    players = [_player_card(p, fc, intel, grades_map) for p in _roster_with_ids(my_team, roster_rows)]
    skill = [p for p in players if p.position in {"QB", "RB", "WR", "TE"}]

    starters = [p for p in skill if p.starter]
    bench = [p for p in skill if not p.starter]
    if not starters:
        starters = sorted(skill, key=lambda x: x.projection, reverse=True)[:9]
        bench = [p for p in skill if p not in starters]

    for i, p in enumerate(sorted(starters, key=lambda x: x.projection, reverse=True)):
        p.tier, p.tier_color = start_tier(p.projection, i + 1)

    current = round(sum(p.projection for p in starters), 1)
    optimal_line = sorted(skill, key=lambda x: x.projection, reverse=True)[:len(starters) or 9]
    optimal = round(sum(p.projection for p in optimal_line), 1)

    moves: list[dict] = []
    starter_names = {p.name for p in starters}
    for bench_p in sorted(bench, key=lambda x: x.projection, reverse=True):
        same_pos = [s for s in starters if s.position == bench_p.position]
        if not same_pos:
            continue
        worst = min(same_pos, key=lambda x: x.projection)
        gain = round(bench_p.projection - worst.projection, 1)
        if gain >= 0.8:
            moves.append({
                "out_name": worst.name,
                "out_last": worst.name.split()[-1],
                "in_name": bench_p.name,
                "in_last": bench_p.name.split()[-1],
                "position": bench_p.position,
                "gain": gain,
                "reason": "projection gap covers the tougher matchup" if gain < 1.5 else "softer matchup",
            })
            if len(moves) >= 3:
                break

    empty_slots = max(0, 9 - len(starters))
    alerts = []
    if empty_slots:
        alerts.append(
            f"{empty_slots} empty starting slot{'s' if empty_slots > 1 else ''} — "
            "check the waiver wire or bye-week/injury situation."
        )

    return StartSitPage(
        week_label="Week 1",
        optimal_projection=optimal,
        current_projection=current,
        bench_left=round(max(0, optimal - current), 1),
        recommended_moves=moves,
        lineup=sorted(starters, key=lambda x: -x.projection),
        empty_slots=empty_slots,
        alerts=alerts,
    )


def build_league_depth_chart(snapshot: dict, fc: FantasyCalcClient, intel, grades: list[dict]) -> DepthChartPage:
    grades_map = {g["name"]: g for g in grades}
    columns = ["QB1", "QB2", "QB3", "RB1", "RB2", "WR1", "WR2"]
    slot_order = {
        "QB": ["QB1", "QB2", "QB3"],
        "RB": ["RB1", "RB2"],
        "WR": ["WR1", "WR2"],
    }
    rows: list[DepthTeamRow] = []
    for team in snapshot.get("teams") or []:
        by_pos: dict[str, list[PlayerCard]] = {k: [] for k in CORE_POSITIONS}
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in by_pos:
                continue
            card = _player_card(
                {"name": p.get("name"), "position": pos, "nfl_team": p.get("team"), "id": p.get("id"), "age": p.get("age"), "injury": p.get("injury_status"), "starter": p.get("is_starter")},
                fc, intel, grades_map,
            )
            by_pos[pos].append(card)
        for pos in by_pos:
            by_pos[pos].sort(key=lambda x: x.value, reverse=True)

        slots: dict[str, PlayerCard | None] = {c: None for c in columns}
        for pos, keys in slot_order.items():
            for i, key in enumerate(keys):
                if i < len(by_pos.get(pos, [])):
                    slots[key] = by_pos[pos][i]

        rows.append(DepthTeamRow(
            team_name=team.get("team_name") or team.get("owner_name") or "Team",
            manager=team.get("owner_name") or "",
            slots=slots,
        ))
    rows.sort(key=lambda r: r.team_name.lower())
    return DepthChartPage(teams=len(rows), rows=rows, columns=columns)


def build_injury_page(my_team: dict, roster_rows: list[dict], fc: FantasyCalcClient, intel, grades: list[dict]) -> InjuryPage:
    grades_map = {g["name"]: g for g in grades}
    players = [_player_card(p, fc, intel, grades_map) for p in _roster_with_ids(my_team, roster_rows)]
    flagged_rows = injury_report(roster_rows)
    flagged_names = {r["name"] for r in flagged_rows}
    flagged = [p for p in players if p.name in flagged_names]
    bench_injured = [p for p in flagged if not p.starter]

    callout = ""
    if bench_injured:
        top = max(bench_injured, key=lambda x: x.value)
        badge, _ = injury_badge(top.injury)
        callout = f"All tags are on the bench — {top.name} ({badge}) is the most valuable name on the board."

    return InjuryPage(flagged=flagged, bench_injured=bench_injured, callout=callout)


def build_my_team_page(my_team: dict, roster_rows: list[dict], fc: FantasyCalcClient, intel, grades: list[dict]) -> MyTeamPage:
    grades_map = {g["name"]: g for g in grades}
    players = [_player_card(p, fc, intel, grades_map) for p in _roster_with_ids(my_team, roster_rows)]
    skill = [p for p in players if p.position in {"QB", "RB", "WR", "TE"}]
    total = sum(p.value for p in skill) or 1
    rooms: list[RosterRoom] = []
    labels = {"QB": "Quarterbacks", "RB": "Running Backs", "WR": "Wide Receivers", "TE": "Tight Ends"}
    for pos in ("QB", "RB", "WR", "TE"):
        group = sorted([p for p in skill if p.position == pos], key=lambda x: x.value, reverse=True)
        if not group:
            continue
        room_total = sum(p.value for p in group)
        rooms.append(RosterRoom(
            position=pos,
            label=labels[pos],
            color=POS_COLORS[pos],
            total_value=room_total,
            pct=int(room_total / total * 100),
            players=group,
        ))
    return MyTeamPage(
        rooms=rooms,
        total_value=total,
        shown=len(skill),
        total_players=len(skill),
    )


def build_bench_ledger_page(my_team: dict, roster_rows: list[dict], fc: FantasyCalcClient, intel, grades: list[dict]) -> list[PlayerCard]:
    grades_map = {g["name"]: g for g in grades}
    bench_names = {r["name"] for r in bench_ledger(roster_rows)}
    players = [_player_card(p, fc, intel, grades_map) for p in _roster_with_ids(my_team, roster_rows)]
    return sorted([p for p in players if p.name in bench_names], key=lambda x: x.value, reverse=True)


def build_bye_page(roster_rows: list[dict], fc: FantasyCalcClient, intel, grades: list[dict], my_team: dict) -> list[PlayerCard]:
    grades_map = {g["name"]: g for g in grades}
    bye_names = {r["name"] for r in bye_week_board(roster_rows)}
    players = [_player_card(p, fc, intel, grades_map) for p in _roster_with_ids(my_team, roster_rows)]
    out = [p for p in players if p.name in bye_names]
    for p, row in zip(out, bye_week_board(roster_rows)):
        p.depth_note = f"Week {row.get('bye_week')} bye"
    return out
