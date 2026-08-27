"""Multi-source ADP board — mirrors Dynatyze ADP blend from free APIs."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from src.adp import load_adp, lookup_adp
from src.fantasycalc import FantasyCalcClient
from src.market_insights import MarketInsightsClient
from src.rankings import fetch_dynatyze_rankings
from src.models import Player

CORE = {"QB", "RB", "WR", "TE"}


@dataclass
class AdpBoardRow:
    player: str
    position: str
    team: str
    consensus: float | None
    sources: int
    variance: float | None
    four_for_four: int | None = None
    sleeper: int | None = None
    fantasycalc: int | None = None
    leaguelogs: int | None = None
    dynatyze: int | None = None
    on_roster: str | None = None
    rank: int = 0


def _clean(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I).strip()


def _sleeper_index(sleeper_players: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for pdata in sleeper_players.values():
        full = pdata.get("full_name") or f"{pdata.get('first_name', '')} {pdata.get('last_name', '')}".strip()
        if not full:
            continue
        index[full.lower()] = pdata
        index[_clean(full)] = pdata
    return index


def _redraft_fc_client(config: dict) -> FantasyCalcClient:
    cfg = {**config, "format": "redraft"}
    return FantasyCalcClient(cfg)


def _dynatyze_redraft_ranks() -> dict[str, int]:
    rows, _ = fetch_dynatyze_rankings("redraft")
    return {_clean(r.player): r.rank for r in rows}


def build_adp_board(
    config: dict,
    snapshot: dict | None = None,
    sleeper_players: dict | None = None,
    limit: int = 150,
) -> tuple[list[AdpBoardRow], str]:
    """Blend ADP from 4for4, Sleeper, FantasyCalc redraft, LeagueLogs, Dynatyze redraft board."""
    adp_map = load_adp()
    league = (snapshot or {}).get("league") or {}
    cfg = {**config, "league": league, "format": "redraft"}

    fc = _redraft_fc_client(cfg)
    fc.load()
    market = MarketInsightsClient(cfg)
    market.load()

    sp_index: dict[str, dict] = {}
    if sleeper_players:
        sp_index = _sleeper_index(sleeper_players)
    elif snapshot:
        from src.sleeper import SleeperClient
        lid = config.get("league_id") or league.get("league_id")
        if lid:
            with SleeperClient(lid) as client:
                sp_index = _sleeper_index(client.get_all_players())

    dynatyze_ranks = _dynatyze_redraft_ranks()

    name_to_mgr: dict[str, str] = {}
    if snapshot:
        for team in snapshot.get("teams") or []:
            mgr = team.get("owner_name") or "Unknown"
            for p in team.get("players") or []:
                if p.get("name"):
                    name_to_mgr[p["name"].lower()] = mgr

    # Seed player universe from 4for4 + FC redraft + dynatyze top 75
    universe: dict[str, dict] = {}

    for player in adp_map.values():
        if player.position not in CORE:
            continue
        key = _clean(player.name)
        universe[key] = {
            "name": player.name,
            "position": player.position,
            "team": player.team or "",
        }

    for fc_v in fc._by_name.values():
        if fc_v.position not in CORE:
            continue
        key = _clean(fc_v.name)
        if key not in universe:
            universe[key] = {"name": fc_v.name, "position": fc_v.position, "team": ""}
        sp = sp_index.get(fc_v.name.lower()) or sp_index.get(key)
        if sp and sp.get("team"):
            universe[key]["team"] = sp.get("team")

    for key, rank in dynatyze_ranks.items():
        if key in universe:
            continue
        # find name from dynatyze rows - use rank keys only for players already partially known
        pass

    rows: list[AdpBoardRow] = []
    for key, meta in universe.items():
        name = meta["name"]
        ff = lookup_adp(name, adp_map)
        ff_adp = ff.adp if ff else None
        pos = meta["position"] or (ff.position if ff else "")
        team = meta["team"] or (ff.team if ff else "")

        sp = sp_index.get(name.lower()) or sp_index.get(key)
        sleeper_rank = sp.get("search_rank") if sp else None
        if sp and sp.get("team") and not team:
            team = sp.get("team", "")

        fc_v = fc.get(name, str(sp.get("player_id")) if sp else None)
        fc_rank = fc_v.overall_rank if fc_v else None

        mi = market.get(name, str(sp.get("player_id")) if sp else None)
        ll_rank = mi.ll_rank if mi else None

        dz_rank = dynatyze_ranks.get(key)

        parts = [v for v in (ff_adp, sleeper_rank, fc_rank, ll_rank, dz_rank) if v and v > 0]
        if not parts:
            continue

        consensus = round(statistics.median(parts), 1)
        variance = round(max(parts) - min(parts), 1) if len(parts) > 1 else 0.0

        rows.append(
            AdpBoardRow(
                player=name,
                position=pos,
                team=team or "",
                consensus=consensus,
                sources=len(parts),
                variance=variance,
                four_for_four=ff_adp,
                sleeper=sleeper_rank,
                fantasycalc=fc_rank,
                leaguelogs=ll_rank,
                dynatyze=dz_rank,
                on_roster=name_to_mgr.get(name.lower()),
            )
        )

    rows.sort(key=lambda r: (r.consensus or 9999, r.player))
    for i, row in enumerate(rows[:limit], 1):
        row.rank = i
    return rows[:limit], (
        "Median blend of 4for4, Sleeper search rank, FantasyCalc redraft, "
        "LeagueLogs, and Dynatyze redraft board · stale sources omitted per player"
    )


def adp_numeric(value: Player | int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, Player):
        return value.adp
    return int(value)
