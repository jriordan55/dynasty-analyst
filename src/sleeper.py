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

    def get_user_drafts(self, user_id: str, season: str | None = None, sport: str | None = None) -> list[dict]:
        """User's drafts for a season — includes in-progress mocks not always on league list."""
        if not user_id:
            return []
        league = self.get_league()
        season = season or league.get("season") or "2026"
        sport = sport or league.get("sport") or "nfl"
        try:
            data = self._get(f"/user/{user_id}/drafts/{sport}/{season}")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _collect_draft_candidates(self, my_user_id: str | None) -> list[dict]:
        """Merge league + user draft feeds; user endpoint is often fresher for mocks."""
        by_id: dict[str, dict] = {}
        for d in self.get_drafts() or []:
            did = d.get("draft_id")
            if did:
                by_id[did] = d

        if my_user_id:
            for d in self.get_user_drafts(my_user_id):
                if str(d.get("league_id") or "") != str(self.league_id):
                    continue
                did = d.get("draft_id")
                if not did:
                    continue
                if did in by_id:
                    by_id[did] = merge_draft_records(by_id[did], d)
                else:
                    by_id[did] = d

        league = self.get_league()
        league_draft_id = league.get("draft_id")
        if league_draft_id and league_draft_id not in by_id:
            try:
                by_id[league_draft_id] = self.get_draft(league_draft_id)
            except Exception:
                pass

        return list(by_id.values())

    def get_draft_state(self, my_user_id: str | None = None) -> dict | None:
        """Active league draft (prefers in-progress mock or live draft)."""
        drafts = self._collect_draft_candidates(my_user_id)
        if not drafts:
            return None

        draft_meta = select_active_draft(drafts)
        if not draft_meta:
            return None

        draft_id = draft_meta["draft_id"]
        draft = self.get_draft(draft_id)
        picks = self.get_draft_picks(draft_id)
        users = self.get_users()
        rosters = self.get_rosters()
        players = self.get_all_players()
        user_map = {u["user_id"]: u for u in users}
        roster_to_owner = {r["roster_id"]: r.get("owner_id") for r in rosters}

        slot_by_user: dict[str, int] = {}
        draft_order = draft.get("draft_order") or draft_meta.get("draft_order") or {}
        for uid, slot in draft_order.items():
            slot_by_user[str(uid)] = int(slot)

        enriched_picks = []
        for pick in picks:
            meta = pick.get("metadata") or {}
            name = meta.get("full_name") or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
            if not name and pick.get("player_id"):
                player_row = players.get(str(pick["player_id"]), {})
                name = player_row.get("full_name") or (
                    f"{player_row.get('first_name', '')} {player_row.get('last_name', '')}".strip()
                )
            owner_id = pick.get("picked_by") or roster_to_owner.get(pick.get("roster_id"))
            owner = user_map.get(owner_id or "", {})
            enriched_picks.append({
                **pick,
                "player_name": name,
                "manager": owner.get("display_name") or owner.get("username", "Unknown"),
                "position": meta.get("position") or (
                    players.get(str(pick.get("player_id") or ""), {}).get("position", "")
                ),
            })

        total_rosters = draft.get("settings", {}).get("teams") or len(slot_by_user) or 12
        rounds = draft.get("settings", {}).get("rounds") or 16
        total_picks = total_rosters * rounds
        completed = len({p["pick_no"] for p in picks if p.get("pick_no") and p.get("player_id")})

        status = (draft.get("status") or draft_meta.get("status") or "pre_draft").lower()
        draft_stub = {
            "status": status,
            "last_picked": draft.get("last_picked") or draft_meta.get("last_picked"),
            "teams": total_rosters,
            "rounds": rounds,
            "picks": enriched_picks,
        }
        from src.draft import effective_draft_status, is_draft_active

        effective_status = effective_draft_status(draft_stub)
        my_slot = slot_by_user.get(str(my_user_id or "")) or slot_by_user.get(my_user_id or "", None)
        on_clock = _pick_on_clock(
            enriched_picks, slot_by_user, user_map, total_rosters,
            draft_status=effective_status,
            rounds=rounds,
        )
        if on_clock and my_user_id:
            on_clock["is_mine"] = str(on_clock.get("user_id")) == str(my_user_id)

        label, is_mock = draft_display_info(draft_meta, draft)

        return {
            "draft_id": draft_id,
            "status": effective_status,
            "api_status": status,
            "last_picked": draft.get("last_picked") or draft_meta.get("last_picked"),
            "is_active": is_draft_active(draft_stub),
            "type": draft.get("type") or draft_meta.get("type"),
            "draft_order": slot_by_user,
            "slot_to_roster_id": draft.get("slot_to_roster_id") or {},
            "teams": total_rosters,
            "rounds": rounds,
            "my_slot": my_slot,
            "my_user_id": my_user_id,
            "picks": enriched_picks,
            "total_picks": total_picks,
            "completed_picks": completed,
            "on_clock": on_clock,
            "user_map": user_map,
            "draft_label": label,
            "is_mock": is_mock,
            "metadata": draft.get("metadata") or draft_meta.get("metadata") or {},
            "available_drafts": [
                {
                    "draft_id": d.get("draft_id"),
                    "status": d.get("status"),
                    "label": draft_display_info(d, d)[0],
                }
                for d in drafts
            ],
            "sync_source": "user+league" if my_user_id else "league",
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
                    "depth_chart_position": p.get("depth_chart_position"),
                    "years_exp": p.get("years_exp"),
                    "is_starter": pid in starters,
                    "is_taxi": pid in taxi,
                    "is_ir": pid in reserve,
                })

            settings = roster.get("settings") or {}
            teams.append({
                "roster_id": roster["roster_id"],
                "owner_id": roster.get("owner_id"),
                "owner_name": owner.get("display_name") or owner.get("username", "Unknown"),
                "team_name": team_name,
                "wins": settings.get("wins", 0),
                "losses": settings.get("losses", 0),
                "fpts": settings.get("fpts", 0),
                "fpts_against": settings.get("fpts_against", 0),
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


def merge_draft_records(a: dict, b: dict) -> dict:
    """Combine draft list entries — prefer the more active status."""
    status_rank = {"drafting": 0, "paused": 1, "pre_draft": 2, "complete": 3}
    sa = status_rank.get((a.get("status") or "pre_draft").lower(), 9)
    sb = status_rank.get((b.get("status") or "pre_draft").lower(), 9)
    primary, secondary = (a, b) if sa <= sb else (b, a)
    return {**secondary, **primary, "status": primary.get("status") or secondary.get("status")}


def select_active_draft(drafts: list[dict]) -> dict | None:
    """Pick the draft board to sync — active mock/live first, then upcoming league draft."""
    if not drafts:
        return None

    status_rank = {"drafting": 0, "paused": 1, "pre_draft": 2, "complete": 3}

    def activity_score(d: dict) -> int:
        lp = d.get("last_picked") or 0
        age_min = (time.time() * 1000 - lp) / 60_000 if lp else 999_999
        if age_min <= 90:
            return 3
        if lp:
            return 1
        return 0

    def sort_key(d: dict) -> tuple:
        status = (d.get("status") or "pre_draft").lower()
        rank = status_rank.get(status, 9)
        ts = d.get("start_time") or d.get("last_picked") or d.get("created") or 0
        return (rank, -activity_score(d), -int(ts))

    return sorted(drafts, key=sort_key)[0]


def draft_display_info(draft_meta: dict, draft_full: dict | None = None) -> tuple[str, bool]:
    """Human label and mock flag for UI."""
    meta = (draft_full or {}).get("metadata") or draft_meta.get("metadata") or {}
    name = (meta.get("name") or "").lower()
    desc = (meta.get("description") or "").lower()
    meta_type = (meta.get("type") or "").lower()
    is_mock = "mock" in name or "mock" in desc or meta_type == "mock"

    status = ((draft_full or draft_meta).get("status") or "pre_draft").lower()
    if status == "drafting":
        return ("Mock draft" if is_mock else "Live draft"), is_mock
    if status == "complete":
        return ("Mock draft (done)" if is_mock else "Draft complete"), is_mock
    if is_mock:
        return "Mock draft (scheduled)", True
    return "League draft", False


def _pick_on_clock(
    picks: list[dict],
    slot_by_user: dict[str, int],
    user_map: dict[str, dict],
    teams: int,
    draft_status: str | None = None,
    rounds: int = 16,
) -> dict | None:
    """Determine who is on the clock for snake drafts."""
    if not slot_by_user:
        return None
    if (draft_status or "").lower() in ("complete", "complete_mock"):
        return None

    from src.draft import current_draft_pick

    draft_stub = {
        "status": draft_status,
        "teams": teams,
        "rounds": rounds,
        "picks": picks,
    }
    pick_no = current_draft_pick(draft_stub, teams)
    round_no = (pick_no - 1) // teams + 1
    pos_in_round = (pick_no - 1) % teams
    slot = pos_in_round + 1 if round_no % 2 == 1 else teams - pos_in_round

    user_id = next((uid for uid, s in slot_by_user.items() if s == slot), None)
    if not user_id:
        return {"pick_no": pick_no, "round": round_no, "slot": slot, "is_mine": False}

    owner = user_map.get(user_id, {})
    return {
        "pick_no": pick_no,
        "round": round_no,
        "slot": slot,
        "user_id": user_id,
        "manager": owner.get("display_name") or owner.get("username", "Unknown"),
    }
