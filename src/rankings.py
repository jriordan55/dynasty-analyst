"""Rankings boards — Dynatyze markdown, ADP, FantasyCalc, LeagueLogs."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.adp import load_adp, lookup_adp
from src.fantasycalc import FantasyCalcClient
from src.market_insights import MarketInsightsClient

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
DYNATYZE_TTL = 6 * 3600

_ROW = re.compile(
    r"^\|\s*(?P<rank>\d+)\s*\|\s*\[(?P<player>[^\]]+)\]"
    r"\([^)]+\)\s*\|\s*(?P<pos>\w+)\s*\|\s*(?P<team>\w+)\s*\|\s*(?P<value>[\d,]+)\s*\|"
)


@dataclass
class RankRow:
    rank: int
    player: str
    position: str
    team: str
    value: int
    source: str
    fc_value: int | None = None
    fc_rank: int | None = None
    ll_rank: int | None = None
    adp: float | None = None
    on_roster: str | None = None  # manager name if in synced league
    signal: str = ""


def _cache_path(kind: str) -> Path:
    return CACHE_DIR / f"dynatyze_{kind}_rankings.md"


def fetch_dynatyze_rankings(kind: str = "dynasty", force: bool = False) -> tuple[list[RankRow], str]:
    """Pull public Dynatyze markdown rankings (top 75)."""
    urls = {
        "dynasty": "https://dynatyze.com/football/nfl-rankings.md",
        "redraft": "https://dynatyze.com/football/fantasy-rankings.md",
    }
    url = urls.get(kind, urls["dynasty"])
    cache = _cache_path(kind)
    text = ""
    updated = ""

    if not force and cache.exists() and time.time() - cache.stat().st_mtime < DYNATYZE_TTL:
        text = cache.read_text(encoding="utf-8")
    else:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers={"Accept": "text/markdown"})
            resp.raise_for_status()
            text = resp.text
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")

    m = re.search(r"Updated:\s*(.+)", text)
    if m:
        updated = m.group(1).strip()

    rows: list[RankRow] = []
    for line in text.splitlines():
        hit = _ROW.match(line.strip())
        if not hit:
            continue
        rows.append(
            RankRow(
                rank=int(hit.group("rank")),
                player=hit.group("player"),
                position=hit.group("pos"),
                team=hit.group("team"),
                value=int(hit.group("value").replace(",", "")),
                source="Dynatyze",
            )
        )
    return rows, updated


def overlay_league(rows: list[RankRow], snapshot: dict | None, config: dict | None = None) -> list[RankRow]:
    """Mark which manager owns each ranked player + FC/LL context."""
    if not snapshot:
        return rows

    name_to_mgr: dict[str, str] = {}
    for team in snapshot.get("teams") or []:
        mgr = team.get("owner_name") or team.get("team_name") or "Unknown"
        for p in team.get("players") or []:
            if p.get("name"):
                name_to_mgr[p["name"].lower()] = mgr

    cfg = config or {}
    fc = FantasyCalcClient({**cfg, "league": snapshot.get("league") or {}})
    fc.load()
    market = MarketInsightsClient({**cfg, "league": snapshot.get("league") or {}})
    market.load()
    adp_map = load_adp()

    out: list[RankRow] = []
    for row in rows:
        key = row.player.lower()
        fc_v = fc.get(row.player)
        mi = market.get(row.player)
        adp_entry = lookup_adp(row.player, adp_map)
        adp = adp_entry.adp if adp_entry else None
        signal = _buy_hold_signal(row, fc_v.value if fc_v else None, fc_v.trend_30d if fc_v else 0)
        out.append(
            RankRow(
                rank=row.rank,
                player=row.player,
                position=row.position,
                team=row.team,
                value=row.value,
                source=row.source,
                fc_value=fc_v.value if fc_v else None,
                fc_rank=fc_v.overall_rank if fc_v else None,
                ll_rank=mi.ll_rank if mi else None,
                adp=adp,
                on_roster=name_to_mgr.get(key),
                signal=signal,
            )
        )
    return out


def _buy_hold_signal(row: RankRow, fc_value: int | None, trend: int) -> str:
    if trend >= 80:
        return "BUY"
    if trend <= -80:
        return "SELL"
    if fc_value and row.value:
        gap = (fc_value - row.value) / max(row.value, 1) * 100
        if gap >= 8:
            return "BUY"
        if gap <= -8:
            return "SELL"
    return "HOLD"


def adp_rankings(config: dict, snapshot: dict | None = None, limit: int = 150) -> tuple[list[RankRow], str]:
    from src.adp_sources import build_adp_board

    board, note = build_adp_board(config, snapshot, limit=limit)
    rows: list[RankRow] = []
    for b in board:
        rows.append(
            RankRow(
                rank=b.rank,
                player=b.player,
                position=b.position,
                team=b.team,
                value=int(b.consensus or 0),
                source=f"{b.sources} sources",
                adp=b.consensus,
                on_roster=b.on_roster,
            )
        )
    return rows, note


def fc_rankings(config: dict, limit: int = 100) -> list[RankRow]:
    fc = FantasyCalcClient(config)
    fc.load()
    if not fc._loaded:
        return []
    values = sorted(fc._by_name.values(), key=lambda v: v.value, reverse=True)
    seen: set[str] = set()
    rows: list[RankRow] = []
    rank = 0
    for v in values:
        if v.position == "PICK":
            continue
        key = v.name.lower()
        if key in seen:
            continue
        seen.add(key)
        rank += 1
        if rank > limit:
            break
        rows.append(
            RankRow(
                rank=rank,
                player=v.name,
                position=v.position,
                team="",
                value=v.value,
                source="FantasyCalc",
                fc_value=v.value,
                fc_rank=v.overall_rank,
                signal="BUY" if v.trend_30d >= 50 else ("SELL" if v.trend_30d <= -50 else "HOLD"),
            )
        )
    return rows


def pick_rankings(config: dict) -> list[RankRow]:
    fc = FantasyCalcClient(config)
    fc.load()
    picks = sorted(fc._picks.values(), key=lambda v: v.value, reverse=True)
    seen: set[str] = set()
    rows: list[RankRow] = []
    for i, p in enumerate(picks, 1):
        key = p.name.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            RankRow(
                rank=i,
                player=p.name,
                position="PICK",
                team="",
                value=p.value,
                source="FantasyCalc",
                fc_value=p.value,
            )
        )
    return rows


def expert_consensus(config: dict, limit: int = 75) -> list[RankRow]:
    """FantasyCalc rank as consensus anchor with LeagueLogs overlay."""
    fc_rows = fc_rankings(config, limit=limit)
    market = MarketInsightsClient(config)
    market.load()
    out: list[RankRow] = []
    for row in fc_rows:
        mi = market.get(row.player)
        out.append(
            RankRow(
                rank=row.fc_rank or row.rank,
                player=row.player,
                position=row.position,
                team=row.team,
                value=row.fc_value or 0,
                source="Expert consensus",
                fc_value=row.fc_value,
                fc_rank=row.fc_rank,
                ll_rank=mi.ll_rank if mi else None,
                signal=row.signal,
            )
        )
    return out


def where_we_disagree(config: dict, min_gap: int = 12, limit: int = 50) -> list[RankRow]:
    """Players where FantasyCalc and LeagueLogs ranks diverge."""
    fc_rows = fc_rankings(config, limit=200)
    market = MarketInsightsClient(config)
    market.load()
    rows: list[RankRow] = []
    for row in fc_rows:
        mi = market.get(row.player)
        if not mi or not mi.ll_rank or not row.fc_rank:
            continue
        gap = abs(mi.ll_rank - row.fc_rank)
        if gap < min_gap:
            continue
        direction = "FC higher" if row.fc_rank < mi.ll_rank else "LL higher"
        rows.append(
            RankRow(
                rank=gap,
                player=row.player,
                position=row.position,
                team=row.team,
                value=row.fc_value or 0,
                source=direction,
                fc_value=row.fc_value,
                fc_rank=row.fc_rank,
                ll_rank=mi.ll_rank,
                signal=f"Δ{gap}",
            )
        )
    rows.sort(key=lambda r: r.rank, reverse=True)
    for i, row in enumerate(rows[:limit], 1):
        row.rank = i
    return rows[:limit]
