"""FantasyPros consensus rankings & projections — https://www.fantasypros.com/nfl/

Requires FANTASYPROS_API_KEY — request at https://www.fantasypros.com/api-data/
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_TTL = 12 * 3600
BASE_URL = "https://api.fantasypros.com/v2/json/nfl"


@dataclass
class FantasyProsInsight:
    name: str
    ecr_rank: int | None = None
    pos_rank: str | None = None
    tier: int | None = None
    rank_min: int | None = None
    rank_max: int | None = None
    projected_points: float | None = None
    projection_note: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = []
        if self.ecr_rank:
            parts.append(f"ECR #{self.ecr_rank}")
        if self.pos_rank:
            parts.append(f"Pos {self.pos_rank}")
        if self.tier:
            parts.append(f"Tier {self.tier}")
        if self.projected_points:
            parts.append(f"Proj {self.projected_points:.0f} pts")
        if self.projection_note:
            parts.append(self.projection_note)
        return " · ".join(parts) if parts else ""


def _clean_name(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I).strip()


def _scoring_param(config: dict) -> str:
    scoring = (config.get("scoring") or "ppr").lower()
    return {"ppr": "PPR", "half": "HALF", "half_ppr": "HALF", "standard": "STD", "std": "STD"}.get(scoring, "PPR")


class FantasyProsClient:
    def __init__(self, api_key: str | None = None, config: dict | None = None):
        self.api_key = api_key or os.getenv("FANTASYPROS_API_KEY", "")
        self.config = config or {}
        self._rankings: dict[str, FantasyProsInsight] = {}
        self._loaded = False
        self.available = bool(self.api_key)

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key}

    def _season(self) -> str:
        league = self.config.get("league") or {}
        return str(league.get("season") or "2025")

    def load(self, force_refresh: bool = False) -> bool:
        if not self.api_key:
            return False
        if self._loaded and not force_refresh:
            return True

        cache_path = CACHE_DIR / f"fantasypros_{self._season()}.json"
        if not force_refresh and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < CACHE_TTL:
                self._index(json.loads(cache_path.read_text(encoding="utf-8")))
                self._loaded = True
                return True

        scoring = _scoring_param(self.config)
        season = self._season()
        combined: dict[str, dict] = {}

        try:
            with httpx.Client(timeout=30) as client:
                for pos in ("QB", "RB", "WR", "TE"):
                    resp = client.get(
                        f"{BASE_URL}/{season}/consensus-rankings",
                        params={"position": pos, "scoring": scoring},
                        headers=self._headers(),
                    )
                    if resp.status_code == 403:
                        return False
                    resp.raise_for_status()
                    for p in resp.json().get("players") or []:
                        name = p.get("player_name") or p.get("name") or ""
                        if name:
                            combined[name.lower()] = {**p, "_position": pos}

                # Rest-of-season / preseason projections (week=0)
                for pos in ("QB", "RB", "WR", "TE"):
                    try:
                        presp = client.get(
                            f"{BASE_URL}/{season}/projections",
                            params={"position": pos, "scoring": scoring, "week": 0},
                            headers=self._headers(),
                        )
                        if presp.status_code != 200:
                            continue
                        for p in presp.json().get("players") or []:
                            name = p.get("player_name") or p.get("name") or ""
                            if not name:
                                continue
                            pts = p.get("projected_points") or p.get("points") or p.get("fpts")
                            if pts is None:
                                stats = p.get("stats") or p.get("projections") or {}
                                pts = stats.get("points") or stats.get("fpts")
                            key = name.lower()
                            if key in combined:
                                combined[key]["_projected_points"] = pts
                            else:
                                combined[key] = {"player_name": name, "_position": pos, "_projected_points": pts}
                    except Exception:
                        continue
        except Exception:
            return False

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
        self._index(combined)
        self._loaded = True
        return True

    def _index(self, combined: dict[str, dict]) -> None:
        self._rankings.clear()
        for key, p in combined.items():
            name = p.get("player_name") or p.get("name") or key
            pts = p.get("_projected_points")
            try:
                pts_f = float(pts) if pts is not None else None
            except (TypeError, ValueError):
                pts_f = None

            rank_std = p.get("rank_std")
            tags = []
            if rank_std is not None:
                try:
                    if float(rank_std) <= 3:
                        tags.append("Expert consensus")
                    elif float(rank_std) >= 8:
                        tags.append("Experts split")
                except (TypeError, ValueError):
                    pass

            insight = FantasyProsInsight(
                name=name,
                ecr_rank=_int(p.get("rank_ecr")),
                pos_rank=p.get("pos_rank"),
                tier=_int(p.get("tier")),
                rank_min=_int(p.get("rank_min")),
                rank_max=_int(p.get("rank_max")),
                projected_points=pts_f,
                tags=tags,
            )
            self._rankings[name.lower()] = insight
            self._rankings[_clean_name(name)] = insight

    def get(self, name: str) -> FantasyProsInsight | None:
        if not self.api_key:
            return None
        if not self._loaded:
            self.load()
        return self._rankings.get(name.lower()) or self._rankings.get(_clean_name(name))


def _int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None
