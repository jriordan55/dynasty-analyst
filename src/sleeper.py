from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
PLAYERS_CACHE = CACHE_DIR / "sleeper_players.json"
PLAYERS_TTL = 86400  # 24 hours


class SleeperClient:
    BASE = "https://api.sleeper.app/v1"

    def __init__(self, league_id: str, cache_dir: Path | None = None):
        self.league_id = league_id
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(timeout=30.0)

    def _get(self, path: str) -> dict | list:
        resp = self._client.get(f"{self.BASE}{path}")
        resp.raise_for_status()
        return resp.json()

    def get_league(self) -> dict:
        return self._get(f"/league/{self.league_id}")

    def get_rosters(self) -> list[dict]:
        return self._get(f"/league/{self.league_id}/rosters")

    def get_users(self) -> list[dict]:
        return self._get(f"/league/{self.league_id}/users")

    def get_drafts(self) -> list[dict]:
        return self._get(f"/league/{self.league_id}/drafts")

    def get_draft(self, draft_id: str) -> dict:
        return self._get(f"/draft/{draft_id}")

    def get_draft_picks(self, draft_id: str) -> list[dict]:
        return self._get(f"/draft/{draft_id}/picks")

    def get_transactions(self, week: int | None = None) -> list[dict]:
        if week is None:
            state = self._get("/state/nfl")
            week = state.get("week", 1)
        return self._get(f"/league/{self.league_id}/transactions/{week}")

    def get_traded_picks(self) -> list[dict]:
        return self._get(f"/league/{self.league_id}/traded_picks")

    def get_league_chain(self, max_seasons: int = 4) -> list[dict]:
        """Walk previous_league_id to collect recent seasons."""
        chain: list[dict] = []
        current_id: str | None = self.league_id
        seen: set[str] = set()
        while current_id and current_id not in seen and len(chain) < max_seasons:
            seen.add(current_id)
            league = self.get_league_by_id(current_id)
            chain.append(league)
            current_id = league.get("previous_league_id")
        return chain

    def get_league_by_id(self, league_id: str) -> dict:
        return self._get(f"/league/{league_id}")

    def get_all_transactions(self, max_week: int = 18) -> list[dict]:
        """Completed trades and adds across all weeks."""
        all_txns: list[dict] = []
        seen_ids: set[str] = set()
        for week in range(1, max_week + 1):
            try:
                txns = self.get_transactions(week)
            except Exception:
                continue
            for txn in txns:
                tid = txn.get("transaction_id")
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                all_txns.append({**txn, "week": week})
        return all_txns

    def get_historical_draft_picks(self, max_seasons: int = 3) -> list[dict]:
        """Draft picks from current + previous league seasons."""
        history: list[dict] = []
        for league in self.get_league_chain(max_seasons):
            lid = league["league_id"]
            try:
                drafts = self._get(f"/league/{lid}/drafts")
            except Exception:
                continue
            for draft_meta in drafts or []:
                draft_id = draft_meta.get("draft_id")
                if not draft_id:
                    continue
                try:
                    picks = self.get_draft_picks(draft_id)
                except Exception:
                    continue
                history.append({
                    "league_id": lid,
                    "season": league.get("season"),
                    "draft_id": draft_id,
                    "picks": picks,
                })
        return history

    def get_trade_history_bundle(self, max_seasons: int = 3) -> dict:
        """Transactions + draft history + pick ownership for trade intel."""
        chain = self.get_league_chain(max_seasons)
        trades: list[dict] = []
        seen: set[str] = set()
        for league in chain:
            lid = league["league_id"]
            for week in range(1, 19):
                try:
                    txns = self._get(f"/league/{lid}/transactions/{week}")
                except Exception:
                    continue
                for txn in txns:
                    if txn.get("type") != "trade" or txn.get("status") != "complete":
                        continue
                    tid = txn.get("transaction_id")
                    if tid and tid in seen:
                        continue
                    if tid:
                        seen.add(tid)
                    trades.append({**txn, "source_league_id": lid, "week": week})
        try:
            traded_picks = self.get_traded_picks()
        except Exception:
            traded_picks = []
        return {
            "league_chain": chain,
            "trades": trades,
            "draft_history": self.get_historical_draft_picks(max_seasons),
            "traded_picks": traded_picks,
        }

    def get_trending_players(self, lookback_hours: int = 24, limit: int = 25) -> dict:
        adds = self._client.get(
            f"{self.BASE}/players/nfl/trending/add",
            params={"lookback_hours": lookback_hours, "limit": limit},
        ).json()
        drops = self._client.get(
            f"{self.BASE}/players/nfl/trending/drop",
            params={"lookback_hours": lookback_hours, "limit": limit},
        ).json()
        return {"adds": adds, "drops": drops}

    def get_all_players(self, force_refresh: bool = False) -> dict[str, dict]:
        cache_path = self.cache_dir / "sleeper_players.json"
        if not force_refresh and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < PLAYERS_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        players = self._get("/players/nfl")
        cache_path.write_text(json.dumps(players), encoding="utf-8")
        return players

    def resolve_user(self, username: str | None = None, user_id: str | None = None) -> dict | None:
        users = self.get_users()
        if user_id:
            return next((u for u in users if u["user_id"] == user_id), None)
        if username:
            uname = username.lower()
            return next(
                (u for u in users if u.get("display_name", "").lower() == uname
                 or u.get("username", "").lower() == uname
                 or u.get("metadata", {}).get("team_name", "").lower() == uname),
                None,
            )
        return None

    def get_draft_state(self, my_user_id: str | None = None) -> dict | None:
        """Latest league draft with picks and slot mapping."""
        drafts = self.get_drafts()
        if not drafts:
            return None

        draft_meta = drafts[0]
        draft_id = draft_meta["draft_id"]
        draft = self.get_draft(draft_id)
        picks = self.get_draft_picks(draft_id)
        users = self.get_users()
        user_map = {u["user_id"]: u for u in users}

        slot_by_user: dict[str, int] = {}
        for uid, slot in (draft.get("draft_order") or draft_meta.get("draft_order") or {}).items():
            slot_by_user[uid] = int(slot)

        enriched_picks = []
        for pick in picks:
            meta = pick.get("metadata") or {}
            name = meta.get("full_name") or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
            owner = user_map.get(pick.get("picked_by", ""), {})
            enriched_picks.append({
                **pick,
                "player_name": name,
                "manager": owner.get("display_name") or owner.get("username", "Unknown"),
                "position": meta.get("position", ""),
            })

        total_rosters = draft.get("settings", {}).get("teams") or len(slot_by_user) or 12
        rounds = draft.get("settings", {}).get("rounds") or 16
        total_picks = total_rosters * rounds
        completed = len([p for p in picks if p.get("player_id")])

        my_slot = slot_by_user.get(my_user_id or "", None)
        on_clock = _pick_on_clock(picks, slot_by_user, user_map, total_rosters)

        return {
            "draft_id": draft_id,
            "status": draft.get("status") or draft_meta.get("status"),
            "type": draft.get("type") or draft_meta.get("type"),
            "draft_order": slot_by_user,
            "teams": total_rosters,
            "rounds": rounds,
            "my_slot": my_slot,
            "my_user_id": my_user_id,
            "picks": enriched_picks,
            "total_picks": total_picks,
            "completed_picks": completed,
            "on_clock": on_clock,
            "user_map": user_map,
        }

    def get_league_snapshot(self, my_user_id: str | None = None) -> dict:
        """Full league state for analysis."""
        league = self.get_league()
        rosters = self.get_rosters()
        users = self.get_users()
        players = self.get_all_players()
        trending = self.get_trending_players()
        draft_state = self.get_draft_state(my_user_id)

        user_map = {u["user_id"]: u for u in users}

        teams = []
        for roster in rosters:
            owner = user_map.get(roster.get("owner_id", ""), {})
            team_name = owner.get("metadata", {}).get("team_name") or owner.get("display_name", "Unknown")
            player_ids = roster.get("players") or []
            starters = set(roster.get("starters") or [])
            taxi = set(roster.get("taxi") or [])
            reserve = set(roster.get("reserve") or [])

            roster_players = []
            for pid in player_ids:
                p = players.get(pid, {})
                if not p:
                    continue
                pos = p.get("position", "")
                if pos in ("OL", "DL", "LB", "CB", "S", "K", "DEF"):
                    if pos not in ("K", "DEF"):
                        continue
                roster_players.append({
                    "id": pid,
                    "name": p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
                    "position": pos,
                    "team": p.get("team") or "",
                    "age": p.get("age"),
                    "injury_status": p.get("injury_status"),
                    "search_rank": p.get("search_rank"),
                    "depth_chart_order": p.get("depth_chart_order"),
                    "years_exp": p.get("years_exp"),
                    "is_starter": pid in starters,
                    "is_taxi": pid in taxi,
                    "is_ir": pid in reserve,
                })

            teams.append({
                "roster_id": roster["roster_id"],
                "owner_id": roster.get("owner_id"),
                "owner_name": owner.get("display_name") or owner.get("username", "Unknown"),
                "team_name": team_name,
                "wins": roster.get("settings", {}).get("wins", 0),
                "losses": roster.get("settings", {}).get("losses", 0),
                "players": roster_players,
                "draft_picks": roster.get("draft_picks") or [],
                "is_mine": roster.get("owner_id") == my_user_id,
            })

        trade_history = self.get_trade_history_bundle(max_seasons=3)

        return {
            "league": league,
            "teams": teams,
            "trending": trending,
            "my_user_id": my_user_id,
            "draft": draft_state,
            "trade_history": trade_history,
        }

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SleeperClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _pick_on_clock(
    picks: list[dict],
    slot_by_user: dict[str, int],
    user_map: dict[str, dict],
    teams: int,
) -> dict | None:
    """Determine who is on the clock for snake drafts."""
    if not slot_by_user:
        return None

    pick_no = len(picks) + 1
    round_no = (pick_no - 1) // teams + 1
    pos_in_round = (pick_no - 1) % teams
    slot = pos_in_round + 1 if round_no % 2 == 1 else teams - pos_in_round

    user_id = next((uid for uid, s in slot_by_user.items() if s == slot), None)
    if not user_id:
        return {"pick_no": pick_no, "round": round_no, "slot": slot}

    owner = user_map.get(user_id, {})
    return {
        "pick_no": pick_no,
        "round": round_no,
        "slot": slot,
        "user_id": user_id,
        "manager": owner.get("display_name") or owner.get("username", "Unknown"),
    }
