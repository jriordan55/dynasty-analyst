"""FantasyCalc dynasty trade values — https://www.fantasycalc.com/trade-calculator"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_FILE = CACHE_DIR / "fantasycalc_values.json"
CACHE_TTL = 6 * 3600  # 6 hours
API_URL = "https://api.fantasycalc.com/values/current"


@dataclass
class FantasyCalcValue:
    name: str
    position: str
    value: int
    overall_rank: int
    position_rank: int
    trend_30d: int
    sleeper_id: str | None = None
    tier: int | None = None
    roster_pct: float | None = None

    @property
    def display_value(self) -> str:
        return f"{self.value:,}"

    @property
    def trend_label(self) -> str:
        if self.trend_30d > 50:
            return f"Rising (+{self.trend_30d})"
        if self.trend_30d < -50:
            return f"Falling ({self.trend_30d})"
        if self.trend_30d > 0:
            return f"Up +{self.trend_30d}"
        if self.trend_30d < 0:
            return f"Down {self.trend_30d}"
        return "Stable"


def _clean_name(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I).strip()


def _league_params(config: dict) -> dict:
    scoring = (config.get("scoring") or "ppr").lower()
    ppr = {"ppr": 1, "half": 0.5, "half_ppr": 0.5, "standard": 0, "std": 0}.get(scoring, 1)
    starters = config.get("starters") or {}
    num_qbs = 2 if starters.get("SUPERFLEX", 0) else 1
    league = config.get("league") or {}
    num_teams = league.get("total_rosters") or league.get("settings", {}).get("num_teams") or 12
    if num_teams not in (10, 12, 14):
        num_teams = 12 if num_teams <= 11 else 14
    is_dynasty = (config.get("format") or "dynasty").lower() == "dynasty"
    return {
        "isDynasty": str(is_dynasty).lower(),
        "numQbs": num_qbs,
        "numTeams": num_teams,
        "ppr": ppr,
    }


class FantasyCalcClient:
    """Trade values from real trades — matches FantasyCalc calculator settings."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._by_name: dict[str, FantasyCalcValue] = {}
        self._by_sleeper: dict[str, FantasyCalcValue] = {}
        self._picks: dict[str, FantasyCalcValue] = {}
        self._loaded = False

    def load(self, force_refresh: bool = False) -> None:
        if self._loaded and not force_refresh:
            return
        params = _league_params(self.config)
        cache_key = json.dumps(params, sort_keys=True)
        cached = self._read_cache(cache_key)
        if cached and not force_refresh:
            self._index(cached)
            self._loaded = True
            return

        with httpx.Client(timeout=30) as client:
            resp = client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        self._write_cache(cache_key, data)
        self._index(data)
        self._loaded = True

    def _read_cache(self, cache_key: str) -> list | None:
        if not CACHE_FILE.exists():
            return None
        try:
            blob = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if blob.get("key") != cache_key:
                return None
            if time.time() - blob.get("ts", 0) > CACHE_TTL:
                return None
            return blob.get("data")
        except Exception:
            return None

    def _write_cache(self, cache_key: str, data: list) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps({"key": cache_key, "ts": time.time(), "data": data}, indent=2),
            encoding="utf-8",
        )

    def _index(self, data: list) -> None:
        self._by_name.clear()
        self._by_sleeper.clear()
        self._picks.clear()
        for entry in data:
            player = entry.get("player") or {}
            name = player.get("name") or ""
            pos = player.get("position") or ""
            fc = FantasyCalcValue(
                name=name,
                position=pos,
                value=int(entry.get("value") or 0),
                overall_rank=int(entry.get("overallRank") or 999),
                position_rank=int(entry.get("positionRank") or 999),
                trend_30d=int(entry.get("trend30Day") or 0),
                sleeper_id=str(player.get("sleeperId")) if player.get("sleeperId") else None,
                tier=entry.get("maybeTier"),
                roster_pct=entry.get("maybeRosterPercent"),
            )
            if pos == "PICK":
                self._picks[name.lower()] = fc
                self._picks[_clean_name(name)] = fc
            else:
                self._by_name[name.lower()] = fc
                self._by_name[_clean_name(name)] = fc
                if fc.sleeper_id:
                    self._by_sleeper[fc.sleeper_id] = fc

    def get(self, name: str, sleeper_id: str | None = None) -> FantasyCalcValue | None:
        if not self._loaded:
            self.load()
        if sleeper_id and sleeper_id in self._by_sleeper:
            return self._by_sleeper[sleeper_id]
        key = name.lower()
        return self._by_name.get(key) or self._by_name.get(_clean_name(name))

    def pick_value(self, season: str | int, round_no: int, slot: int | None = None) -> FantasyCalcValue | None:
        if not self._loaded:
            self.load()
        season = str(season)
        if slot:
            label = f"{season} pick {round_no}.{slot:02d}"
            hit = self._picks.get(label.lower())
            if hit:
                return hit
        # Closest pick in same round
        prefix = f"{season} pick {round_no}."
        matches = [v for k, v in self._picks.items() if k.startswith(prefix)]
        if matches:
            if slot:
                matches.sort(key=lambda v: abs(v.position_rank - slot))
            return matches[0]
        # Any season, round average
        round_matches = [v for k, v in self._picks.items() if f"pick {round_no}." in k]
        if round_matches:
            round_matches.sort(key=lambda v: v.value, reverse=True)
            return round_matches[len(round_matches) // 2]
        return None

    def evaluate_trade(
        self,
        send_players: list[str],
        receive_players: list[str],
        send_picks: list[tuple[str, int, int | None]] | None = None,
        receive_picks: list[tuple[str, int, int | None]] | None = None,
        sleeper_ids: dict[str, str] | None = None,
    ) -> dict:
        """Return FantasyCalc-side trade math (same basis as fantasycalc.com calculator)."""
        send_total = 0
        recv_total = 0
        send_detail: list[str] = []
        recv_detail: list[str] = []
        ids = sleeper_ids or {}

        for name in send_players:
            fc = self.get(name, ids.get(name))
            if fc:
                send_total += fc.value
                send_detail.append(f"{name} ({fc.display_value})")
            else:
                send_detail.append(f"{name} (no FC value)")

        for name in receive_players:
            fc = self.get(name, ids.get(name))
            if fc:
                recv_total += fc.value
                recv_detail.append(f"{name} ({fc.display_value})")
            else:
                recv_detail.append(f"{name} (no FC value)")

        for season, rnd, slot in send_picks or []:
            fc = self.pick_value(season, rnd, slot)
            if fc:
                send_total += fc.value
                send_detail.append(f"{fc.name} ({fc.display_value})")

        for season, rnd, slot in receive_picks or []:
            fc = self.pick_value(season, rnd, slot)
            if fc:
                recv_total += fc.value
                recv_detail.append(f"{fc.name} ({fc.display_value})")

        delta = recv_total - send_total
        if abs(delta) <= max(150, send_total * 0.03):
            verdict = "Fair on FantasyCalc"
        elif delta > 0:
            verdict = "You win on FantasyCalc"
        else:
            verdict = "You overpay on FantasyCalc"

        return {
            "send_total": send_total,
            "receive_total": recv_total,
            "delta": delta,
            "verdict": verdict,
            "send_detail": send_detail,
            "receive_detail": recv_detail,
            "source": "FantasyCalc",
            "url": "https://www.fantasycalc.com/trade-calculator",
        }
