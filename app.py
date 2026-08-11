"""Dynasty Fantasy Football Analyst — web app."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analyst import DynastyAnalyst, load_config

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
    return base


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
                st.success("League synced!")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.markdown("**Quick links**")
    st.markdown("- [Find league ID on Sleeper](https://sleeper.app)")
    st.markdown("- [4for4 ADP rankings](https://www.4for4.com/adp)")

    st.markdown("- [@RotoWireNFL on X](https://x.com/RotoWireNFL)")
    st.markdown("- [@UnderdogNFL on X](https://x.com/UnderdogNFL)")

if not CONFIG_PATH.exists() or not get_config().get("league_id") or get_config().get("league_id") == "YOUR_LEAGUE_ID":
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
    analyst = DynastyAnalyst(get_config())
    analyst.sync()
except Exception as e:
    st.error(f"Could not load league: {e}")
    st.stop()

tab_overview, tab_grades, tab_sell, tab_trades, tab_waivers, tab_news = st.tabs(
    ["League Map", "My Grades", "Sell Alerts", "Trade Targets", "Waivers", "Fantasy News"]
)

with tab_overview:
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
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    my = data.get("my_needs")
    if my:
        c1, c2, c3 = st.columns(3)
        c1.metric("Your Team", data["my_team"])
        c2.metric("Desperate For", ", ".join(my.desperate_for) or "None")
        c3.metric("Surplus", ", ".join(f"{k} (+{v})" for k, v in my.surplus.items()) or "None")

with tab_grades:
    grades = analyst.grade_my_roster()
    df = pd.DataFrame([{
        "Player": g["name"],
        "Pos": g["position"],
        "ADP": g["adp"] or "—",
        "Age": g["age"] or "—",
        "Grade": g["grade"],
        "Notes": "; ".join(g["notes"]),
    } for g in grades])
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_sell:
    sells = analyst.sell_candidates()
    if not sells:
        st.success("No urgent sell candidates.")
    else:
        for s in sells:
            color = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.urgency, "")
            st.warning(f"{color} **{s.player}** ({s.position}, ADP {s.adp or 'N/A'}) — {s.reason}")

with tab_trades:
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

with tab_waivers:
    waivers = analyst.waiver_targets()
    df = pd.DataFrame([{
        "Player": w.player,
        "Pos": w.position,
        "ADP": w.adp or "—",
        "Why": w.reason,
    } for w in waivers[:15]])
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_news:
    try:
        by_source = analyst.news.get_news_by_source()
    except Exception as e:
        st.error(f"Could not load news feeds: {e}")
        by_source = {}

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("@RotoWireNFL")
        st.caption("[x.com/RotoWireNFL](https://x.com/RotoWireNFL)")
        for n in by_source.get("rotowire", [])[:10]:
            st.markdown(f"**{n['headline']}**")
            if n.get("description"):
                st.caption(n["description"][:220])
            if n.get("link"):
                st.markdown(f"[Read more]({n['link']})")
            st.divider()
    with col2:
        st.subheader("@UnderdogNFL")
        st.caption("[x.com/UnderdogNFL](https://x.com/UnderdogNFL)")
        for n in by_source.get("underdog", [])[:10]:
            st.markdown(f"**{n['headline']}**")
            if n.get("link"):
                st.markdown(f"[Read more]({n['link']})")
            st.divider()
    with col3:
        st.subheader("ESPN")
        for n in by_source.get("espn", [])[:10]:
            st.markdown(f"**{n['headline']}**")
            if n.get("link"):
                st.markdown(f"[Read more]({n['link']})")
            st.divider()

st.divider()
with st.expander("Export context for Claude / Cursor chat"):
    st.code(analyst.build_context(), language="markdown")
