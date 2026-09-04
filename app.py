"""Dynasty Fantasy Football Analyst — web app."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analyst import DynastyAnalyst, load_config
from src.draft import format_pick_label, is_pre_draft
from src.ui_dynatyze import (
    init_navigation,
    inject_dynatyze_shell,
    render_dashboard_home,
    render_league_hub_nav,
    render_sidebar_league,
    render_top_nav,
)
from src.dynatyze_dashboard import build_dynatyze_dashboard
from src.my_league import build_dashboard, build_roster_rows, section_counts
from src.news import get_news_client
from src.ui_my_league import render_my_league
from src.ui_platform import (
    inject_dynatyze_styles,
    render_analytics,
    render_rankings,
    render_tools,
    render_trade_calculator,
)
from src.ui_live_draft import render_live_draft
from src.version import APP_BUILD

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "league.json"
EXAMPLE_PATH = ROOT / "config" / "league.example.json"

POS_COLORS = {"QB": "#3b82f6", "RB": "#22c55e", "WR": "#a855f7", "TE": "#f59e0b"}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_config() -> dict:
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        cfg = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        try:
            for key in ("league_id", "username", "league_name", "fantasypros_api_key"):
                if key in st.secrets:
                    cfg[key] = st.secrets[key]
        except Exception:
            pass
    if cfg.get("league_id"):
        cfg["league_id"] = _normalize_league_id(str(cfg["league_id"]))
    return cfg


def _normalize_league_id(raw: str) -> str:
    """Sleeper league IDs are numeric strings — strip spaces and accidental characters."""
    return re.sub(r"\D", "", (raw or "").strip())


def _needs_league_setup(config: dict) -> bool:
    league_id = _normalize_league_id(config.get("league_id") or "")
    username = (config.get("username") or "").strip()
    return (
        not league_id
        or league_id == "YOUR_LEAGUE_ID"
        or not username
        or username == "YOUR_SLEEPER_USERNAME"
    )


def _run_save_and_sync(config: dict, league_id: str, username: str, league_name: str) -> None:
    league_id = _normalize_league_id(league_id)
    username = (username or "").strip()
    if not league_id or not username:
        st.error("Enter league ID and username.")
        return
    if len(league_id) < 15:
        st.error(
            f"League ID looks too short ({len(league_id)} digits). "
            "Copy the **full** number from your Sleeper league URL — it is usually 18–19 digits."
        )
        return
    updated = {**config, "league_id": league_id, "username": username}
    if league_name:
        updated["league_name"] = league_name.strip()
    save_config(updated)
    try:
        with st.spinner("Syncing from Sleeper..."):
            analyst = DynastyAnalyst(updated)
            analyst.sync()
            analyst.news.close()
        save_config({**updated, **analyst.config})
        load_grades.clear()
        load_live_draft.clear()
        st.success("League synced!")
        st.rerun()
    except Exception as e:
        st.error(str(e))


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
        return {"rotowire": [], "injuries": []}
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
    inject_dynatyze_styles()
    inject_dynatyze_shell()
    st.markdown(
        """
        <style>
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


def _render_pick_cards(recs, *, highlight_first: bool = False, show_fit: bool = True) -> None:
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
            if show_fit:
                m1, m2, m3 = st.columns(3)
                m1.metric("ADP", _cell(r.adp))
                m2.metric("Fit", f"{r.fit_score:.0f}")
                m3.metric("Upside", f"{r.upside_score:.0f}" if r.upside_score else "—")
            else:
                m1, m2 = st.columns(2)
                m1.metric("ADP", _cell(r.adp))
                m2.metric("Upside", f"{r.upside_score:.0f}" if r.upside_score else "—")
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


def _board_insight(entry, *, show_fit: bool = True) -> str:
    parts = []
    if entry.upside_note:
        parts.append(_first_sentence(entry.upside_note))
    elif show_fit and entry.fit_reason:
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
    source_labels = {"rotowire": "@RotoWireNFL"}
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
    page_title=f"Dynatyze · Dynasty Analyst [{APP_BUILD}]",
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
            _run_save_and_sync(config, league_id, username, league_name)

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
if _needs_league_setup(config):
    st.title("Dynasty Fantasy Football Analyst")
    st.caption(
        "No league connected yet. Use the form below — or click the **›** arrow in the top-left to open the sidebar."
    )
    st.markdown("### Connect your Sleeper league")
    c1, c2 = st.columns(2)
    with c1:
        setup_league_id = st.text_input(
            "Sleeper League ID",
            value="" if config.get("league_id") == "YOUR_LEAGUE_ID" else config.get("league_id", ""),
            placeholder="1363674260144418816",
            help="Copy the full ID from sleeper.app/leagues/1363674260144418816 — all digits, usually 18–19 characters.",
            key="setup_league_id",
        )
    with c2:
        setup_username = st.text_input(
            "Your Sleeper username",
            value="" if config.get("username") == "YOUR_SLEEPER_USERNAME" else config.get("username", ""),
            placeholder="jon696969",
            key="setup_username",
        )
    setup_league_name = st.text_input(
        "League name (optional)",
        value=config.get("league_name", ""),
        key="setup_league_name",
    )
    if st.button("Save & Sync", type="primary", key="setup_save_sync"):
        _run_save_and_sync(config, setup_league_id, setup_username, setup_league_name)

    st.markdown(
        """
        **What you'll get after syncing**
        - **My Leagues** dashboard with lineup tools, depth chart, and waiver radar
        - **Rankings** — dynasty board, ADP, projections
        - **Trade Calc** — FantasyCalc-graded trades for your league
        - **Draft** — live pick recommendations and keeper-aware next pick
        """
    )
    st.stop()

try:
    analyst = DynastyAnalyst(config)
    analyst._ensure_snapshot()
    if not analyst.draft_state():
        analyst.refresh_draft()
except Exception as e:
    err = str(e)
    lid = config.get("league_id", "")
    if "404" in err and "sleeper" in err.lower():
        st.error(
            f"**League not found on Sleeper.** The app tried ID `{lid}` ({len(str(lid))} digits). "
            "Your ID is probably missing a digit — open your league on Sleeper and copy the **entire** number from the URL."
        )
        st.markdown(
            "Example: `https://sleeper.app/leagues/`**`1363674260144418816`** "
            "→ league ID is **`1363674260144418816`** (19 digits, ends in **6**)."
        )
    else:
        st.error(f"Could not load league: {e}")
    st.markdown("### Fix league connection")
    c1, c2 = st.columns(2)
    with c1:
        fix_id = st.text_input("Sleeper League ID", value=lid, key="fix_league_id")
    with c2:
        fix_user = st.text_input("Username", value=config.get("username", ""), key="fix_username")
    if st.button("Save & Sync", type="primary", key="fix_save_sync"):
        _run_save_and_sync(config, fix_id, fix_user, config.get("league_name", ""))
    st.stop()

overview = analyst.league_overview()
ctx = _draft_context(analyst, config)
draft = ctx["draft"]
teams = ctx["teams"]
my_slot = ctx["my_slot"]
has_keepers = ctx["show_keeper_ui"]
show_fit = not is_pre_draft(draft)
_, my_team_data = analyst._ensure_loaded()
dash = build_dashboard(analyst._ensure_snapshot(), my_team_data, config)
grades = load_grades(json.dumps(config, sort_keys=True))
init_navigation()

roster_rows = build_roster_rows(my_team_data, analyst.intel(), analyst.adp_map, grades)
nav_counts = section_counts(roster_rows, analyst._ensure_snapshot(), analyst.waiver_targets())

if st.session_state.get("sync_requested"):
    st.session_state.sync_requested = False
    try:
        with st.spinner("Syncing..."):
            analyst.sync()
            analyst.refresh_draft()
            analyst.news.close()
        load_grades.clear()
        load_live_draft.clear()
        st.rerun()
    except Exception as e:
        st.error(str(e))

with st.sidebar:
    st.divider()
    render_sidebar_league(dash, nav_counts, st.session_state.league_section)

render_top_nav(st.session_state.page)
st.markdown(
    f'<p style="color:#6b7280;font-size:0.68rem;margin:-0.25rem 0 0.35rem 0;">'
    f'Build <b style="color:#10b981;">{APP_BUILD}</b></p>',
    unsafe_allow_html=True,
)
page = st.session_state.page

if page == "dashboard":
    render_league_hub_nav(st.session_state.league_section)

# ── My Leagues / Dashboard ───────────────────────────────────────────────────

if page == "dashboard":
    try:
        if st.session_state.league_section == "Dashboard":
            from src.ui_platform import _fc_client

            dz = build_dynatyze_dashboard(
                analyst._ensure_snapshot(),
                my_team_data,
                config,
                _fc_client(analyst, config),
                grades,
                analyst.waiver_targets(),
                analyst.intel(),
                analyst.adp_map,
                dash,
            )
            render_dashboard_home(dz)
            st.markdown("##### Quick actions")
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                if st.button(f"Lineup · {dz.injury_count} hurt", use_container_width=True):
                    st.session_state.league_section = "Start/Sit"
                    st.rerun()
            with q2:
                if st.button("Waivers", use_container_width=True):
                    st.session_state.league_section = "Waiver Wire"
                    st.rerun()
            with q3:
                if st.button("Trades", use_container_width=True):
                    st.session_state.page = "trade"
                    st.rerun()
            with q4:
                if st.button(f"League · #{dz.value_rank}", use_container_width=True):
                    st.session_state.page = "league"
                    st.rerun()
        else:
            render_my_league(
                analyst, config, ctx, grades,
                section_override=st.session_state.league_section,
            )
    except Exception as e:
        st.error(f"Dashboard failed: {e}")

# ── Rankings ─────────────────────────────────────────────────────────────────

elif page == "rankings":
    try:
        render_rankings(analyst, config)
    except Exception as e:
        st.error(f"Rankings failed: {e}")

# ── Analytics ─────────────────────────────────────────────────────────────────

elif page == "analytics":
    try:
        render_analytics(analyst, config)
    except Exception as e:
        st.error(f"Analytics failed: {e}")

# ── Tools ─────────────────────────────────────────────────────────────────────

elif page == "tools":
    try:
        render_tools(analyst, config, ctx)
    except Exception as e:
        st.error(f"Tools failed: {e}")

# ── Draft ─────────────────────────────────────────────────────────────────────

elif page == "draft":
    try:
        render_live_draft(analyst, config, show_fit=show_fit)
    except Exception as e:
        st.error(f"Draft failed: {e}")

# ── My Team (League Hub) ──────────────────────────────────────────────────────

elif page == "trade":
    try:
        render_trade_calculator(analyst, config)
    except Exception as e:
        st.error(f"Trade calculator failed: {e}")

# ── League wire ───────────────────────────────────────────────────────────────

elif page == "league":
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

elif page == "news":
    try:
        section = st.radio(
            "Section",
            ["Headlines", "Waivers"],
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
            roster_only = st.toggle("My players only", value=False)
            news_df = _build_news_table(by_source, roster_names)
            if roster_only and not news_df.empty:
                news_df = news_df[news_df["Your Player"] != "—"]
            st.caption("@RotoWireNFL · Green = mentions someone on your roster.")
            _render_news_table(news_df)

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
