from __future__ import annotations

import httpx


class EspnNewsClient:
    """Fetch live NFL news and injuries from ESPN public APIs."""

    NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"
    INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=20.0)

    def get_news(self, limit: int = 25) -> list[dict]:
        resp = self._client.get(self.NEWS_URL, params={"limit": limit})
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {
                "headline": a.get("headline", ""),
                "description": a.get("description", ""),
                "published": a.get("published", ""),
                "keywords": [k.get("displayName", "") for k in a.get("categories", [])],
                "link": a.get("links", {}).get("web", {}).get("href", ""),
            }
            for a in articles
        ]

    def get_injuries(self) -> list[dict]:
        resp = self._client.get(self.INJURIES_URL)
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
                })
        return results

    def news_for_player(self, player_name: str, news: list[dict] | None = None) -> str | None:
        news = news or self.get_news(limit=50)
        name_parts = player_name.lower().split()
        for article in news:
            text = f"{article['headline']} {article['description']}".lower()
            keywords = " ".join(article.get("keywords", [])).lower()
            combined = f"{text} {keywords}"
            if all(part in combined for part in name_parts if len(part) > 2):
                return article["headline"]
        return None

    def injury_for_player(self, player_name: str, injuries: list[dict] | None = None) -> dict | None:
        injuries = injuries or self.get_injuries()
        name_lower = player_name.lower()
        for inj in injuries:
            if inj["name"].lower() == name_lower or name_lower in inj["name"].lower():
                return inj
        return None

    def close(self) -> None:
        self._client.close()
