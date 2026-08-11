from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.adp import lookup_adp
from src.models import Player

CORE_POSITIONS = {"QB", "RB", "WR", "TE"}

# 12-team replacement-level ADP ranks by position
REPLACEMENT_RANK = {"QB": 12, "RB": 24, "WR": 36, "TE": 12}

INJURY_PENALTIES = {
    "out": 40,
    "doubtful": 30,
    "injured reserve": 35,
    "ir": 35,
    "pup": 30,
    "questionable": 12,
    "probable": 4,
}


@dataclass
class PlayerContext:
    name: str
    position: str = ""
    adp: int | None = None
    sleeper_rank: int | None = None
    blended_adp: int | None = None
    injury_status: str = ""
    injury_detail: str = ""
    injury_penalty: float = 0.0
    sleeper_injury: str = ""
    depth_chart_order: int | None = None
    trending_signal: str = ""
    trending_count: int = 0
    news_headline: str = ""
    vor: float = 0.0
    role_note: str = ""
    upside_score: float = 0.0
    upside_note: str = ""
    flags: list[str] = field(default_factory=list)


ROLE_UPSIDE_PATTERN = re.compile(
    r"\b(starter|bellcow|bell cow|lead back|workhorse|wr1|alpha|expanded role|"
    r"snap share|snap count|promoted|depth chart|breakout|camp standout|"
    r"rb1|te1|starting job|feature back|hot hand|complement|inherited|"
    r"first-team|first team|expanded|target share|touches|volume)\b",
    re.I,
)


def _clean_name(name: str) -> str:
    return re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name.lower(), flags=re.I)


def _sleeper_index(sleeper_players: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for pdata in sleeper_players.values():
        full = pdata.get("full_name") or f"{pdata.get('first_name', '')} {pdata.get('last_name', '')}".strip()
        if full:
            index[full.lower()] = pdata
            index[_clean_name(full)] = pdata
    return index


def _injury_index(injuries: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for inj in injuries:
        name = inj.get("name", "")
        if name:
            index[name.lower()] = inj
            index[_clean_name(name)] = inj
    return index


def _trending_index(trending: dict, sleeper_players: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for kind in ("adds", "drops"):
        for entry in trending.get(kind, []):
            pid = str(entry.get("player_id", ""))
            pdata = sleeper_players.get(pid, {})
            name = pdata.get("full_name") or f"{pdata.get('first_name', '')} {pdata.get('last_name', '')}".strip()
            if not name:
                continue
            key = name.lower()
            index[key] = {
                "signal": "Hot add" if kind == "adds" else "Trending drop",
                "count": entry.get("count", 0),
                "kind": kind,
            }
    return index


def compute_replacement_levels(adp_map: dict[str, Player]) -> dict[str, int]:
    by_pos: dict[str, list[int]] = {p: [] for p in CORE_POSITIONS}
    for player in adp_map.values():
        if player.adp and player.position in CORE_POSITIONS:
            by_pos[player.position].append(player.adp)
    levels: dict[str, int] = {}
    for pos, ranks in by_pos.items():
        ranks.sort()
        idx = REPLACEMENT_RANK.get(pos, 12) - 1
        levels[pos] = ranks[idx] if len(ranks) > idx else (ranks[-1] if ranks else 180)
    return levels


def blend_adp(four_for_four: int | None, sleeper_rank: int | None) -> int | None:
    if four_for_four and sleeper_rank:
        return round((four_for_four + sleeper_rank) / 2)
    return four_for_four or sleeper_rank


def enrich_adp_map(adp_map: dict[str, Player], sleeper_players: dict) -> dict[str, Player]:
    """Blend 4for4 ADP with Sleeper search_rank for sharper market values."""
    index = _sleeper_index(sleeper_players)
    enriched: dict[str, Player] = {}
    for key, player in adp_map.items():
        sp = index.get(player.name.lower()) or index.get(_clean_name(player.name))
        sleeper_rank = sp.get("search_rank") if sp else None
        blended = blend_adp(player.adp, sleeper_rank)
        enriched[key] = Player(
            name=player.name,
            position=player.position,
            team=player.team or (sp.get("team") if sp else "") or "",
            age=sp.get("age") if sp else None,
            adp=blended,
            adp_position_rank=player.adp_position_rank,
        )
    return enriched


class PlayerIntel:
    """Merged external signals: ESPN injuries, Sleeper metadata, trending, news."""

    def __init__(
        self,
        adp_map: dict[str, Player],
        injuries: list[dict] | None = None,
        trending: dict | None = None,
        news: list[dict] | None = None,
        sleeper_players: dict | None = None,
    ) -> None:
        self.adp_map = adp_map
        self.injuries = injuries or []
        self.trending = trending or {}
        self.news = news or []
        self.sleeper_players = sleeper_players or {}
        self._injury_idx = _injury_index(self.injuries)
        self._trend_idx = _trending_index(self.trending, self.sleeper_players)
        self._sleeper_idx = _sleeper_index(self.sleeper_players)
        self.replacement_levels = compute_replacement_levels(adp_map)

    @classmethod
    def from_snapshot(cls, snapshot: dict, news_client=None) -> PlayerIntel:
        injuries: list[dict] = []
        news: list[dict] = []
        if news_client:
            try:
                injuries = news_client.get_injuries()
                news = news_client.get_news(limit=80)
            except Exception:
                pass
        from src.sleeper import CACHE_DIR
        import json

        sleeper_players: dict = {}
        cache = CACHE_DIR / "sleeper_players.json"
        if cache.exists():
            sleeper_players = json.loads(cache.read_text(encoding="utf-8"))

        from src.adp import load_adp

        adp_map = enrich_adp_map(load_adp(), sleeper_players)
        return cls(
            adp_map=adp_map,
            injuries=injuries,
            trending=snapshot.get("trending", {}),
            news=news,
            sleeper_players=sleeper_players,
        )

    def _lookup_sleeper(self, name: str) -> dict | None:
        return self._sleeper_idx.get(name.lower()) or self._sleeper_idx.get(_clean_name(name))

    def _lookup_injury(self, name: str) -> dict | None:
        return self._injury_idx.get(name.lower()) or self._injury_idx.get(_clean_name(name))

    def _news_for(self, name: str) -> str:
        parts = [p for p in name.lower().split() if len(p) > 2]
        for item in self.news:
            text = f"{item.get('headline', '')} {item.get('description', '')}".lower()
            if item.get("player", "").lower() == name.lower():
                return item.get("headline", "")
            if parts and all(p in text for p in parts):
                return item.get("headline", "")
        return ""

    def get(self, name: str, position: str = "") -> PlayerContext:
        adp_entry = lookup_adp(name, self.adp_map)
        adp = adp_entry.adp if adp_entry else None
        pos = position or (adp_entry.position if adp_entry else "")
        sp = self._lookup_sleeper(name)
        inj = self._lookup_injury(name)
        trend = self._trend_idx.get(name.lower(), {})
        sleeper_rank = sp.get("search_rank") if sp else None
        blended = blend_adp(adp, sleeper_rank)

        injury_status = ""
        injury_detail = ""
        penalty = 0.0
        if inj:
            injury_status = inj.get("status", "")
            injury_detail = inj.get("detail") or inj.get("injury") or inj.get("note") or ""
            if isinstance(inj.get("type"), dict):
                injury_detail = injury_detail or inj["type"].get("description", "")
            penalty = INJURY_PENALTIES.get(injury_status.lower(), 8 if injury_status else 0)
        elif sp and sp.get("injury_status"):
            injury_status = sp["injury_status"]
            penalty = INJURY_PENALTIES.get(injury_status.lower(), 10)

        depth = sp.get("depth_chart_order") if sp else None
        role_note = ""
        if depth == 1:
            role_note = "Starter"
        elif depth and depth >= 3:
            role_note = "Depth chart backup"

        rep = self.replacement_levels.get(pos, 150)
        vor = max(0.0, float(rep - (blended or adp or rep)))

        flags: list[str] = []
        if injury_status:
            flags.append(f"Injury: {injury_status}")
        if trend.get("signal"):
            flags.append(trend["signal"])
        if role_note == "Starter":
            flags.append("Starter")
        headline = self._news_for(name)
        if headline:
            flags.append("In news")

        upside_score, upside_note = self._compute_upside(
            sp, age=sp.get("age") if sp else None,
            years_exp=sp.get("years_exp") if sp else None,
            headline=headline, blended=blended, adp=adp,
            depth=depth, trend=trend.get("signal", ""),
        )

        return PlayerContext(
            name=name,
            position=pos,
            adp=adp,
            sleeper_rank=sleeper_rank,
            blended_adp=blended,
            injury_status=injury_status,
            injury_detail=injury_detail,
            injury_penalty=penalty,
            sleeper_injury=sp.get("injury_status", "") if sp else "",
            depth_chart_order=depth,
            trending_signal=trend.get("signal", ""),
            trending_count=trend.get("count", 0),
            news_headline=headline,
            vor=vor,
            role_note=role_note,
            upside_score=upside_score,
            upside_note=upside_note,
            flags=flags,
        )

    def _compute_upside(
        self,
        sp: dict | None,
        age: int | None,
        years_exp: int | None,
        headline: str,
        blended: int | None,
        adp: int | None,
        depth: int | None,
        trend: str,
    ) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []

        text = headline or ""
        if ROLE_UPSIDE_PATTERN.search(text):
            score += 28
            snippet = text[:70] + ("…" if len(text) > 70 else "")
            reasons.append(f"Role news: {snippet}")

        if age and age <= 24:
            score += 14
            reasons.append(f"Age {age} — growth window")
        if years_exp is not None and years_exp <= 2:
            score += 10
            reasons.append("Early-career breakout window")

        if depth == 1 and blended and blended >= 60:
            score += 14
            reasons.append("Starter with room to grow")
        elif depth == 2:
            score += 20
            reasons.append("Backup — one injury from a big role")
        elif depth == 1:
            score += 8
            reasons.append("Listed as team starter")

        if sp and sp.get("search_rank") and adp and sp["search_rank"] < adp - 15:
            score += 16
            reasons.append("Sleeper market rising fast")

        if trend == "Hot add":
            score += 10
            reasons.append("League-mates stashing early")

        if blended and 90 <= blended <= 200 and depth in (1, 2):
            score += 12
            reasons.append("Late-round path to volume")

        return min(100.0, score), "; ".join(reasons[:3])

    def adjust_fit_score(self, name: str, position: str, base_score: float, base_reason: str) -> tuple[float, str]:
        ctx = self.get(name, position)
        score = base_score - ctx.injury_penalty
        reasons = [base_reason] if base_reason else []

        if ctx.vor >= 20:
            score += min(12, ctx.vor / 4)
            reasons.append(f"VOR +{ctx.vor:.0f}")
        if ctx.trending_signal == "Hot add":
            score += 6
            reasons.append("Sleeper trending add")
        elif ctx.trending_signal == "Trending drop":
            score -= 8
            reasons.append("Sleeper trending drop")
        if ctx.depth_chart_order == 1:
            score += 4
        elif ctx.depth_chart_order and ctx.depth_chart_order >= 3:
            score -= 6
            reasons.append("backup role")
        if ctx.news_headline and "injury" in ctx.news_headline.lower():
            score -= 5
        if ctx.upside_score >= 40:
            score += min(10, ctx.upside_score / 5)
            if ctx.upside_note:
                reasons.append(ctx.upside_note.split(";")[0])

        score = min(100.0, max(0.0, score))
        return score, "; ".join(r for r in reasons if r)[:120]

    def flags_text(self, name: str, position: str = "") -> str:
        ctx = self.get(name, position)
        parts = []
        if ctx.injury_status:
            parts.append(f"Injury: {ctx.injury_status}")
        if ctx.trending_signal:
            parts.append(ctx.trending_signal)
        if ctx.role_note and ctx.role_note != "Starter":
            parts.append(ctx.role_note)
        if ctx.news_headline and not ctx.injury_status:
            parts.append("News")
        if ctx.upside_score >= 35:
            parts.append(f"Upside {ctx.upside_score:.0f}")
        return " · ".join(parts)

    def trending_add_targets(self, limit: int = 20) -> list[dict]:
        """Sleeper trending adds resolved to player names."""
        seen: set[str] = set()
        results: list[dict] = []
        for entry in self.trending.get("adds", []):
            pid = str(entry.get("player_id", ""))
            sp = self.sleeper_players.get(pid, {})
            name = sp.get("full_name") or f"{sp.get('first_name', '')} {sp.get('last_name', '')}".strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append({
                "name": name,
                "position": sp.get("position", ""),
                "count": entry.get("count", 0),
            })
        results.sort(key=lambda x: x["count"], reverse=True)
        return results[:limit]

    def grade_adjustments(self, name: str, position: str) -> tuple[float, list[str]]:
        """Return grade bump (negative = downgrade) and extra notes."""
        ctx = self.get(name, position)
        notes: list[str] = []
        delta = 0.0

        if ctx.trending_signal == "Hot add":
            notes.append(f"Sleeper trending add ({ctx.trending_count})")
        elif ctx.trending_signal == "Trending drop":
            delta -= 0.5
            notes.append("Sleeper trending drop")

        if ctx.depth_chart_order == 1:
            notes.append("NFL starter (depth chart)")
        elif ctx.depth_chart_order and ctx.depth_chart_order >= 3:
            delta -= 0.5
            notes.append("Backup on depth chart")

        if ctx.blended_adp and ctx.adp and abs(ctx.blended_adp - ctx.adp) >= 15:
            direction = "above" if ctx.blended_adp < ctx.adp else "below"
            notes.append(f"Sleeper market {direction} 4for4 ADP ({ctx.blended_adp} vs {ctx.adp})")

        if ctx.vor >= 20:
            notes.append(f"High VOR (+{ctx.vor:.0f})")

        if ctx.news_headline and not ctx.injury_status:
            notes.append(f"News: {ctx.news_headline[:80]}")

        return delta, notes


def positional_scarcity(draft: dict | None, pick_no: int | None = None) -> dict[str, float]:
    """How scarce each position is relative to expected draft pace (12-team)."""
    if not draft:
        return {}
    picks = draft.get("picks", [])
    total = pick_no or len(picks) or 1
    expected_pace = total / 4  # rough equal split across QB/RB/WR/TE
    counts: dict[str, int] = {p: 0 for p in CORE_POSITIONS}
    for pick in picks:
        pos = pick.get("position") or pick.get("metadata", {}).get("position", "")
        if pos in counts:
            counts[pos] += 1
    scarcity = {}
    for pos, count in counts.items():
        scarcity[pos] = max(0.0, (count / max(total, 1)) - (1 / len(CORE_POSITIONS))) * 100
    return scarcity
