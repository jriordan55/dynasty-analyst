"""Live draft — available players table only."""

from __future__ import annotations

import re

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


def normalize_draft_id(raw: str | None) -> str | None:
    """Extract draft ID from a Sleeper URL or bare numeric ID."""
    if not raw:
        return None
    text = str(raw).strip()
    match = re.search(r"/draft/nfl/(\d+)", text)
    if match:
        return match.group(1)
    digits = re.sub(r"\D", "", text)
    return digits or None


def resolve_draft_id(config: dict) -> str | None:
    """Draft ID from tab input, URL query param, config, or last connected draft."""
    tab = normalize_draft_id(st.session_state.get("live_draft_input_id"))
    if tab:
        return tab
    for key in ("draft", "draft_id"):
        try:
            qp = st.query_params.get(key)
        except Exception:
            qp = None
        if qp:
            parsed = normalize_draft_id(qp if isinstance(qp, str) else str(qp))
            if parsed:
                return parsed
    cfg = normalize_draft_id(config.get("draft_id"))
    if cfg:
        return cfg
    return st.session_state.get("live_draft_selected_id")


def _init_draft_input(config: dict) -> None:
    if "live_draft_input_id" in st.session_state:
        return
    for key in ("draft", "draft_id"):
        try:
            qp = st.query_params.get(key)
        except Exception:
            qp = None
        if qp:
            parsed = normalize_draft_id(qp if isinstance(qp, str) else str(qp))
            if parsed:
                st.session_state["live_draft_input_id"] = parsed
                return
    cfg = normalize_draft_id(config.get("draft_id"))
    st.session_state["live_draft_input_id"] = cfg or ""


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
        pinned_draft_id=draft_id,
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

    _init_draft_input(config)
    st.text_input(
        "Sleeper draft ID or URL",
        key="live_draft_input_id",
        placeholder="Paste draft ID or sleeper.com/draft/nfl/… — leave blank for league auto-detect",
        label_visibility="visible",
    )

    draft_id = resolve_draft_id(config)

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
