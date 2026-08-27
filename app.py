"""Dynasty Fantasy Football Analyst — web app."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analyst import DynastyAnalyst, load_config
from src.draft import format_pick_label
from src.news import get_news_client

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "league.json"
EXAMPLE_PATH = ROOT / "config" / "league.example.json"

POS_COLORS = {"QB": "#3b82f6", "RB": "#22c55e", "WR": "#a855f7", "TE": "#f59e0b"}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    base = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    try:
        for key in ("league_id", "username", "league_name", "fantasypros_api_key"):
            if key in st.secrets:
                base[key] = st.secrets[key]
    except Exception:
        pass
    return base


def _cell(value, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _truncate(text: str, max_len: int = 100) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _first_sentence(text: str) -> str:
    """Pull the first readable chunk from a reason string."""
    for sep in (" · ", "; ", " — "):
        if sep in text:
            return text.split(sep)[0].strip()
    return _truncate(text, 80)


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


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            background: #1a1d24;
            padding: 0.65rem 0.85rem;
            border-radius: 0.5rem;
            border: 1px solid #2d3139;
        }
        .pos-pill {
            display: inline-block;
            padding: 0.1rem 0.45rem;
            border-radius: 0.35rem;
            font-size: 0.72rem;
            font-weight: 700;
            color: #fff;
            margin-right: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _pos_badge(position: str) -> str:
    color = POS_COLORS.get(position, "#64748b")
    return f'<span class="pos-pill" style="background:{color}">{position}</span>'


def _safe_dataframe(df: pd.DataFrame, height: int | None = None) -> None:
    kwargs = {"width": "stretch", "hide_index": True}
    if height:
        kwargs["height"] = height
    st.dataframe(df.astype(str), **kwargs)


def _render_pick_cards(recs, *, highlight_first: bool = False) -> None:
    if not recs:
        st.info("No recommendations yet — sync your league.")
        return
    for i, r in enumerate(recs, 1):
        border = "#1DB954" if highlight_first and i == 1 else None
        with st.container(border=True):
            if border:
                st.markdown(
                    f"**#{i} {r.player}** {_pos_badge(r.position)}",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"**{i}. {r.player}** {_pos_badge(r.position)}",
                    unsafe_allow_html=True,
                )
            m1, m2, m3 = st.columns(3)
            m1.metric("ADP", _cell(r.adp))
            m2.metric("Fit", f"{r.fit_score:.0f}")
            m3.metric("Upside", f"{r.upside_score:.0f}" if r.upside_score else "—")
            st.caption(_truncate(r.reason, 130))


def _render_upside_cards(targets, limit: int = 6) -> None:
    if not targets:
        st.info("No high-upside targets in the pool right now.")
        return
    cols = st.columns(2)
    for idx, u in enumerate(targets[:limit]):
        with cols[idx % 2]:
            with st.container(border=True):
                st.markdown(
                    f"**{u.player}** {_pos_badge(u.position)}",
                    unsafe_allow_html=True,
                )
                st.caption(f"ADP {_cell(u.adp)} · Upside **{u.upside_score:.0f}**")
                st.caption(_truncate(u.insight, 90))


def _board_insight(entry) -> str:
    parts = []
    if entry.upside_note:
        parts.append(_first_sentence(entry.upside_note))
    elif entry.fit_reason:
        parts.append(_first_sentence(entry.fit_reason))
    if entry.news_flag and entry.news_flag != "—":
        parts.append(entry.news_flag.split(" · ")[0])
    return " · ".join(parts) if parts else "—"


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
                "Summary": summary[:140] if summary else "—",
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
            "Detail": _truncate(inj.get("detail", "") or "—", 60),
            "_roster_hit": on_roster,
        })
    rows.sort(key=lambda r: (not r["_roster_hit"], r["Player"]))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.drop(columns=["_roster_hit"])


def _highlight_roster_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Your Player" not in df.columns:
        return df.style

    def _style_row(row: pd.Series) -> list[str]:
        if row["Your Player"] != "—":
            return ["background-color: #1a4d2e; color: #ecfdf5"] * len(row)
        return [""] * len(row)

    return df.style.apply(_style_row, axis=1)


def _render_news_table(df: pd.DataFrame, height: int = 360) -> None:
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
        height=height,
        column_config=link_cfg,
    )


def _draft_context(analyst: DynastyAnalyst, config: dict) -> dict:
    """Shared draft state used across Home and Draft tabs."""
    draft = analyst.draft_state()
    keepers = analyst.get_keepers()
    my_slot = (draft or {}).get("my_slot")
    teams = (draft or {}).get("teams") or len((draft or {}).get("draft_order") or {}) or 12
    recs, next_picks, target_pick = analyst.pick_recommendations(
        keeper_names=keepers, limit=5, draft=draft, my_slot=my_slot,
    )
    upside = analyst.upside_targets(keeper_names=keepers, limit=12)
    plan = analyst.draft_plan(keepers)
    return {
        "draft": draft,
        "keepers": keepers,
        "show_keeper_ui": analyst.show_keeper_ui(),
        "my_slot": my_slot,
        "teams": teams,
        "recs": recs,
        "next_picks": next_picks,
        "target_pick": target_pick,
        "upside": upside,
        "plan": plan,
    }


# ── Page setup ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Dynasty Analyst",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)
_inject_styles()

with st.sidebar:
    st.markdown("### 🏈 Dynasty Analyst")
    config = get_config()

    with st.expander("League settings", expanded=not config.get("league_id")):
        league_id = st.text_input(
            "Sleeper League ID",
            value=config.get("league_id", "") if config.get("league_id") != "YOUR_LEAGUE_ID" else "",
            help="From your league URL: sleeper.app/leagues/1234567890",
        )
        username = st.text_input(
            "Your Sleeper username",
            value=config.get("username", ""),
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
                        snapshot = analyst.sync()
                        analyst.news.close()
                    save_config({**updated, **analyst.config})
                    load_grades.clear()
                    load_live_draft.clear()
                    st.success("League synced!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if st.button("Refresh all data", use_container_width=True):
        try:
            with st.spinner("Refreshing..."):
                analyst = DynastyAnalyst(get_config())
                analyst.sync()
                analyst.refresh_draft()
                analyst.news.close()
            save_config({**get_config(), **analyst.config})
            load_grades.clear()
            load_live_draft.clear()
            st.success("Data refreshed.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

config = get_config()
if (
    not config.get("league_id")
    or config.get("league_id") == "YOUR_LEAGUE_ID"
    or not config.get("username")
):
    st.title("Dynasty Fantasy Football Analyst")
    st.info("Open **League settings** in the sidebar, enter your Sleeper league ID and username, then click **Save & Sync**.")
    st.markdown(
        """
        **What you'll get**
        - A **Home** dashboard with your next picks and breakout targets
        - **Draft** prep tailored to your snake slot
        - **My Team** roster grades and sell alerts
        - **League** map and trade targets
        - **News** and waivers in one place
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
    st.info("Open **League settings** and click **Save & Sync**.")
    st.stop()

overview = analyst.league_overview()
ctx = _draft_context(analyst, config)
draft = ctx["draft"]
teams = ctx["teams"]
my_slot = ctx["my_slot"]
has_keepers = ctx["show_keeper_ui"]

with st.sidebar:
    st.divider()
    st.caption("Connected")
    st.markdown(f"**{overview.get('my_team') or 'My Team'}**")
    if overview.get("record"):
        st.caption(f"Record {overview['record']}")
    if my_slot:
        st.caption(f"Draft slot **{my_slot}**")
    if ctx["target_pick"]:
        st.caption(f"Next pick: **{format_pick_label(ctx['target_pick'], teams)}**")
    if ctx["plan"].remaining_needs:
        st.caption(f"Needs: {', '.join(ctx['plan'].remaining_needs[:3])}")

st.title(overview.get("my_team") or "Dynasty Analyst")
st.caption(config.get("league_name") or "Sleeper league · synced")

tab_home, tab_draft, tab_team, tab_league, tab_news = st.tabs(
    ["Home", "Draft", "My Team", "League", "News"]
)

# ── Home ──────────────────────────────────────────────────────────────────────

with tab_home:
    try:
        my = overview.get("my_needs")
        c1, c2, c3 = st.columns(3)
        c1.metric("Draft slot", my_slot or "—")
        c2.metric(
            "Next pick",
            format_pick_label(ctx["target_pick"], teams).split(" (")[0] if ctx["target_pick"] else "—",
        )
        c3.metric("Top need", ", ".join(ctx["plan"].remaining_needs[:2]) or "Balanced")

        if ctx["keepers"]:
            st.caption("Draft keepers (from Sleeper): " + " · ".join(f"`{k}`" for k in ctx["keepers"]))

        st.divider()
        left, right = st.columns([3, 2])

        with left:
            if ctx["target_pick"]:
                st.subheader(f"Best at {format_pick_label(ctx['target_pick'], teams)}")
            else:
                st.subheader("Top picks for your build")
            if ctx["next_picks"]:
                upcoming = " → ".join(p.split(" (")[0] for p in [format_pick_label(p, teams) for p in ctx["next_picks"][:3]])
                st.caption(f"Upcoming: {upcoming}")
            _render_pick_cards(ctx["recs"][:3])

        with right:
            st.subheader("Breakout watch")
            _render_upside_cards(ctx["upside"], limit=4)

        sells = analyst.sell_candidates()
        if sells:
            st.divider()
            st.subheader("Action items")
            for s in sells[:3]:
                icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.urgency, "")
                st.markdown(f"{icon} Consider selling **{s.player}** — {_truncate(s.reason, 80)}")
    except Exception as e:
        st.error(f"Home failed: {e}")

# ── Draft ─────────────────────────────────────────────────────────────────────

with tab_draft:
    try:
        view = st.radio(
            "Show",
            ["My picks", "Upside targets", "All players", "Live draft"],
            horizontal=True,
            label_visibility="collapsed",
        )

        keepers = ctx["keepers"]

        if view == "My picks":
            st.subheader("Pick recommendations")
            st.caption("Ranked for your roster holes, ADP window at your next snake pick, and upside.")
            if my_slot and ctx["next_picks"]:
                st.info(
                    f"Slot **{my_slot}** · Next picks: "
                    + " · ".join(format_pick_label(p, teams) for p in ctx["next_picks"][:4])
                )
            _render_pick_cards(ctx["recs"], highlight_first=True)

        elif view == "Upside targets":
            st.subheader("High upside & bigger roles")
            st.caption("Youth, depth-chart climb, trending adds, and role-change news.")
            _render_upside_cards(ctx["upside"], limit=12)
            with st.expander("Full upside table"):
                udf = pd.DataFrame([{
                    "Player": u.player,
                    "Pos": u.position,
                    "ADP": _cell(u.adp),
                    "Upside": u.upside_score,
                    "Insight": _truncate(u.insight, 100),
                } for u in ctx["upside"]])
                _safe_dataframe(udf, height=400)

        elif view == "All players":
            pos_filter = st.selectbox("Position", ["All", "QB", "RB", "WR", "TE"], label_visibility="collapsed")
            board = analyst.draft_board(keeper_names=keepers, limit=100)
            if pos_filter != "All":
                board = [b for b in board if b.position == pos_filter]

            st.caption("Sorted by roster fit. Green rows = strong fit (75+).")
            if not board:
                st.info("No available players — sync draft or refresh league data.")
            else:
                bdf = pd.DataFrame([{
                    "Player": b.player,
                    "Pos": b.position,
                    "ADP": _cell(b.adp),
                    "Fit": b.fit_score,
                    "Upside": b.upside_score or "—",
                    "Insight": _board_insight(b),
                } for b in board[:50]])
                styled = bdf.style.apply(
                    lambda row: (
                        ["background-color: #1a4d2e; color: #ecfdf5"] * len(row)
                        if float(row["Fit"]) >= 75 else [""] * len(row)
                    ),
                    axis=1,
                )
                st.dataframe(styled, width="stretch", hide_index=True, height=480)

        else:
            if st.button("Refresh live draft"):
                load_live_draft.clear()
                analyst.refresh_draft()
                st.rerun()

            live = load_live_draft(config["league_id"], config["username"])
            if not live:
                st.info("No Sleeper draft found yet.")
            else:
                on_clock = live.get("on_clock") or {}
                my_user_id = analyst._ensure_snapshot().get("my_user_id") or live.get("my_user_id")
                is_my_pick = on_clock.get("user_id") == my_user_id
                live_teams = live.get("teams") or teams

                s1, s2, s3 = st.columns(3)
                s1.metric("Status", live.get("status", "—"))
                s2.metric("Progress", f"{live.get('completed_picks', 0)}/{live.get('total_picks', '?')}")
                s3.metric("Your slot", live.get("my_slot") or "—")

                if on_clock:
                    if is_my_pick:
                        st.success(f"You're on the clock — Pick {on_clock.get('pick_no')} (Rd {on_clock.get('round')})")
                    else:
                        st.info(f"On clock: **{on_clock.get('manager')}** · Pick {on_clock.get('pick_no')}")

                live_recs, live_next, live_target = analyst.pick_recommendations(
                    keeper_names=keepers,
                    limit=5,
                    draft=live,
                    my_slot=live.get("my_slot"),
                    on_clock=is_my_pick,
                )
                if is_my_pick:
                    st.subheader("Pick now")
                    _render_pick_cards(live_recs, highlight_first=True)
                else:
                    label = format_pick_label(live_target, live_teams) if live_target else "your next pick"
                    st.subheader(f"Queue for {label}")
                    _render_pick_cards(live_recs[:4])

                picks = live.get("picks", [])
                if picks:
                    with st.expander("Recent picks", expanded=False):
                        pdf = pd.DataFrame([{
                            "Pick": p.get("pick_no"),
                            "Rd": p.get("round"),
                            "Manager": p.get("manager"),
                            "Player": p.get("player_name"),
                            "Pos": p.get("position"),
                        } for p in reversed(picks[-24:])])
                        _safe_dataframe(pdf, height=320)
    except Exception as e:
        st.error(f"Draft failed: {e}")

# ── My Team ───────────────────────────────────────────────────────────────────

with tab_team:
    try:
        team_sections = ["Roster grades", "Sell alerts"]
        if has_keepers:
            team_sections = ["Keepers"] + team_sections
        section = st.radio(
            "Section",
            team_sections,
            horizontal=True,
            label_visibility="collapsed",
        )

        if section == "Keepers" and has_keepers:
            _, my_team = analyst._ensure_loaded()
            skill_players = sorted(
                p["name"] for p in my_team.get("players", [])
                if p.get("position") in {"QB", "RB", "WR", "TE"}
            )
            max_keepers = int(config.get("max_keepers") or ctx["plan"].max_keepers or 0)
            default_keepers = [k for k in ctx["keepers"] if k in skill_players]

            selected = st.multiselect(
                f"Select keepers (max {max_keepers})",
                skill_players,
                default=default_keepers,
                max_selections=max_keepers,
            )
            if st.button("Save keepers", type="primary"):
                updated = {**config, "keepers": selected}
                save_config(updated)
                st.success("Keepers saved.")
                st.rerun()

            plan = analyst.keeper_plan(selected)
            m1, m2, m3 = st.columns(3)
            m1.metric("Locked", f"{len(plan.keepers)}/{plan.max_keepers}")
            m2.metric("Draft needs", ", ".join(plan.remaining_needs[:2]) or "Balanced")
            m3.metric("Priorities", ", ".join(plan.draft_priorities[:2]) or "—")

            counts = plan.post_keeper_counts
            st.caption(
                f"After keepers — QB {counts.get('QB', 0)} · RB {counts.get('RB', 0)} · "
                f"WR {counts.get('WR', 0)} · TE {counts.get('TE', 0)}"
            )
            if plan.keepers:
                kdf = pd.DataFrame([{
                    "Player": k["name"],
                    "Pos": k["position"],
                    "ADP": _cell(k["adp"]),
                    "Round": _cell(k.get("keeper_round")),
                } for k in plan.keepers])
                _safe_dataframe(kdf)

        elif section == "Roster grades":
            grades = load_grades(json.dumps(config, sort_keys=True))
            df = pd.DataFrame([{
                "Player": g["name"],
                "Pos": g["position"],
                "ADP": _cell(g["adp"]),
                "Age": _cell(g["age"]),
                "Grade": g["grade"],
                "Notes": _truncate("; ".join(g["notes"]), 80),
            } for g in grades])
            _safe_dataframe(df, height=480)

        else:
            sells = analyst.sell_candidates()
            if not sells:
                st.success("No urgent sell candidates on your roster.")
            else:
                for s in sells:
                    icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.urgency, "")
                    with st.container(border=True):
                        st.markdown(f"{icon} **{s.player}** ({s.position}) · ADP {_cell(s.adp)}")
                        st.caption(s.reason)
    except Exception as e:
        st.error(f"My Team failed: {e}")

# ── League ────────────────────────────────────────────────────────────────────

with tab_league:
    try:
        section = st.radio(
            "Section",
            ["Trade proposals", "Team breakdown", "Manager tendencies", "Manager map"],
            horizontal=True,
            label_visibility="collapsed",
        )

        profiles = analyst.team_trade_profiles()
        proposals = analyst.trade_proposals()
        tendencies = analyst.manager_tendencies()
        _, my_team_data = analyst._ensure_loaded()
        my_profile = next(
            (p for p in profiles if p.owner_id == my_team_data.get("owner_id")), None,
        )

        if section == "Trade proposals":
            st.caption(
                "Realistic offers only — filtered so the other manager breaks even or wins slightly on "
                "[FantasyCalc](https://www.fantasycalc.com/trade-calculator). "
                "Rankings from FantasyCalc + [LeagueLogs](https://leaguelogs.com) (free)."
            )
            if not proposals:
                st.info("No strong proposals yet — sync league data or check Team breakdown for manual targets.")
            else:
                for p in proposals[:10]:
                    with st.container(border=True):
                        acc_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(p.acceptance, "")
                        head = f"{acc_color} **{p.target_manager}** ({p.target_team})"
                        st.markdown(
                            f"{head} · **{p.acceptance} accept chance** · Leverage {p.leverage_score:.0f}"
                        )
                        send = p.you_send_players + [f"📋 {x}" for x in p.you_send_picks]
                        recv = p.you_receive_players + [f"📋 {x}" for x in p.you_receive_picks]
                        c1, c2, c3 = st.columns([2, 2, 1])
                        with c1:
                            st.markdown("**You send**")
                            st.markdown(" · ".join(send) if send else "—")
                        with c2:
                            st.markdown("**You get**")
                            st.markdown(" · ".join(recv) if recv else "—")
                        with c3:
                            if p.fc_receive_total:
                                st.metric("FantasyCalc in", f"{p.fc_receive_total:,}")
                                st.caption(
                                    f"Out {p.fc_send_total:,} · Δ {p.fc_delta:+,} · {p.fc_verdict or p.fairness}"
                                )
                            else:
                                st.metric("Value in", f"{p.receive_value:.0f}")
                                st.caption(f"Out {p.send_value:.0f} · Δ {p.value_delta:+.0f} · {p.fairness}")
                        if p.fp_insight:
                            st.caption(f"**Market:** {p.fp_insight}")
                        if p.their_fc_edge > 0:
                            st.caption(f"They gain **{p.their_fc_edge:,}** on FantasyCalc — fair for them.")
                        st.caption(f"**Why they bite:** {_truncate(p.why_they_accept, 120)}")
                        st.caption(f"**Why you win:** {_truncate(p.why_you_win, 120)} · *{p.risk_notes}*")

        elif section == "Team breakdown":
            managers = [p.manager for p in profiles]
            selected = st.selectbox("Select team", managers, label_visibility="collapsed")
            profile = next(p for p in profiles if p.manager == selected)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Record", profile.record)
            m2.metric("Mode", profile.win_mode)
            m3.metric("Desperate", ", ".join(profile.desperate_for) or "None")
            m4.metric("Surplus", ", ".join(profile.surplus_at) or "None")

            st.markdown(f"**Archetype:** {profile.tendency.archetype}")
            if profile.tendency.notes:
                st.caption(profile.tendency.notes)

            st.subheader("Position units — quality & value")
            unit_df = pd.DataFrame([{
                "Pos": u.position,
                "Count": u.count,
                "Quality": u.quality,
                "Starter Val": u.starter_value,
                "Depth Val": u.depth_value,
                "Top Player": u.top_player,
                "Need": u.need_score,
                "Surplus": u.surplus_score,
                "Notes": _truncate(u.notes, 70),
            } for u in profile.units])
            _safe_dataframe(unit_df, height=220)

            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Best trade assets")
                if profile.tradeable_assets:
                    adf = pd.DataFrame([{
                        "Player": v.name,
                        "Pos": v.position,
                        "FantasyCalc": f"{v.fc_value:,}" if v.fc_value else "—",
                        "FC Trend": v.fc_trend or "—",
                        "Grade": v.grade,
                        "FantasyPros": _truncate(v.fp_summary, 40) or "—",
                        "Market": _truncate(v.summary, 50),
                    } for v in profile.tradeable_assets[:8]])
                    _safe_dataframe(adf, height=280)
                else:
                    st.caption("No clear trade chips — core is consolidated.")
            with col_b:
                st.subheader("Top roster targets")
                tdf = pd.DataFrame([{
                    "Player": v.name,
                    "Pos": v.position,
                    "FantasyCalc": f"{v.fc_value:,}" if v.fc_value else "—",
                    "Grade": v.grade,
                    "FantasyPros": _truncate(v.fp_summary, 40) or "—",
                    "Profile": _truncate(v.summary, 50),
                } for v in profile.targets_on_roster])
                _safe_dataframe(tdf, height=280)

            if profile.pick_values:
                st.subheader("Draft pick capital")
                pdf = pd.DataFrame([{"Pick": l, "Value": v} for l, v in profile.pick_values])
                _safe_dataframe(pdf, height=160)

            team_proposals = [p for p in proposals if p.target_manager == selected]
            if team_proposals:
                st.subheader(f"Suggested deals with {selected}")
                for p in team_proposals[:3]:
                    send = ", ".join(p.you_send_players + p.you_send_picks)
                    recv = ", ".join(p.you_receive_players + p.you_receive_picks)
                    st.markdown(f"**Send** {send} → **Get** {recv} · Value Δ {p.value_delta:+.0f} ({p.fairness})")

        elif section == "Manager tendencies":
            st.caption("Built from prior-season drafts and trade history in your Sleeper league chain.")
            trows = [{
                "Manager": t.manager,
                "Archetype": t.archetype,
                "Trades": t.trade_count,
                "Picks moved": t.picks_traded,
                "Early RB%": f"{t.draft_rb_early_pct:.0f}%",
                "Early WR%": f"{t.draft_wr_early_pct:.0f}%",
                "Youth%": f"{t.draft_youth_pct:.0f}%",
                "Likes": ", ".join(t.likes) or "—",
                "Notes": _truncate(t.notes, 80),
            } for t in tendencies.values()]
            trows.sort(key=lambda r: r["Trades"], reverse=True)
            _safe_dataframe(pd.DataFrame(trows), height=420)

        else:
            my = overview.get("my_needs")
            if my:
                c1, c2, c3 = st.columns(3)
                c1.metric("Desperate for", ", ".join(my.desperate_for) or "None")
                c2.metric("Surplus", ", ".join(f"{k}+{v}" for k, v in my.surplus.items()) or "None")
                c3.metric("Match score leaders", len([p for p in profiles if p.best_match_score >= 3]))

            rows = [{
                "Manager": p.manager,
                "Match": p.best_match_score,
                "Desperate": ", ".join(p.desperate_for) or "—",
                "Surplus": ", ".join(p.surplus_at) or "—",
                "Mode": p.win_mode,
                "Top need": p.desperate_for[0] if p.desperate_for else "—",
            } for p in profiles if p.manager != overview.get("my_team")]
            rows.sort(key=lambda r: r["Match"], reverse=True)
            _safe_dataframe(pd.DataFrame(rows), height=420)
    except Exception as e:
        st.error(f"League failed: {e}")

# ── News ──────────────────────────────────────────────────────────────────────

with tab_news:
    try:
        section = st.radio(
            "Section",
            ["Headlines", "Injuries", "Waivers"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if section == "Waivers":
            waivers = analyst.waiver_targets()
            df = pd.DataFrame([{
                "Player": w.player,
                "Pos": w.position,
                "ADP": _cell(w.adp),
                "Why": _truncate(w.reason, 90),
            } for w in waivers[:15]])
            _safe_dataframe(df, height=400)
        else:
            by_source = load_news_feeds()
            roster_names = _roster_player_names(analyst)

            if section == "Headlines":
                roster_only = st.toggle("My players only", value=False)
                news_df = _build_news_table(by_source, roster_names)
                if roster_only and not news_df.empty:
                    news_df = news_df[news_df["Your Player"] != "—"]
                st.caption("Green = mentions someone on your roster.")
                _render_news_table(news_df)
            else:
                inj_df = _build_injury_table(by_source.get("injuries", [])[:40], roster_names)
                st.caption("Green = your roster.")
                _render_news_table(inj_df)

            if st.button("Refresh news"):
                load_news_feeds.clear()
                st.rerun()
    except Exception as e:
        st.error(f"News failed: {e}")

with st.expander("Export for AI chat"):
    if st.button("Generate context"):
        try:
            st.code(analyst.build_context(), language="markdown")
        except Exception as e:
            st.error(f"Export failed: {e}")
