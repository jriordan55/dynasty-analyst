"""Vegas vs model signals — market-implied points vs our consensus."""

from __future__ import annotations

import re
from dataclasses import dataclass


def _clean(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I).strip()


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


@dataclass
class VegasSignal:
    player: str
    position: str
    vegas_pts: float  # market / books implied half-PPR season
    our_pts: float
    edge: float  # our - vegas (positive = value)
    vgs: int  # display score (market anchor)
    vgs_trend: float  # edge momentum proxy
    confidence: str
    note: str


def compute_vegas_signal(
    name: str,
    position: str,
    adp: float | None,
    fc_value: int = 0,
    fc_rank: int = 999,
    fc_trend: int = 0,
    scoring: str = "Half-PPR",
) -> VegasSignal | None:
    """Lightweight Vegas signal without rebuilding full projection boards."""
    mult = _scoring_mult(scoring)
    market_pts = _season_pts_from_adp(adp, position)
    if not market_pts and not fc_value:
        return None
    if market_pts:
        market_pts = round(market_pts * mult, 1)
    else:
        market_pts = round(_season_pts_from_fc(fc_value, position, fc_rank) * mult * 0.92, 1)

    our_pts = round(_season_pts_from_fc(fc_value, position, fc_rank) * mult, 1)
    edge = round(our_pts - market_pts, 1)
    vgs = int(round(market_pts))
    vgs_trend = round(fc_trend / 100.0 * 8 + edge * 0.12, 1)
    spread_pct = abs(edge) / max(our_pts, 1) * 100
    confidence = "HIGH" if spread_pct <= 8 else ("MED" if spread_pct <= 15 else "LOW")
    note = f"Books ~{market_pts:.0f} half-PPR · We ~{our_pts:.0f} · {edge:+.1f} edge"

    return VegasSignal(
        player=name,
        position=position,
        vegas_pts=market_pts,
        our_pts=our_pts,
        edge=edge,
        vgs=vgs,
        vgs_trend=vgs_trend,
        confidence=confidence,
        note=note,
    )


def build_vegas_index(
    fc_client,
    rows: list[tuple[str, str, float | None]],
    scoring: str = "Half-PPR",
) -> dict[str, VegasSignal]:
    """Map player name → VegasSignal from (name, position, adp) rows."""
    index: dict[str, VegasSignal] = {}
    for name, position, adp in rows:
        fc_v = fc_client.get(name)
        sig = compute_vegas_signal(
            name,
            position,
            adp,
            fc_value=fc_v.value if fc_v else 0,
            fc_rank=fc_v.overall_rank if fc_v else 999,
            fc_trend=fc_v.trend_30d if fc_v else 0,
            scoring=scoring,
        )
        if not sig:
            continue
        index[name.lower()] = sig
        index[_clean(name)] = sig
    return index


def get_vegas_signal(index: dict[str, VegasSignal], name: str) -> VegasSignal | None:
    return index.get(name.lower()) or index.get(_clean(name))
