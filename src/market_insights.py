"""Free market rankings & insights — no API key required.

Sources:
- FantasyCalc (trade values, ranks, trends) — https://www.fantasycalc.com
- LeagueLogs (dynasty market ranks) — https://developer.leaguelogs.com
- Sleeper search rank & trending (via PlayerIntel)
- Optional FantasyPros when FANTASYPROS_API_KEY is set
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from src.fantasycalc import FantasyCalcClient, FantasyCalcValue

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
LL_CACHE = CACHE_DIR / "leaguelogs_market.json"
LL_TTL = 12 * 3600
LL_URL = "https://developer.leaguelogs.com/v1/market"


@dataclass
class MarketInsight:
    name: str
    fc_value: int | None = None
    fc_rank: int | None = None
    fc_trend: str = ""
    ll_rank: int | None = None
    ll_value: float | None = None
    fp_summary: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = []
        if self.fc_rank:
            parts.append(f"Market #{self.fc_rank}")
        if self.fc_value:
            parts.append(f"FC {self.fc_value:,}")
        if self.fc_trend and self.fc_trend != "Stable":
            parts.append(self.fc_trend)
        if self.ll_rank and (not self.fc_rank or abs(self.ll_rank - self.fc_rank) > 8):
            parts.append(f"LL #{self.ll_rank}")
        if self.fp_summary:
            parts.append(self.fp_summary)
        return " · ".join(parts) if parts else ""


def _clean_name(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I).strip()


def _league_logs_profile(config: dict) -> str:
    scoring = (config.get("scoring") or "ppr").lower()
    ppr_key = "ppr1" if scoring == "ppr" else "ppr0_5"
    fmt = "dynasty" if (config.get("format") or "dynasty").lower() == "dynasty" else "redraft"
    starters = config.get("starters") or {}
    qbs = "2qb" if starters.get("SUPERFLEX", 0) else "1qb"
    return f"{fmt}-{qbs}-12t-{ppr_key}"


class MarketInsightsClient:
    """Unified free insights; FantasyPros layered on when key exists."""

    def __init__(self, config: dict | None = None, fp_client=None):
        self.config = config or {}
        self.fc = FantasyCalcClient(self.config)
        self.fp = fp_client
        self._by_sleeper: dict[str, MarketInsight] = {}
        self._by_name: dict[str, MarketInsight] = {}
        self._loaded = False

    def load(self, force_refresh: bool = False) -> None:
        if self._loaded and not force_refresh:
            return
        self.fc.load(force_refresh=force_refresh)
        ll_index = self._load_leaguelogs(force_refresh)
        if self.fp and self.fp.available:
            self.fp.load(force_refresh=force_refresh)

        self._by_sleeper.clear()
        self._by_name.clear()

        # Index from FantasyCalc (primary)
        for key, fc in {**self.fc._by_name, **self.fc._by_sleeper}.items():
            if not isinstance(fc, FantasyCalcValue):
                continue
            if fc.position == "PICK":
                continue
            ll = ll_index.get(fc.sleeper_id or "", {})
            fp_sum = ""
            if self.fp and self.fp.available:
                fp = self.fp.get(fc.name)
                if fp:
                    fp_sum = fp.summary
            insight = MarketInsight(
                name=fc.name,
                fc_value=fc.value,
                fc_rank=fc.overall_rank,
                fc_trend=fc.trend_label,
                ll_rank=ll.get("overallRank"),
                ll_value=ll.get("value"),
                fp_summary=fp_sum,
            )
            self._by_name[fc.name.lower()] = insight
            self._by_name[_clean_name(fc.name)] = insight
            if fc.sleeper_id:
                self._by_sleeper[fc.sleeper_id] = insight

        self._loaded = True

    def _load_leaguelogs(self, force_refresh: bool) -> dict[str, dict]:
        profile = _league_logs_profile(self.config)
        if not force_refresh and LL_CACHE.exists():
            age = time.time() - LL_CACHE.stat().st_mtime
            if age < LL_TTL:
                try:
                    blob = json.loads(LL_CACHE.read_text(encoding="utf-8"))
                    if blob.get("profile") == profile:
                        return blob.get("index") or {}
                except Exception:
                    pass

        index: dict[str, dict] = {}
        try:
            with httpx.Client(timeout=45) as client:
                resp = client.get(f"{LL_URL}/{profile}")
                if resp.status_code == 200:
                    for row in resp.json().get("data") or []:
                        sid = str(row.get("sleeperPlayerId") or "")
                        if sid:
                            index[sid] = row
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    LL_CACHE.write_text(
                        json.dumps({"profile": profile, "ts": time.time(), "index": index}, indent=2),
                        encoding="utf-8",
                    )
        except Exception:
            pass
        return index

    def get(self, name: str, sleeper_id: str | None = None) -> MarketInsight | None:
        if not self._loaded:
            self.load()
        if sleeper_id and sleeper_id in self._by_sleeper:
            return self._by_sleeper[sleeper_id]
        return self._by_name.get(name.lower()) or self._by_name.get(_clean_name(name))

    @property
    def fc_client(self) -> FantasyCalcClient:
        if not self._loaded:
            self.load()
        return self.fc
