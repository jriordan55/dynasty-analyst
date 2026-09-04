"""Live draft — available players table only."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.live_draft import analyze_live_draft, fetch_sleeper_draft

COLUMN_HELP = {
    "Pick": "★ = recommended for your next snake pick.",
    "Player": "Player name.",
    "Pos": "Position (QB, RB, WR, TE).",
    "Team": "NFL team.",
    "ADP": "Average draft position.",
    "7d ADP": "7-day ADP change — ↗ riser, ↘ faller, → stable.",
    "Fit": "Roster fit score (0–100) based on who you have already drafted.",
    "Upside": "Upside score from role, age, news, and trends.",
    "FC": "FantasyCalc dynasty value.",
    "VGS": "Vegas signal score from books vs model.",
    "Vegas": "Vegas point edge — positive means model likes player vs books.",
    "Grade": "Quick draft grade (A–F) from ADP, upside, and injury.",
    "Tags": "VALUE, NEED, RISER, VEGAS+, etc.",
    "Notes": "Fit reason, injury flag, or intel note.",
}


def _available_dataframe(analysis) -> pd.DataFrame:
    rows = []
    for p in analysis.available:
        rows.append({
            "Pick": "★" if p.recommend else "",
            "Player": p.player,
            "Pos": p.position,
            "Team": p.team,
            "ADP": p.adp,
            "7d ADP": f"{p.adp_arrow}{abs(p.adp_change_7d):.1f}" if p.adp_change_7d else p.adp_arrow,
            "Fit": round(p.fit_score, 1),
            "Upside": round(p.upside_score, 1),
            "FC": p.fc_value,
            "VGS": p.vgs,
            "Vegas": f"{p.vegas_edge:+.0f}" if p.vegas_edge else "",
            "Grade": p.grade,
            "Tags": ", ".join(p.tags),
            "Notes": p.note,
        })
    return pd.DataFrame(rows)


def _load_analysis(analyst, config: dict, draft_id: str | None):
    draft = fetch_sleeper_draft(
        config["league_id"],
        config.get("username", ""),
        draft_id=draft_id,
    )
    if draft and analyst._snapshot is not None:
        analyst._snapshot["draft"] = draft
    if draft and draft.get("draft_id"):
        st.session_state["live_draft_selected_id"] = draft["draft_id"]
    return analyze_live_draft(analyst, config, draft=draft)


def render_live_draft(analyst, config: dict, *, show_fit: bool = True) -> None:
    """Available players table — auto-syncs with Sleeper every 5 seconds."""
    try:
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=5000, limit=None, key="live_draft_poll")
    except ImportError:
        pass

    draft_id = st.session_state.get("live_draft_selected_id")

    try:
        analysis = _load_analysis(analyst, config, draft_id)
    except Exception as exc:
        st.error(str(exc))
        return

    df = _available_dataframe(analysis) if analysis else pd.DataFrame()
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(720, 40 + max(len(df), 1) * 35),
    )

    st.markdown("**Column definitions**")
    for col, desc in COLUMN_HELP.items():
        st.markdown(f"- **{col}** — {desc}")
