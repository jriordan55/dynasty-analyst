from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

# X / Twitter accounts (primary news sources)
ROTOWIRE_X_HANDLE = "RotoWireNFL"
UNDERDOG_X_HANDLE = "UnderdogNFL"
ROTOWIRE_X_URL = f"https://x.com/{ROTOWIRE_X_HANDLE}"
UNDERDOG_X_URL = f"https://x.com/{UNDERDOG_X_HANDLE}"

# Nitter RSS mirrors for X timelines (no API key required)
ROTOWIRE_X_RSS = f"https://nitter.net/{ROTOWIRE_X_HANDLE}/rss"
UNDERDOG_X_RSS = f"https://nitter.net/{UNDERDOG_X_HANDLE}/rss"

# Fallback feeds if X mirror is unavailable
ROTOWIRE_NFL_RSS = "https://www.rotowire.com/rss/news.php?sport=NFL"
UNDERDOG_NFL_RSS = "https://underblog.underdogfantasy.com/feed"

NFL_KEYWORDS = re.compile(
    r"\b(nfl|fantasy football|best ball|draft guide|week \d|quarterback|"
    r"running back|wide receiver|tight end|wr1|rb1|te1|adp|keeper|dynasty|"
    r"training camp|preseason|playoff|super bowl|touchdown|rushing|receiving)\b",
    re.I,
)

_DC = "{http://purl.org/dc/elements/1.1/}"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _to_x_link(link: str, handle: str) -> str:
    match = re.search(r"/status/(\d+)", link)
    if match:
        return f"https://x.com/{handle}/status/{match.group(1)}"
    return f"https://x.com/{handle}"


def _parse_pub_date(pub_raw: str) -> tuple[str, float]:
    if not pub_raw:
        return "", 0.0
    try:
        dt = parsedate_to_datetime(pub_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), dt.timestamp()
    except (ValueError, TypeError):
        return pub_raw, 0.0


def _player_from_headline(headline: str) -> str:
    if ":" in headline:
        candidate = headline.split(":", 1)[0].strip()
        if 2 <= len(candidate.split()) <= 4:
            return candidate
    return ""


def _is_actionable_post(headline: str) -> bool:
    """Skip replies, retweets, and link-only noise from X timelines."""
    if not headline or len(headline) < 12:
        return False
    if re.match(r"^R to @", headline, re.I):
        return False
    if re.match(r"^RT @", headline, re.I):
        return False
    if headline.startswith("@") and ":" not in headline:
        return False
    # Skip truncated link-only replies
    if "rotowire.com/football/player" in headline and len(headline) < 60:
        return False
    return True


def _parse_rss(xml_text: str, source: str, x_handle: str | None = None) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item"):
        title = _strip_html(item.findtext("title") or "")
        raw_link = (item.findtext("link") or "").strip()
        description = _strip_html(item.findtext("description") or "")
        pub_raw = item.findtext("pubDate") or item.findtext(f"{_DC}date") or ""
        published, sort_ts = _parse_pub_date(pub_raw)

        link = _to_x_link(raw_link, x_handle) if x_handle else raw_link
        headline = title or description
        player = _player_from_headline(headline)

        items.append({
            "source": source,
            "headline": headline,
            "description": description if description != headline else "",
            "published": published,
            "sort_ts": sort_ts,
            "link": link,
            "player": player,
            "keywords": [],
            "x_handle": x_handle or "",
        })

    if x_handle:
        items = [i for i in items if _is_actionable_post(i["headline"])]
    return items


def _is_nfl_fantasy(item: dict) -> bool:
    text = f"{item['headline']} {item['description']}"
    return bool(NFL_KEYWORDS.search(text))


class FantasyNewsClient:
    """Aggregate fantasy news from @RotoWireNFL, @UnderdogNFL, and ESPN."""

    ESPN_NEWS_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/news"
    ESPN_INJURIES_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=25.0,
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

    def _fetch_rss_with_fallback(
        self,
        primary_url: str,
        fallback_url: str,
        source: str,
        x_handle: str,
        limit: int,
    ) -> list[dict]:
        for url in (primary_url, fallback_url):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                handle = x_handle if url == primary_url else None
                label = f"@{x_handle}" if handle else source
                items = _parse_rss(resp.text, label, handle)
                if items:
                    items.sort(key=lambda x: x["sort_ts"], reverse=True)
                    return items[:limit]
            except httpx.HTTPError:
                continue
        return []

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
                "x_handle": "",
            })
        return results

    def get_rotowire_news(self, limit: int = 20) -> list[dict]:
        """Live posts from @RotoWireNFL on X."""
        return self._fetch_rss_with_fallback(
            ROTOWIRE_X_RSS, ROTOWIRE_NFL_RSS, "Rotowire", ROTOWIRE_X_HANDLE, limit
        )

    def get_underdog_news(self, limit: int = 20) -> list[dict]:
        """Live posts from @UnderdogNFL on X."""
        items = self._fetch_rss_with_fallback(
            UNDERDOG_X_RSS, UNDERDOG_NFL_RSS, "Underdog", UNDERDOG_X_HANDLE, limit
        )
        # Blog fallback may include non-NFL posts
        if items and not items[0].get("x_handle"):
            items = [i for i in items if _is_nfl_fantasy(i)]
        return items[:limit]

    def get_news(self, limit: int = 30) -> list[dict]:
        merged: list[dict] = []
        for fetch in (
            lambda: self.get_rotowire_news(limit=limit),
            lambda: self.get_underdog_news(limit=limit),
            lambda: self.get_espn_news(limit=limit),
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
            ("rotowire", lambda: self.get_rotowire_news(limit=20)),
            ("underdog", lambda: self.get_underdog_news(limit=20)),
            ("espn", lambda: self.get_espn_news(limit=15)),
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


EspnNewsClient = FantasyNewsClient
