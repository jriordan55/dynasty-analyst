"""Dynasty Fantasy Football Analyst — web app."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analyst import DynastyAnalyst, load_config
from src.news import get_news_client

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "league.json"
EXAMPLE_PATH = ROOT / "config" / "league.example.json"


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    base = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    try:
        for key in ("league_id", "username", "league_name"):
            if key in st.secrets:
                base[key] = st.secrets[key]
    except Exception:
        pass
    return base


def _cell(value, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


@st.cache_data(ttl=300, show_spinner=False)
def load_news_feeds() -> dict:
    client = get_news_client()
    try:
        return client.get_news_by_source()
    except Exception:
        return {"rotowire": [], "underdog": [], "espn": [], "injuries": []}
    finally:
        client.close()


@st.cache_data(ttl=30, show_spinner=False)
def load_live_draft(league_id: str, username: str) -> dict | None:
    from src.sleeper import SleeperClient

    with SleeperClient(league_id) as sleeper:
        user = sleeper.resolve_user(username=username)
        my_id = user["user_id"] if user else None
        return sleeper.get_draft_state(my_id)


@st.cache_data(ttl=120, show_spinner=False)
def load_grades(config_json: str) -> list[dict]:
    analyst = DynastyAnalyst(json.loads(config_json))
    analyst._ensure_snapshot()
    try:
        return analyst.grade_my_roster()
    finally:
        analyst.news.close()


def _safe_dataframe(df: pd.DataFrame) -> None:
    """Render table without pyarrow mixed-type crashes."""
    st.dataframe(df.astype(str), width="stretch", hide_index=True)


def _roster_player_names(analyst: DynastyAnalyst) -> set[str]:
    try:
        _, my_team = analyst._ensure_loaded()
        skill = {"QB", "RB", "WR", "TE"}
        return {
            p["name"] for p in my_team.get("players", [])
            if p.get("name") and p.get("position") in skill
        }
    except Exception:
        return set()


def _match_roster_players(item: dict, roster_names: set[str]) -> list[str]:
    text = f"{item.get('headline', '')} {item.get('description', '')}".lower()
    matched: list[str] = []
    tagged = item.get("player", "")
    if tagged and tagged in roster_names:
        matched.append(tagged)
    for name in sorted(roster_names, key=len, reverse=True):
        if name in matched:
            continue
        parts = [p for p in name.lower().split() if len(p) > 2]
        if parts and all(p in text for p in parts):
            matched.append(name)
    return matched


def _build_news_table(by_source: dict, roster_names: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    source_labels = {
        "rotowire": "@RotoWireNFL",
        "underdog": "@UnderdogNFL",
        "espn": "ESPN",
    }
    for key, label in source_labels.items():
        for item in by_source.get(key, []):
            players = _match_roster_players(item, roster_names)
            summary = (item.get("description") or "").strip()
            if summary and summary == item.get("headline", ""):
                summary = ""
            rows.append({
                "Your Player": ", ".join(players) if players else "—",
                "Source": label,
                "Headline": item.get("headline", ""),
                "Summary": summary[:180] if summary else "—",
                "Link": item.get("link", ""),
                "_roster_hit": bool(players),
                "_sort_ts": item.get("sort_ts", 0),
            })

    rows.sort(key=lambda r: (not r["_roster_hit"], -r["_sort_ts"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.drop(columns=["_roster_hit", "_sort_ts"])


def _build_injury_table(injuries: list[dict], roster_names: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for inj in injuries:
        name = inj.get("name", "")
        on_roster = name in roster_names
        rows.append({
            "Your Player": name if on_roster else "—",
            "Player": name,
            "Team": inj.get("team", ""),
            "Pos": inj.get("position", ""),
            "Status": inj.get("status", ""),
            "Detail": inj.get("detail", "") or "—",
            "_roster_hit": on_roster,
        })
    rows.sort(key=lambda r: (not r["_roster_hit"], r["Player"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.drop(columns=["_roster_hit"])


def _highlight_roster_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return a Styler that highlights rows mentioning your roster players."""
    if df.empty or "Your Player" not in df.columns:
        return df.style

    def _style_row(row: pd.Series) -> list[str]:
        if row["Your Player"] != "—":
            return ["background-color: #1a4d2e; color: #ecfdf5"] * len(row)
        return [""] * len(row)

    return df.style.apply(_style_row, axis=1)


def _render_news_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No headlines loaded right now.")
        return
    styled = _highlight_roster_rows(df)
    link_cfg = {}
    if "Link" in df.columns:
        link_cfg["Link"] = st.column_config.LinkColumn("Link", display_text="Read →")
    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        column_config=link_cfg,
    )


st.set_page_config(
    page_title="Dynasty Analyst",
    page_icon="🏈",
    layout="wide",
)

st.title("Dynasty Fantasy Football Analyst")
st.caption("Sleeper · 4for4 ADP · @RotoWireNFL · @UnderdogNFL · ESPN")

with st.sidebar:
    st.header("League Setup")
    config = get_config()

    league_id = st.text_input(
        "Sleeper League ID",
        value=config.get("league_id", "") if config.get("league_id") != "YOUR_LEAGUE_ID" else "",
        help="From your league URL: sleeper.app/leagues/1234567890",
    )
    username = st.text_input(
        "Your Sleeper username",
        value=config.get("username", ""),
        help="Your display name in the league",
    )
    league_name = st.text_input("League name (optional)", value=config.get("league_name", ""))

    if st.button("Save & Sync", type="primary", use_container_width=True):
        if not league_id or not username:
            st.error("Enter league ID and username.")
        else:
            updated = {**config, "league_id": league_id.strip(), "username": username.strip()}
            if league_name:
                updated["league_name"] = league_name.strip()
            save_config(updated)
            try:
                with st.spinner("Syncing from Sleeper..."):
                    analyst = DynastyAnalyst(updated)
                    analyst.sync()
                    analyst.news.close()
                load_grades.clear()
                st.success("League synced!")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    if st.button("Refresh league data", use_container_width=True):
        try:
            with st.spinner("Refreshing from Sleeper..."):
                analyst = DynastyAnalyst(get_config())
                analyst.sync()
                analyst.news.close()
            load_grades.clear()
            st.success("League data refreshed.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.markdown("**Quick links**")
    st.markdown("- [Find league ID on Sleeper](https://sleeper.app)")
    st.markdown("- [4for4 ADP rankings](https://www.4for4.com/adp)")
    st.markdown("- [@RotoWireNFL on X](https://x.com/RotoWireNFL)")
    st.markdown("- [@UnderdogNFL on X](https://x.com/UnderdogNFL)")

config = get_config()
if (
    not config.get("league_id")
    or config.get("league_id") == "YOUR_LEAGUE_ID"
    or not config.get("username")
):
    st.info("Enter your Sleeper league ID and username in the sidebar, then click **Save & Sync**.")
    st.markdown(
        """
        ### What you get
        - **League map** — who is desperate at RB, overloaded at WR, etc.
        - **Roster grades** — your players vs ADP + live news
        - **Sell alerts** — aging RBs before the value cliff
        - **Trade targets** — specific managers who need what you have
        - **Waiver picks** — tailored to your roster holes
        """
    )
    st.stop()

try:
    analyst = DynastyAnalyst(config)
    analyst._ensure_snapshot()
    if not analyst.draft_state():
        analyst.refresh_draft()
except Exception as e:
    st.error(f"Could not load league: {e}")
    st.info("Click **Save & Sync** in the sidebar to connect your Sleeper league.")
    st.stop()

tab_overview, tab_keepers, tab_draft, tab_live, tab_grades, tab_sell, tab_trades, tab_waivers, tab_news = st.tabs(
    [
        "League Map",
        "Keepers",
        "Draft Board",
        "Live Draft",
        "My Grades",
        "Sell Alerts",
        "Trade Targets",
        "Waivers",
        "Fantasy News",
    ]
)

with tab_overview:
    try:
        data = analyst.league_overview()
        st.subheader("Manager profiles — trade leverage")
        rows = []
        for t in data["all_teams"]:
            c = t["counts"]
            rows.append({
                "Manager": t["manager"],
                "Team": t["team"],
                "QB": c.get("QB", 0),
                "RB": c.get("RB", 0),
                "WR": c.get("WR", 0),
                "TE": c.get("TE", 0),
                "Desperate For": ", ".join(t["desperate_for"]) or "—",
                "Overloaded": ", ".join(t["overloaded_at"]) or "—",
            })
        _safe_dataframe(pd.DataFrame(rows))

        my = data.get("my_needs")
        if my:
            c1, c2, c3 = st.columns(3)
            c1.metric("Your Team", data["my_team"])
            c2.metric("Desperate For", ", ".join(my.desperate_for) or "None")
            c3.metric("Surplus", ", ".join(f"{k} (+{v})" for k, v in my.surplus.items()) or "None")

        st.subheader("Manager draft tendencies")
        st.caption("Predictions based on roster build, keeper positions, and draft slot.")
        profiles = analyst.manager_draft_profiles()
        prof_df = pd.DataFrame([{
            "Slot": _cell(p.draft_slot),
            "Manager": p.manager,
            "Team": p.team,
            "RB": p.rb_count,
            "WR": p.wr_count,
            "QB": p.qb_count,
            "TE": p.te_count,
            "Tendency": p.tendency,
            "Keepers": ", ".join(p.keeper_positions) or "—",
            "Draft Prediction": p.draft_prediction,
        } for p in profiles])
        _safe_dataframe(prof_df)
    except Exception as e:
        st.error(f"League map failed: {e}")

with tab_keepers:
    try:
        _, my_team = analyst._ensure_loaded()
        skill_players = sorted(
            p["name"] for p in my_team.get("players", [])
            if p.get("position") in {"QB", "RB", "WR", "TE"}
        )
        max_keepers = int(config.get("max_keepers", 4))
        synced = analyst.get_keepers()
        default_keepers = [k for k in synced if k in skill_players]

        c1, c2 = st.columns([3, 1])
        with c2:
            if st.button("Sync from Sleeper"):
                draft = analyst.refresh_draft()
                if draft:
                    load_live_draft.clear()
                    synced = analyst.get_keepers()
                    st.rerun()
        with c1:
            selected = st.multiselect(
                f"Your keepers (max {max_keepers})",
                skill_players,
                default=default_keepers,
                max_selections=max_keepers,
            )

        if st.button("Save keepers", type="primary"):
            updated = {**config, "keepers": selected}
            save_config(updated)
            config.update(updated)
            st.success("Keepers saved.")

        plan = analyst.keeper_plan(selected)
        st.subheader("Post-keeper roster outlook")
        m1, m2, m3 = st.columns(3)
        m1.metric("Keepers locked", f"{len(plan.keepers)}/{plan.max_keepers}")
        m2.metric("Top draft needs", ", ".join(plan.remaining_needs[:3]) or "Balanced")
        m3.metric("Draft priorities", ", ".join(plan.draft_priorities[:3]))

        if plan.keepers:
            kdf = pd.DataFrame([{
                "Player": k["name"],
                "Pos": k["position"],
                "ADP": _cell(k["adp"]),
                "Keeper Round": _cell(k.get("keeper_round")),
            } for k in plan.keepers])
            _safe_dataframe(kdf)

        counts = plan.post_keeper_counts
        st.markdown(
            f"**After keepers:** QB {counts.get('QB', 0)} · "
            f"RB {counts.get('RB', 0)} · WR {counts.get('WR', 0)} · TE {counts.get('TE', 0)}"
        )
    except Exception as e:
        st.error(f"Keepers failed: {e}")

with tab_draft:
    try:
        keepers = config.get("keepers") or analyst.get_keepers()
        pos_filter = st.selectbox("Filter by position", ["All", "QB", "RB", "WR", "TE"])
        board = analyst.draft_board(keeper_names=keepers, limit=100)
        if pos_filter != "All":
            board = [b for b in board if b.position == pos_filter]

        st.subheader("Available players — ranked by roster fit")
        st.caption("Fit score blends ADP value with your post-keeper needs. News/injury flags shown.")
        if not board:
            st.info("No available players found. Sync draft or check keepers.")
        else:
            bdf = pd.DataFrame([{
                "Player": b.player,
                "Pos": b.position,
                "ADP": _cell(b.adp),
                "Tier": b.tier,
                "Fit": b.fit_score,
                "Why": b.fit_reason,
                "News/Injury": b.news_flag or "—",
                "Team": b.team or "—",
            } for b in board[:60]])
            styled = bdf.style.apply(
                lambda row: (
                    ["background-color: #1a4d2e; color: #ecfdf5"] * len(row)
                    if float(row["Fit"]) >= 75 else [""] * len(row)
                ),
                axis=1,
            )
            st.dataframe(styled, width="stretch", hide_index=True)

        recs = analyst.pick_recommendations(keeper_names=keepers, limit=5)
        st.subheader("Top 5 picks for your build")
        for i, r in enumerate(recs, 1):
            st.markdown(f"**{i}. {r.player}** ({r.position}, ADP {_cell(r.adp)}) — Fit {r.fit_score:.0f} · {r.reason}")
    except Exception as e:
        st.error(f"Draft board failed: {e}")

with tab_live:
    try:
        if st.button("Refresh live draft"):
            load_live_draft.clear()
            analyst.refresh_draft()
            st.rerun()

        live = load_live_draft(config["league_id"], config["username"])
        if not live:
            st.info("No Sleeper draft found for this league yet.")
        else:
            on_clock = live.get("on_clock") or {}
            my_slot = live.get("my_slot")
            status = live.get("status", "unknown")
            st.caption(f"Draft status: **{status}** · Your slot: **{my_slot or '—'}** · Pick {live.get('completed_picks', 0)}/{live.get('total_picks', '?')}")

            snapshot = analyst._ensure_snapshot()
            my_user_id = snapshot.get("my_user_id") or live.get("my_user_id")
            is_my_pick = on_clock.get("user_id") == my_user_id

            if on_clock:
                if is_my_pick:
                    st.success(f"You're on the clock — Pick {on_clock.get('pick_no')} (Round {on_clock.get('round')})")
                else:
                    st.info(f"On the clock: **{on_clock.get('manager')}** — Pick {on_clock.get('pick_no')} (Round {on_clock.get('round')})")

            keepers = config.get("keepers") or analyst.get_keepers()
            recs = analyst.pick_recommendations(keeper_names=keepers, limit=5)
            if is_my_pick:
                st.subheader("Pick this now")
                for i, r in enumerate(recs, 1):
                    st.markdown(
                        f"### {i}. {r.player} ({r.position})\n"
                        f"ADP {_cell(r.adp)} · Fit **{r.fit_score:.0f}** — {r.reason}"
                    )
            else:
                st.subheader("Best available for your team")
                for i, r in enumerate(recs[:3], 1):
                    st.markdown(f"**{i}. {r.player}** ({r.position}, ADP {_cell(r.adp)}) — {r.reason}")

            picks = live.get("picks", [])
            if picks:
                st.subheader("Draft board — picks so far")
                pdf = pd.DataFrame([{
                    "Pick": p.get("pick_no"),
                    "Rnd": p.get("round"),
                    "Manager": p.get("manager"),
                    "Player": p.get("player_name"),
                    "Pos": p.get("position"),
                    "Keeper": "Yes" if p.get("is_keeper") else "",
                } for p in reversed(picks[-36:])])
                _safe_dataframe(pdf)
    except Exception as e:
        st.error(f"Live draft failed: {e}")

with tab_grades:
    try:
        grades = load_grades(json.dumps(config, sort_keys=True))
        df = pd.DataFrame([{
            "Player": g["name"],
            "Pos": g["position"],
            "ADP": _cell(g["adp"]),
            "Age": _cell(g["age"]),
            "Grade": g["grade"],
            "Notes": "; ".join(g["notes"]),
        } for g in grades])
        _safe_dataframe(df)
    except Exception as e:
        st.error(f"Roster grades failed: {e}")

with tab_sell:
    try:
        sells = analyst.sell_candidates()
        if not sells:
            st.success("No urgent sell candidates.")
        else:
            for s in sells:
                color = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.urgency, "")
                st.warning(f"{color} **{s.player}** ({s.position}, ADP {s.adp or 'N/A'}) — {s.reason}")
    except Exception as e:
        st.error(f"Sell alerts failed: {e}")

with tab_trades:
    try:
        matches = analyst.trade_targets()
        if not matches:
            st.info("No automated matches — check the League Map for manual targets.")
            st.markdown(
                "**Tip:** Look for managers who are *desperate* at a position you're deep at. "
                "Example: you have 6 RBs, they have 1 RB and 6 WRs → offer an RB, ask for their WR1."
            )
        else:
            for t in matches[:10]:
                with st.expander(f"{t.target_manager} — leverage {t.leverage_score:.1f}"):
                    st.markdown(f"**Send:** {', '.join(t.you_give)}")
                    st.markdown(f"**Get:** {', '.join(t.you_get)}")
                    st.caption(t.rationale)
    except Exception as e:
        st.error(f"Trade targets failed: {e}")

with tab_waivers:
    try:
        waivers = analyst.waiver_targets()
        df = pd.DataFrame([{
            "Player": w.player,
            "Pos": w.position,
            "ADP": _cell(w.adp),
            "Why": w.reason,
        } for w in waivers[:15]])
        _safe_dataframe(df)
    except Exception as e:
        st.error(f"Waiver targets failed: {e}")

with tab_news:
    try:
        by_source = load_news_feeds()
        roster_names = _roster_player_names(analyst)

        if not any(by_source.get(k) for k in ("rotowire", "underdog", "espn")):
            st.warning("Some feeds are slow or unavailable — showing what we could load.")

        roster_only = st.checkbox("Show my roster news only", value=False)
        news_df = _build_news_table(by_source, roster_names)
        if roster_only and not news_df.empty:
            news_df = news_df[news_df["Your Player"] != "—"]

        st.subheader("Fantasy News Feed")
        st.caption("Green rows mention a player on your roster. Sorted with your players first.")
        _render_news_table(news_df)

        st.subheader("Injury Report")
        injuries = by_source.get("injuries", [])
        inj_df = _build_injury_table(injuries[:40], roster_names)
        if inj_df.empty:
            st.info("Injury report unavailable right now.")
        else:
            _render_news_table(inj_df)

        if st.button("Refresh news"):
            load_news_feeds.clear()
            st.rerun()
    except Exception as e:
        st.error(f"News failed: {e}")

st.divider()
with st.expander("Export context for Claude / Cursor chat"):
    if st.button("Generate export"):
        try:
            st.code(analyst.build_context(), language="markdown")
        except Exception as e:
            st.error(f"Export failed: {e}")
