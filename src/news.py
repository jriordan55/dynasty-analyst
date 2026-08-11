from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

# Public RSS feeds — no API key required
ROTOWIRE_NFL_RSS = "https://www.rotowire.com/rss/news.php?sport=NFL"
UNDERDOG_NFL_RSS = "https://underblog.underdogfantasy.com/feed"

NFL_KEYWORDS = re.compile(
    r"\b(nfl|fantasy football|best ball|draft guide|week \d|quarterback|"
    r"running back|wide receiver|tight end|wr1|rb1|te1|adp|keeper|dynasty|"
    r"training camp|preseason|playoff|super bowl|touchdown|rushing|receiving)\b",
    re.I,
)


def _parse_rss(xml_text: str, source: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_raw = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
        published = pub_raw
        sort_ts = 0.0
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                sort_ts = dt.timestamp()
                published = dt.isoformat()
            except (ValueError, TypeError):
                pass

        # Rotowire titles often "Player Name: headline"
        player = ""
        if source == "Rotowire" and ":" in title:
            player = title.split(":", 1)[0].strip()

        items.append({
            "source": source,
            "headline": title,
            "description": description,
            "published": published,
            "sort_ts": sort_ts,
            "link": link,
            "player": player,
            "keywords": [],
        })
    return items


def _is_nfl_fantasy(item: dict) -> bool:
    text = f"{item['headline']} {item['description']}"
    return bool(NFL_KEYWORDS.search(text))


class FantasyNewsClient:
    """Aggregate fantasy news from ESPN, Rotowire, and Underdog NFL."""

    ESPN_NEWS_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/news"
    ESPN_INJURIES_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=20.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/xml,application/xml,*/*",
                "Referer": "https://www.espn.com/",
            },
            follow_redirects=True,
        )

    def get_espn_news(self, limit: int = 25) -> list[dict]:
        resp = self._client.get(self.ESPN_NEWS_URL, params={"limit": limit})
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        results = []
        for a in articles:
            pub = a.get("published", "")
            sort_ts = 0.0
            if pub:
                try:
                    sort_ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            results.append({
                "source": "ESPN",
                "headline": a.get("headline", ""),
                "description": a.get("description", ""),
                "published": pub,
                "sort_ts": sort_ts,
                "link": a.get("links", {}).get("web", {}).get("href", ""),
                "player": "",
                "keywords": [k.get("displayName", "") for k in a.get("categories", [])],
            })
        return results

    def get_rotowire_news(self, limit: int = 30) -> list[dict]:
        resp = self._client.get(ROTOWIRE_NFL_RSS)
        resp.raise_for_status()
        items = _parse_rss(resp.text, "Rotowire")
        items.sort(key=lambda x: x["sort_ts"], reverse=True)
        return items[:limit]

    def get_underdog_news(self, limit: int = 20, nfl_only: bool = True) -> list[dict]:
        resp = self._client.get(UNDERDOG_NFL_RSS)
        resp.raise_for_status()
        items = _parse_rss(resp.text, "Underdog")
        if nfl_only:
            items = [i for i in items if _is_nfl_fantasy(i)]
        items.sort(key=lambda x: x["sort_ts"], reverse=True)
        return items[:limit]

    def get_news(self, limit: int = 30) -> list[dict]:
        """Merged feed from ESPN + Rotowire + Underdog, newest first."""
        merged: list[dict] = []
        for fetch in (
            lambda: self.get_espn_news(limit=limit),
            lambda: self.get_rotowire_news(limit=limit),
            lambda: self.get_underdog_news(limit=limit),
        ):
            try:
                merged.extend(fetch())
            except httpx.HTTPError:
                continue
        merged.sort(key=lambda x: x.get("sort_ts", 0), reverse=True)
        return merged[:limit]

    def get_news_by_source(self) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for key, fetch in [
            ("espn", lambda: self.get_espn_news(limit=15)),
            ("rotowire", lambda: self.get_rotowire_news(limit=20)),
            ("underdog", lambda: self.get_underdog_news(limit=15)),
        ]:
            try:
                result[key] = fetch()
            except httpx.HTTPError:
                result[key] = []
        return result

    def get_injuries(self) -> list[dict]:
        resp = self._client.get(self.ESPN_INJURIES_URL)
        resp.raise_for_status()
        results = []
        for team_entry in resp.json().get("injuries", []):
            team = team_entry.get("displayName", "")
            for item in team_entry.get("injuries", []):
                athlete = item.get("athlete", {})
                results.append({
                    "name": athlete.get("displayName", ""),
                    "team": team,
                    "position": athlete.get("position", {}).get("abbreviation", ""),
                    "status": item.get("status", ""),
                    "detail": item.get("type", {}).get("description", ""),
                    "date": item.get("date", ""),
                    "source": "ESPN",
                })
        return results

    def news_for_player(self, player_name: str, news: list[dict] | None = None) -> str | None:
        news = news or self.get_news(limit=80)
        name_parts = [p for p in player_name.lower().split() if len(p) > 2]
        if not name_parts:
            return None

        for article in news:
            text = f"{article['headline']} {article['description']} {' '.join(article.get('keywords', []))}".lower()
            if article.get("player") and article["player"].lower() == player_name.lower():
                return f"[{article['source']}] {article['headline']}"
            if all(part in text for part in name_parts):
                return f"[{article['source']}] {article['headline']}"
        return None

    def player_news(self, player_name: str, limit: int = 5) -> list[dict]:
        """All recent news mentioning a player across sources."""
        news = self.get_news(limit=100)
        name_parts = [p for p in player_name.lower().split() if len(p) > 2]
        hits = []
        for article in news:
            text = f"{article['headline']} {article['description']}".lower()
            if article.get("player") and article["player"].lower() == player_name.lower():
                hits.append(article)
            elif name_parts and all(p in text for p in name_parts):
                hits.append(article)
        return hits[:limit]

    def close(self) -> None:
        self._client.close()


# Backward-compatible alias
EspnNewsClient = FantasyNewsClient
