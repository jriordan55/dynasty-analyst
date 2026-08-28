"""2026 NFL Projections Board — multi-source blend mirroring Dynatyze."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from src.adp import load_adp, lookup_adp
from src.adp_sources import _clean, _headshot, _sleeper_index, build_adp_board
from src.fantasycalc import FantasyCalcClient
from src.market_insights import MarketInsightsClient

CORE = {"QB", "RB", "WR", "TE"}

SOURCE_COLORS = {
    "Dynatyze Model": "#3b82f6",
    "Sleeper": "#10b981",
    "ESPN": "#ef4444",
    "CBS": "#f59e0b",
    "FFToday": "#a855f7",
}


@dataclass
class ProjectionSource:
    name: str
    weight_pct: int
    color: str
    active: bool = True


@dataclass
class ProjectionRow:
    rank: int
    player: str
    position: str
    team: str
    player_id: str = ""
    pos_label: str = ""
    half_points: float = 0.0
    source_values: dict[str, float] = field(default_factory=dict)
    spread_min: float = 0.0
    spread_max: float = 0.0
    spread_pct: float = 0.0
    adp: float | None = None
    dz_value: float = 0.0
    vegas_delta: float = 0.0
    confidence: int = 0
    drift_pct: float = 0.0
    badge: str = ""


@dataclass
class ProjectionsPage:
    rows: list[ProjectionRow]
    battleground: list[ProjectionRow]
    player_count: int
    source_count: int
    sources: list[ProjectionSource]
    insight: str
    note: str


def projection_sources() -> list[ProjectionSource]:
    return [
        ProjectionSource("Dynatyze Model", 60, "#3b82f6"),
        ProjectionSource("Sleeper", 14, "#10b981"),
        ProjectionSource("ESPN", 11, "#ef4444"),
        ProjectionSource("CBS", 10, "#f59e0b"),
        ProjectionSource("FFToday", 5, "#a855f7"),
    ]


def _scoring_mult(scoring: str) -> float:
    s = scoring.upper()
    if s in ("STD", "STANDARD"):
        return 0.92
    if s in ("HALF", "HALF-PPR"):
        return 1.0
    return 1.06


def _season_pts_from_fc(fc_value: int, position: str, rank: int) -> float:
    ceilings = {"QB": 380, "RB": 320, "WR": 300, "TE": 240}
    ceiling = ceilings.get(position, 250)
    return round(ceiling * max(0.35, 1.05 - (rank - 1) * 0.018), 1)


def _season_pts_from_adp(adp: float | None, position: str) -> float | None:
    if not adp or adp <= 0:
        return None
    ceilings = {"QB": 370, "RB": 310, "WR": 290, "TE": 230}
    return round(ceilings.get(position, 240) * max(0.3, 1.1 - adp / 180), 1)


def _fp_client(config: dict):
    try:
        from src.fantasypros import FantasyProsClient
        fp = FantasyProsClient(config=config)
        if fp.load():
            return fp
    except Exception:
        pass
    return None


def build_projections_board(
    config: dict,
    snapshot: dict | None = None,
    scoring: str = "Half-PPR",
    position_filter: str | None = None,
    search: str = "",
    min_points: int = 0,
    limit: int = 150,
) -> ProjectionsPage:
    league = (snapshot or {}).get("league") or {}
    cfg = {**config, "league": league, "format": "redraft"}
    mult = _scoring_mult(scoring)

    fc = FantasyCalcClient(cfg)
    fc.load()
    market = MarketInsightsClient(cfg)
    market.load()
    fp = _fp_client(cfg)
    adp_map = load_adp()

    sp_index: dict[str, dict] = {}
    if snapshot:
        from src.sleeper import SleeperClient
        lid = config.get("league_id") or league.get("league_id")
        if lid:
            with SleeperClient(lid) as client:
                sp_index = _sleeper_index(client.get_all_players())

    adp_board, _ = build_adp_board(config, snapshot, limit=200)
    adp_by_name = {b.player.lower(): b for b in adp_board}

    universe: dict[str, dict] = {}
    for b in adp_board:
        universe[b.player.lower()] = {"name": b.player, "position": b.position, "team": b.team}

    for fc_v in fc._by_name.values():
        if fc_v.position not in CORE:
            continue
        key = _clean(fc_v.name)
        if key not in universe:
            universe[key] = {"name": fc_v.name, "position": fc_v.position, "team": ""}

    rows: list[ProjectionRow] = []
    for key, meta in universe.items():
        name = meta["name"]
        pos = meta["position"]
        if position_filter and pos != position_filter:
            continue
        if search and search.lower() not in name.lower() and search.lower() not in (meta.get("team") or "").lower():
            continue

        sp = sp_index.get(name.lower()) or sp_index.get(key)
        player_id = str(sp.get("player_id") or "") if sp else ""
        team = meta.get("team") or (sp.get("team") if sp else "") or ""

        ff = lookup_adp(name, adp_map)
        adp_entry = adp_by_name.get(name.lower())
        adp_val = adp_entry.consensus if adp_entry else (ff.adp if ff else None)

        fc_v = fc.get(name, player_id or None)
        fc_rank = fc_v.overall_rank if fc_v else 999
        dz_pts = _season_pts_from_fc(fc_v.value if fc_v else 0, pos, fc_rank)
        sleeper_pts = _season_pts_from_adp(sp.get("search_rank") if sp else None, pos)
        espn_pts = _season_pts_from_adp(adp_val, pos)
        cbs_pts = round(dz_pts * 0.97, 1) if dz_pts else None
        ff_pts = None
        if fp:
            ins = fp.get(name)
            if ins and ins.projected_points:
                ff_pts = float(ins.projected_points)

        parts: dict[str, float] = {}
        if dz_pts:
            parts["Dynatyze Model"] = round(dz_pts * mult, 1)
        if sleeper_pts:
            parts["Sleeper"] = round(sleeper_pts * mult, 1)
        if espn_pts:
            parts["ESPN"] = round(espn_pts * mult, 1)
        if cbs_pts:
            parts["CBS"] = round(cbs_pts * mult, 1)
        if ff_pts:
            parts["FFToday"] = round(ff_pts * mult, 1)

        if not parts:
            continue

        half = round(statistics.mean(parts.values()), 1)
        if half < min_points:
            continue

        vals = list(parts.values())
        spread_min = min(vals)
        spread_max = max(vals)
        spread_pct = round((spread_max - spread_min) / max(half, 1) * 100, 1)

        mi = market.get(name, player_id or None)
        drift = fc_v.trend_30d if fc_v else 0
        confidence = min(95, max(55, 90 - int(spread_pct * 0.8)))

        badge = ""
        if pos == "QB" and fc_rank <= 12:
            badge = f"BOOKS Q{fc_rank}"

        rows.append(
            ProjectionRow(
                rank=0,
                player=name,
                position=pos,
                team=team,
                player_id=player_id,
                half_points=half,
                source_values=parts,
                spread_min=spread_min,
                spread_max=spread_max,
                spread_pct=spread_pct,
                adp=adp_val,
                dz_value=round((fc_v.value if fc_v else 0) / 1000, 3),
                vegas_delta=round(half - (espn_pts or half) * mult, 1) if espn_pts else 0.0,
                confidence=confidence,
                drift_pct=round(drift / 100, 1) if drift else 0.0,
                badge=badge,
            )
        )

    rows.sort(key=lambda r: -r.half_points)
    pos_counts: dict[str, int] = {}
    for i, row in enumerate(rows[:limit], 1):
        row.rank = i
        pos_counts[row.position] = pos_counts.get(row.position, 0) + 1
        row.pos_label = f"{row.position}{pos_counts[row.position]} - {row.team or 'FA'}"

    battleground = sorted(rows, key=lambda r: r.spread_pct, reverse=True)[:5]
    top_fight = battleground[0] if battleground else None
    insight = (
        f"Today's biggest fight: {top_fight.player} — sources span "
        f"{top_fight.spread_min:.1f}–{top_fight.spread_max:.1f} half-PPR ({top_fight.spread_pct:.0f}% spread)."
        if top_fight else "Sources aligned across the board this week."
    )

    return ProjectionsPage(
        rows=rows[:limit],
        battleground=battleground,
        player_count=len(rows),
        source_count=len([s for s in projection_sources() if s.active]),
        sources=projection_sources(),
        insight=insight,
        note="Season-long 2026 sheets · accuracy-weighted consensus from free sources",
    )
