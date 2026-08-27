from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.adp import load_adp, parse_adp_markdown, save_adp_json
from src.analysis import (
    analyze_team_needs,
    find_sell_candidates,
    find_trade_matches,
    find_waiver_targets,
    grade_roster,
)
from src.market_insights import MarketInsightsClient
from src.fantasypros import FantasyProsClient
from src.trade_analysis import analyze_league_trades, proposals_to_legacy_matches
from src.draft import (
    build_draft_board,
    build_keeper_plan,
    build_manager_profiles,
    build_roster_draft_plan,
    build_upside_targets,
    format_pick_label,
    league_has_keepers,
    recommend_for_my_slot,
    recommend_picks,
    sync_keepers_from_draft,
)
from src.news import FantasyNewsClient, get_news_client
from src.player_intel import PlayerIntel
from src.sleeper import SleeperClient

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "league.json"


def load_config() -> dict:
    load_dotenv(ROOT / ".env")
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        example = ROOT / "config" / "league.example.json"
        config = json.loads(example.read_text(encoding="utf-8"))

    config["league_id"] = config.get("league_id") or os.getenv("SLEEPER_LEAGUE_ID", "")
    config["username"] = config.get("username") or os.getenv("SLEEPER_USERNAME", "")
    config["fantasypros_api_key"] = config.get("fantasypros_api_key") or os.getenv("FANTASYPROS_API_KEY", "")
    return config


def refresh_adp(source_path: Path | None = None) -> int:
    source = source_path or ROOT / "data" / "adp-source.md"
    if not source.exists():
        uploads = Path(__file__).resolve().parents[2]
        alt = uploads / "uploads" / "adp-0.md"
        if alt.exists():
            source = alt
        else:
            cursor_upload = Path.home() / ".cursor" / "projects" / "c-Users-student-Documents-fantasy-football" / "uploads" / "adp-0.md"
            if cursor_upload.exists():
                source = cursor_upload

    text = source.read_text(encoding="utf-8")
    players = parse_adp_markdown(text)
    out = ROOT / "data" / "adp.json"
    save_adp_json(players, out)
    return len(players)


class DynastyAnalyst:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.adp_map = load_adp()
        self.news = get_news_client()
        self._snapshot: dict | None = None
        self._my_team: dict | None = None
        self._intel: PlayerIntel | None = None

    def intel(self) -> PlayerIntel:
        if self._intel is None:
            self._intel = PlayerIntel.from_snapshot(self._ensure_snapshot(), self.news)
            self.adp_map = self._intel.adp_map
        return self._intel

    def sync(self, owner_id: str | None = None) -> dict:
        league_id = self.config["league_id"]
        if not league_id or league_id == "YOUR_LEAGUE_ID":
            raise ValueError(
                "Set your Sleeper league ID in config/league.json or SLEEPER_LEAGUE_ID in .env"
            )

        with SleeperClient(league_id) as sleeper:
            user = sleeper.resolve_user(username=self.config.get("username"))
            my_id = owner_id or (user["user_id"] if user else None)
            snapshot = sleeper.get_league_snapshot(my_user_id=my_id)

        cache_path = ROOT / "data" / "cache" / "league_snapshot.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

        self._snapshot = snapshot
        self._my_team = next((t for t in snapshot["teams"] if t.get("is_mine")), None)
        max_k = (snapshot.get("league") or {}).get("settings", {}).get("max_keepers")
        if max_k is not None:
            self.config["max_keepers"] = int(max_k)
            if int(max_k) == 0:
                self.config["keepers"] = []
        return snapshot

    def _ensure_snapshot(self) -> dict:
        if self._snapshot is None:
            cache = ROOT / "data" / "cache" / "league_snapshot.json"
            if cache.exists():
                self._snapshot = json.loads(cache.read_text(encoding="utf-8"))
                self._my_team = next(
                    (t for t in self._snapshot["teams"] if t.get("is_mine")), None
                )
            else:
                self.sync()
        assert self._snapshot is not None
        return self._snapshot

    def _ensure_loaded(self) -> tuple[dict, dict]:
        snapshot = self._ensure_snapshot()
        if self._my_team is None:
            self._my_team = next(
                (t for t in snapshot["teams"] if t.get("is_mine")), None
            )
        if self._my_team is None:
            raise ValueError(
                "Could not find your team. Run: python -m src.cli set-team YOUR_USERNAME"
            )
        return snapshot, self._my_team

    def league_overview(self) -> dict:
        snapshot = self._ensure_snapshot()
        all_needs = [
            analyze_team_needs(t, self.config) for t in snapshot["teams"]
        ]
        my_team = self._my_team or next(
            (t for t in snapshot["teams"] if t.get("is_mine")), None
        )
        my_needs = None
        if my_team:
            my_needs = next(n for n in all_needs if n.owner_id == my_team.get("owner_id"))

        return {
            "my_team": my_team["team_name"] if my_team else None,
            "record": f"{my_team.get('wins', 0)}-{my_team.get('losses', 0)}" if my_team else None,
            "my_needs": my_needs,
            "all_teams": [
                {
                    "manager": n.owner_name,
                    "team": n.team_name,
                    "counts": n.position_counts,
                    "desperate_for": n.desperate_for,
                    "overloaded_at": n.overloaded_at,
                }
                for n in all_needs
            ],
        }

    def grade_my_roster(self) -> list[dict]:
        _, my_team = self._ensure_loaded()
        return grade_roster(my_team, self.adp_map, self.news, self.intel())

    def sell_candidates(self) -> list:
        _, my_team = self._ensure_loaded()
        return find_sell_candidates(my_team, self.adp_map, self.config, self.intel())

    def _market_clients(self):
        snapshot = self._ensure_snapshot()
        cfg = {**self.config, "league": snapshot.get("league") or {}}
        fp_key = self.config.get("fantasypros_api_key") or os.getenv("FANTASYPROS_API_KEY", "")
        fp = FantasyProsClient(api_key=fp_key, config=cfg) if fp_key else None
        market = MarketInsightsClient(cfg, fp_client=fp)
        market.load()
        return market.fc, market

    def has_keepers(self) -> bool:
        return league_has_keepers(self.config, self._ensure_snapshot())

    def draft_plan(self, keeper_names: list[str] | None = None):
        _, my_team = self._ensure_loaded()
        if not self.has_keepers():
            return build_roster_draft_plan(my_team, self.config)
        names = keeper_names if keeper_names is not None else self.get_keepers()
        return build_keeper_plan(my_team, names, self.adp_map, self.config, self.draft_state())

    def _trade_analysis(self):
        snapshot, my_team = self._ensure_loaded()
        keepers = self.get_keepers() if self.has_keepers() else []
        cfg = {**self.config, "keepers": keepers, "league": snapshot.get("league") or {}}
        plan = self.draft_plan(keepers if keepers else None)
        fc, market = self._market_clients()
        return analyze_league_trades(
            snapshot, my_team, cfg, self.intel(), keeper_plan=plan,
            fc_client=fc, market_client=market,
        )

    def trade_targets(self) -> list:
        _, proposals, _ = self._trade_analysis()
        if proposals:
            return proposals_to_legacy_matches(proposals)
        snapshot, my_team = self._ensure_loaded()
        all_needs = [analyze_team_needs(t, self.config) for t in snapshot["teams"]]
        my_needs = next(n for n in all_needs if n.owner_id == my_team.get("owner_id"))
        return find_trade_matches(my_needs, all_needs, self.intel().adp_map, my_team)

    def trade_proposals(self) -> list:
        _, proposals, _ = self._trade_analysis()
        return proposals

    def team_trade_profiles(self) -> list:
        profiles, _, _ = self._trade_analysis()
        return profiles

    def manager_tendencies(self) -> dict:
        snapshot = self._ensure_snapshot()
        from src.trade_analysis import build_manager_tendencies
        return build_manager_tendencies(snapshot, self.intel())

    def waiver_targets(self) -> list:
        snapshot, my_team = self._ensure_loaded()
        my_needs = analyze_team_needs(my_team, self.config)
        return find_waiver_targets(
            snapshot, my_team, self.adp_map,
            snapshot.get("trending", {}), my_needs, self.intel(),
        )

    def draft_state(self) -> dict | None:
        snapshot = self._ensure_snapshot()
        return snapshot.get("draft")

    def refresh_draft(self) -> dict | None:
        league_id = self.config["league_id"]
        with SleeperClient(league_id) as sleeper:
            user = sleeper.resolve_user(username=self.config.get("username"))
            my_id = user["user_id"] if user else None
            draft = sleeper.get_draft_state(my_id)
        self._ensure_snapshot()
        if self._snapshot is not None:
            self._snapshot["draft"] = draft
            cache = ROOT / "data" / "cache" / "league_snapshot.json"
            cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else dict(self._snapshot)
            cached["draft"] = draft
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        return draft

    def get_keepers(self) -> list[str]:
        if not self.has_keepers():
            return []
        configured = self.config.get("keepers") or []
        if configured:
            return configured
        _, my_team = self._ensure_loaded()
        draft = self.draft_state()
        if not draft:
            draft = self.refresh_draft()
        return sync_keepers_from_draft(my_team, draft)

    def keeper_plan(self, keeper_names: list[str] | None = None):
        _, my_team = self._ensure_loaded()
        names = keeper_names if keeper_names is not None else self.get_keepers()
        return build_keeper_plan(my_team, names, self.adp_map, self.config, self.draft_state())

    def draft_board(self, keeper_names: list[str] | None = None, limit: int = 75) -> list:
        snapshot = self._ensure_snapshot()
        names = [] if not self.has_keepers() else (
            keeper_names if keeper_names is not None else self.get_keepers()
        )
        intel = self.intel()
        return build_draft_board(
            self.adp_map, snapshot, self.config, names, intel=intel, limit=limit,
        )

    def upside_targets(self, keeper_names: list[str] | None = None, limit: int = 25) -> list:
        snapshot = self._ensure_snapshot()
        intel = self.intel()
        return build_upside_targets(self.adp_map, snapshot, intel=intel, limit=limit)

    def pick_recommendations(
        self,
        keeper_names: list[str] | None = None,
        limit: int = 5,
        draft: dict | None = None,
        my_slot: int | None = None,
        on_clock: bool = False,
    ) -> tuple[list, list[int], int | None]:
        board = self.draft_board(keeper_names=keeper_names, limit=100)
        draft = draft if draft is not None else self.draft_state()
        if my_slot is None and draft:
            my_slot = draft.get("my_slot")
        teams = draft.get("teams") or len(draft.get("draft_order") or {}) or 12
        return recommend_for_my_slot(
            board, draft, my_slot, teams=teams, on_clock=on_clock, limit=limit,
        )

    def manager_draft_profiles(self) -> list:
        snapshot = self._ensure_snapshot()
        return build_manager_profiles(snapshot, self.config)

    def build_context(self) -> str:
        """Build rich context for AI chat (Claude, Cursor, etc.)."""
        overview = self.league_overview()
        grades = self.grade_my_roster()
        sells = self.sell_candidates()
        trades = self.trade_targets()
        waivers = self.waiver_targets()

        my_needs = overview.get("my_needs")
        lines = [
            "# Dynasty Fantasy Football Analysis Context",
            f"League format: {self.config.get('format', 'dynasty')} {self.config.get('scoring', 'ppr')}",
            f"My team: {overview['my_team']} ({overview['record']})",
            "",
            "## My Positional Needs",
        ]
        if my_needs:
            lines.extend([
                f"Desperate for: {', '.join(my_needs.desperate_for) or 'None'}",
                f"Starter gaps: {my_needs.starter_gaps}",
                f"Surplus: {my_needs.surplus}",
            ])
        else:
            lines.append("Set username to see personalized needs.")
        lines.extend([
            "",
            "## League Manager Profiles (Trade Leverage)",
        ])

        for team in overview["all_teams"]:
            if team["manager"] == overview["my_team"]:
                continue
            lines.append(
                f"- **{team['manager']}** ({team['team']}): "
                f"RB={team['counts'].get('RB',0)} WR={team['counts'].get('WR',0)} "
                f"QB={team['counts'].get('QB',0)} TE={team['counts'].get('TE',0)} | "
                f"Desperate: {team['desperate_for'] or 'balanced'} | "
                f"Overloaded: {team['overloaded_at'] or 'none'}"
            )

        lines.extend(["", "## My Roster Grades (ADP + News)"])
        for g in grades[:25]:
            notes = "; ".join(g["notes"][:2])
            lines.append(f"- {g['name']} ({g['position']}) — Grade {g['grade']} | ADP {g['adp'] or 'N/A'} | {notes}")

        lines.extend(["", "## Sell Before They Fall Off"])
        for s in sells[:8]:
            lines.append(f"- [{s.urgency.upper()}] {s.player} ({s.position}): {s.reason}")

        lines.extend(["", "## Trade Targets (Manager-Specific)"])
        for t in trades[:8]:
            lines.append(
                f"- **{t.target_manager}**: Send {', '.join(t.you_give)} → Get {', '.join(t.you_get)} "
                f"(leverage {t.leverage_score:.1f}) — {t.rationale}"
            )

        lines.extend(["", "## Waiver Wire (For My Situation)"])
        for w in waivers[:10]:
            lines.append(f"- {w.player} ({w.position}, ADP {w.adp}): {w.reason}")

        lines.extend(["", "## Live News — Rotowire, Underdog & ESPN"])
        try:
            by_source = self.news.get_news_by_source()
            for src, label in [("rotowire", "@RotoWireNFL"), ("underdog", "@UnderdogNFL"), ("espn", "ESPN")]:
                items = by_source.get(src, [])
                if items:
                    lines.append(f"\n### {label}")
                    for n in items[:6]:
                        lines.append(f"- [{n['source']}] {n['headline']}")
        except Exception:
            for n in self.news.get_news(limit=10):
                lines.append(f"- [{n.get('source', 'News')}] {n['headline']}")

        lines.extend(["", "## Key Injuries (ESPN)"])
        try:
            injuries = self.news.get_injuries()[:15]
        except Exception:
            injuries = []
        for inj in injuries[:10]:
            lines.append(f"- {inj['name']} ({inj['team']}): {inj['status']} — {inj.get('detail', '')}")

        return "\n".join(lines)

    def ask(self, question: str, api_key: str | None = None) -> str:
        """Natural language analysis via Claude."""
        import anthropic

        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("Set ANTHROPIC_API_KEY in .env for the ask command")

        context = self.build_context()
        client = anthropic.Anthropic(api_key=key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=(
                "You are an elite dynasty fantasy football analyst. You know this manager's full "
                "league context, roster, every other team's needs, live news, and ADP values. "
                "Give specific, actionable advice. Reference managers by name when discussing trades. "
                "Explain trade leverage — why a specific manager would want a player. "
                "Be direct and concise."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"{context}\n\n---\n\nQuestion: {question}",
                }
            ],
        )
        block = message.content[0]
        return block.text if hasattr(block, "text") else str(block)
