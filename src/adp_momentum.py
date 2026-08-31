"""7-day ADP risers / fallers — snapshot history + FantasyCalc fallback."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
HISTORY_FILE = CACHE_DIR / "adp_history.json"
SNAPSHOT_INTERVAL = 20 * 3600  # one snapshot per ~20h
LOOKBACK_SEC = 7 * 86400


@dataclass
class AdpMomentum:
    player: str
    adp: float | None
    adp_7d_ago: float | None
    change_7d: float  # current - prior (negative = riser, ADP improved)
    label: str  # RISER | FALLER | STABLE
    arrow: str  # ↗ or ↘
    color: str  # green | red | gray
    source: str  # history | estimate


def _load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {"snapshots": []}
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"snapshots": []}


def _save_history(blob: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(blob, indent=2), encoding="utf-8")


def record_adp_snapshot(consensus_by_player: dict[str, float], *, league_key: str = "default") -> None:
    """Append a daily ADP snapshot for 7-day delta tracking."""
    if not consensus_by_player:
        return
    blob = _load_history()
    now = time.time()
    snaps = blob.setdefault("snapshots", [])
    if snaps and now - snaps[-1].get("ts", 0) < SNAPSHOT_INTERVAL:
        snaps[-1]["players"] = consensus_by_player
        snaps[-1]["ts"] = now
        snaps[-1]["league_key"] = league_key
    else:
        snaps.append({"ts": now, "league_key": league_key, "players": consensus_by_player})
    # Keep ~45 days
    blob["snapshots"] = snaps[-45:]
    _save_history(blob)


def _snapshot_near(history: dict, target_ts: float) -> dict[str, float] | None:
    snaps = history.get("snapshots") or []
    if not snaps:
        return None
    best = min(snaps, key=lambda s: abs(s.get("ts", 0) - target_ts))
    if abs(best.get("ts", 0) - target_ts) > LOOKBACK_SEC * 1.5:
        return None
    return best.get("players") or {}


def _estimate_from_fc_trend(trend_30d: int) -> float:
    """Approximate 7-day ADP movement from FantasyCalc 30-day value trend."""
    if not trend_30d:
        return 0.0
    # Value up → ADP slot improves (number drops) → negative change
    return round(-trend_30d / 85.0, 1)


def _momentum_label(change: float) -> tuple[str, str, str]:
    if change <= -0.4:
        return "RISER", "↗", "green"
    if change >= 0.4:
        return "FALLER", "↘", "red"
    return "STABLE", "→", "gray"


def lookup_momentum(
    player: str,
    adp: float | None,
    *,
    fc_trend_30d: int = 0,
) -> AdpMomentum:
    """7-day ADP change for one player."""
    key = player.lower()
    history = _load_history()
    target = time.time() - LOOKBACK_SEC
    prior_map = _snapshot_near(history, target)

    change = 0.0
    prior = None
    source = "estimate"

    if prior_map and adp is not None:
        prior = prior_map.get(key) or prior_map.get(player)
        if prior is not None:
            change = round(adp - prior, 1)
            source = "history"

    if source == "estimate" and fc_trend_30d:
        change = _estimate_from_fc_trend(fc_trend_30d)
        if adp is not None:
            prior = round(adp - change, 1)

    label, arrow, color = _momentum_label(change)
    return AdpMomentum(
        player=player,
        adp=adp,
        adp_7d_ago=prior,
        change_7d=change,
        label=label,
        arrow=arrow,
        color=color,
        source=source,
    )


def top_movers(
    rows: list[tuple[str, float | None, int]],
    *,
    limit: int = 12,
) -> tuple[list[AdpMomentum], list[AdpMomentum]]:
    """Return (risers, fallers) from (name, adp, fc_trend) tuples."""
    scored: list[AdpMomentum] = []
    for name, adp, trend in rows:
        m = lookup_momentum(name, adp, fc_trend_30d=trend)
        if abs(m.change_7d) >= 0.3:
            scored.append(m)
    risers = sorted([m for m in scored if m.change_7d < 0], key=lambda m: m.change_7d)[:limit]
    fallers = sorted([m for m in scored if m.change_7d > 0], key=lambda m: -m.change_7d)[:limit]
    return risers, fallers
