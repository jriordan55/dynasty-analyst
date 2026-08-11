from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

# X accounts
ROTOWIRE_X_HANDLE = "RotoWireNFL"
UNDERDOG_X_HANDLE = "UnderdogNFL"

# Reliable feeds (work from Streamlit Cloud)
ROTOWIRE_NFL_RSS = "https://www.rotowire.com/rss/news.php?sport=NFL"
UNDERDOG_NFL_RSS = "https://underblog.underdogfantasy.com/feed"

# X timeline mirrors (may be blocked on some hosts — used as bonus source)
NITTER_MIRRORS = (
    "https://nitter.net",
    "https://nitter.poast.org",
)

ESPN_NEWS_URLS = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/news",
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
)
ESPN_INJURY_URLS = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
)
ESPN_NOW_NEWS = "https://now.core.api.espn.com/v1/sports/news"

NFL_KEYWORDS = re.compile(
    r"\b(nfl|fantasy football|best ball|draft|week \d|quarterback|"
    r"running back|wide receiver|tight end|training camp|preseason|"
    r"touchdown|injury|questionable|out|doubtful)\b",
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
        try:
            dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
            return dt.isoformat(), dt.timestamp()
        except ValueError:
            return pub_raw, 0.0


def _player_from_headline(headline: str) -> str:
    if ":" in headline:
        candidate = headline.split(":", 1)[0].strip()
        if 2 <= len(candidate.split()) <= 4:
            return candidate
    return ""


def _is_actionable_post(headline: str) -> bool:
    if not headline or len(headline) < 12:
        return False
    if re.match(r"^R to @", headline, re.I):
        return False
    if re.match(r"^RT @", headline, re.I):
        return False
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


def _dedupe_news(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = item["headline"].lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda x: x.get("sort_ts", 0), reverse=True)
    return out


class FantasyNewsClient:
    """Fantasy news from @RotoWireNFL, @UnderdogNFL, and ESPN with cloud-safe fallbacks."""

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

    def _get_rss(self, url: str) -> str | None:
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError:
            return None

    def _fetch_from_urls(
        self,
        urls: list[str],
        source: str,
        x_handle: str | None,
        limit: int,
    ) -> list[dict]:
        all_items: list[dict] = []
        for url in urls:
            text = self._get_rss(url)
            if not text:
                continue
            handle = x_handle if x_handle and "nitter" in url else None
            label = f"@{x_handle}" if handle else source
            all_items.extend(_parse_rss(text, label, handle))
        return _dedupe_news(all_items)[:limit]

    def get_rotowire_news(self, limit: int = 20) -> list[dict]:
        """@RotoWireNFL — official RSS first (cloud-safe), then X mirrors."""
        x_urls = [f"{m}/{ROTOWIRE_X_HANDLE}/rss" for m in NITTER_MIRRORS]
        return self._fetch_from_urls(
            [ROTOWIRE_NFL_RSS, *x_urls],
            "Rotowire",
            ROTOWIRE_X_HANDLE,
            limit,
        )

    def get_underdog_news(self, limit: int = 20) -> list[dict]:
        """@UnderdogNFL — X mirrors then Underblog fallback."""
        x_urls = [f"{m}/{UNDERDOG_X_HANDLE}/rss" for m in NITTER_MIRRORS]
        items = self._fetch_from_urls(
            [*x_urls, UNDERDOG_NFL_RSS],
            "Underdog",
            UNDERDOG_X_HANDLE,
            limit * 2,
        )
        # Blog posts need NFL filter; X posts are already NFL-focused
        filtered = [
            i for i in items
            if i.get("x_handle") or _is_nfl_fantasy(i)
        ]
        return _dedupe_news(filtered)[:limit]

    def get_espn_news(self, limit: int = 25) -> list[dict]:
        """ESPN NFL news — same source as sports-leader MCP get_news."""
        for url in ESPN_NEWS_URLS:
            try:
                resp = self._client.get(url, params={"limit": limit})
                resp.raise_for_status()
                articles = resp.json().get("articles", [])
                if articles:
                    return self._format_espn_site_news(articles)
            except httpx.HTTPError:
                continue

        # MCP-style Now API fallback
        try:
            resp = self._client.get(
                ESPN_NOW_NEWS,
                params={"limit": limit, "sport": "football", "league": "nfl"},
            )
            resp.raise_for_status()
            return self._format_espn_now_news(resp.json())
        except httpx.HTTPError:
            return []

    def _format_espn_site_news(self, articles: list[dict]) -> list[dict]:
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

    def _format_espn_now_news(self, data: dict) -> list[dict]:
        results = []
        for item in data.get("headlines", data.get("articles", [])):
            pub = item.get("published", item.get("lastModified", ""))
            _, sort_ts = _parse_pub_date(pub) if pub else ("", 0.0)
            if not sort_ts and pub:
                try:
                    sort_ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            results.append({
                "source": "ESPN",
                "headline": item.get("headline", item.get("title", "")),
                "description": item.get("description", ""),
                "published": pub,
                "sort_ts": sort_ts,
                "link": item.get("link", item.get("links", {}).get("web", {}).get("href", "")),
                "player": "",
                "keywords": item.get("keywords", []),
                "x_handle": "",
            })
        results.sort(key=lambda x: x.get("sort_ts", 0), reverse=True)
        return results

    def get_news(self, limit: int = 30) -> list[dict]:
        merged: list[dict] = []
        for fetch in (
            self.get_rotowire_news,
            self.get_underdog_news,
            self.get_espn_news,
        ):
            try:
                merged.extend(fetch(limit=limit))
            except Exception:
                continue
        return _dedupe_news(merged)[:limit]

    def get_news_by_source(self) -> dict[str, list[dict]]:
        """Always returns all keys — never raises."""
        result: dict[str, list[dict]] = {
            "rotowire": [],
            "underdog": [],
            "espn": [],
            "injuries": [],
        }
        for key, fetch in [
            ("rotowire", lambda: self.get_rotowire_news(limit=15)),
            ("underdog", lambda: self.get_underdog_news(limit=15)),
            ("espn", lambda: self.get_espn_news(limit=15)),
            ("injuries", lambda: self.get_injuries(limit=20)),
        ]:
            try:
                result[key] = fetch()
            except Exception:
                result[key] = []
        return result

    def get_injuries(self, limit: int = 50) -> list[dict]:
        """ESPN injury report — same data as sports-leader MCP."""
        for url in ESPN_INJURY_URLS:
            try:
                resp = self._client.get(url)
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
                if results:
                    return results[:limit]
            except httpx.HTTPError:
                continue
        return []

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


# Single class — do not use a separate EspnNewsClient (breaks Streamlit deploys)
EspnNewsClient = FantasyNewsClient
