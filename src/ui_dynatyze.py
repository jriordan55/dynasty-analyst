"""Dynatyze.com shell — top nav, sidebar, dashboard layout."""

from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from src.dynatyze_dashboard import DynatyzeDashboard
from src.my_league import section_counts, build_roster_rows, injury_report, bye_week_board
from src.version import APP_BUILD

NAV_PAGES = [
    ("dashboard", "My Leagues"),
    ("trade", "Trade Calc"),
    ("rankings", "Rankings"),
    ("analytics", "Analytics"),
    ("tools", "Tools"),
    ("draft", "Draft"),
    ("news", "News"),
]

DASHBOARD_CSS = """
.dz-updated { color: #fbbf24; font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; text-align: right; margin-bottom: 0.35rem; }
.dz-kicker { color: #10b981; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; margin: 0; }
.dz-story { color: #f9fafb; font-size: clamp(1.35rem, 2.5vw, 2rem); font-weight: 800; line-height: 1.2; margin: 0.35rem 0 0.75rem 0; max-width: 52rem; }
.dz-team-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; }
.dz-team-name { color: #fff; font-size: 1.15rem; font-weight: 700; margin: 0; }
.dz-pill { background: #111827; border: 1px solid #374151; color: #9ca3af; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em; padding: 0.2rem 0.55rem; border-radius: 999px; text-transform: uppercase; }
.dz-grid-main { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 1.25rem; margin-top: 0.5rem; }
.dz-panel { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.85rem; padding: 1rem; }
.dz-panel-title { color: #6b7280; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; margin: 0 0 0.85rem 0; }
.dz-faces { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.85rem; }
.dz-face { text-align: center; }
.dz-face-ring { width: 74px; height: 74px; border-radius: 999px; padding: 3px; margin: 0 auto 0.45rem auto; background: linear-gradient(135deg, var(--ring), #111827); }
.dz-face img { width: 68px; height: 68px; border-radius: 999px; object-fit: cover; background: #111827; display: block; margin: 0 auto; }
.dz-face-name { color: #fff; font-size: 0.82rem; font-weight: 700; margin: 0; }
.dz-face-val { color: #6b7280; font-size: 0.72rem; margin: 0.1rem 0 0 0; }
.dz-gauge-wrap { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
.dz-gauge { width: 110px; height: 110px; border-radius: 999px; display: grid; place-items: center; background: conic-gradient(#10b981 calc(var(--pct) * 1%), #1f2937 0); }
.dz-gauge-inner { width: 82px; height: 82px; border-radius: 999px; background: #0f1115; display: grid; place-items: center; text-align: center; }
.dz-gauge-rank { color: #fff; font-size: 0.95rem; font-weight: 800; line-height: 1.1; }
.dz-gauge-val { color: #10b981; font-size: 0.72rem; font-weight: 700; }
.dz-pos-row { margin-bottom: 0.75rem; }
.dz-pos-head { display: flex; justify-content: space-between; color: #d1d5db; font-size: 0.72rem; margin-bottom: 0.25rem; }
.dz-bar { height: 8px; background: #1f2937; border-radius: 999px; overflow: hidden; }
.dz-bar-fill { height: 100%; border-radius: 999px; }
.dz-insight { color: #10b981; font-size: 0.78rem; line-height: 1.45; margin-top: 0.75rem; }
.dz-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-top: 1rem; }
.dz-card { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 0.85rem; min-height: 92px; }
.dz-card-title { color: #fff; font-size: 0.95rem; font-weight: 700; margin: 0.35rem 0 0.15rem 0; }
.dz-card-sub { color: #6b7280; font-size: 0.72rem; margin: 0; }
.dz-card-badge { display: inline-block; background: #111827; border: 1px solid #374151; color: #d1d5db; font-size: 0.62rem; padding: 0.12rem 0.45rem; border-radius: 999px; margin-top: 0.35rem; }
body { margin: 0; background: transparent; color: #e5e7eb; font-family: Montserrat, system-ui, sans-serif; }
"""

SIDEBAR_SECTIONS = [
    ("Dashboard", "dashboard"),
    ("My Team", "My Team"),
    ("Injury Report", "Injury Report"),
    ("Bye Weeks", "Bye Weeks"),
    ("Start/Sit", "Start/Sit"),
    ("Depth Chart", "Depth Chart"),
    ("Bench Ledger", "Bench Ledger"),
    ("Waiver Wire", "Waiver Wire"),
]


def inject_dynatyze_shell() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', system-ui, sans-serif; }
        #MainMenu, footer, header { visibility: hidden; height: 0; }
        .block-container { padding-top: 0.5rem; max-width: 100%; padding-left: 1rem; padding-right: 1rem; }
        section[data-testid="stSidebar"] {
            background: #0a0a0a !important;
            border-right: 1px solid #1f2937;
            min-width: 260px !important;
            width: 260px !important;
        }
        section[data-testid="stSidebar"] .stMarkdown h3 { color: #f9fafb; font-size: 0.95rem; }
        section[data-testid="stSidebar"] .stCaption { color: #9ca3af !important; }
        .dz-topnav {
            display: flex; align-items: center; justify-content: space-between;
            background: #000; border-bottom: 1px solid #1f2937;
            padding: 0.65rem 1rem; margin: -0.5rem -1rem 1rem -1rem;
        }
        .dz-logo { color: #fff; font-weight: 800; letter-spacing: 0.08em; font-size: 0.95rem; }
        .dz-logo span { color: #10b981; }
        .dz-nav-links { display: flex; gap: 1.25rem; flex-wrap: wrap; }
        .dz-nav-links a { color: #d1d5db; text-decoration: none; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
        .dz-nav-links a.active { color: #10b981; }
        .dz-kicker { color: #10b981; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; margin: 0; }
        .dz-story { color: #f9fafb; font-size: clamp(1.35rem, 2.5vw, 2rem); font-weight: 800; line-height: 1.2; margin: 0.35rem 0 0.75rem 0; max-width: 52rem; }
        .dz-team-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; }
        .dz-team-name { color: #fff; font-size: 1.15rem; font-weight: 700; margin: 0; }
        .dz-pill { background: #111827; border: 1px solid #374151; color: #9ca3af; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em; padding: 0.2rem 0.55rem; border-radius: 999px; text-transform: uppercase; }
        .dz-grid-main { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 1.25rem; margin-top: 0.5rem; }
        @media (max-width: 900px) { .dz-grid-main { grid-template-columns: 1fr; } }
        .dz-panel { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.85rem; padding: 1rem; }
        .dz-panel-title { color: #6b7280; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; margin: 0 0 0.85rem 0; }
        .dz-faces { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.85rem; }
        @media (max-width: 700px) { .dz-faces { grid-template-columns: repeat(2, 1fr); } }
        .dz-face { text-align: center; }
        .dz-face-ring { width: 74px; height: 74px; border-radius: 999px; padding: 3px; margin: 0 auto 0.45rem auto; background: linear-gradient(135deg, var(--ring), #111827); }
        .dz-face img { width: 68px; height: 68px; border-radius: 999px; object-fit: cover; background: #111827; display: block; }
        .dz-face-name { color: #fff; font-size: 0.82rem; font-weight: 700; margin: 0; }
        .dz-face-val { color: #6b7280; font-size: 0.72rem; margin: 0.1rem 0 0 0; }
        .dz-gauge-wrap { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
        .dz-gauge {
            width: 110px; height: 110px; border-radius: 999px; display: grid; place-items: center;
            background: conic-gradient(#10b981 calc(var(--pct) * 1%), #1f2937 0);
            position: relative;
        }
        .dz-gauge-inner {
            width: 82px; height: 82px; border-radius: 999px; background: #0f1115;
            display: grid; place-items: center; text-align: center;
        }
        .dz-gauge-rank { color: #fff; font-size: 0.95rem; font-weight: 800; line-height: 1.1; }
        .dz-gauge-val { color: #10b981; font-size: 0.72rem; font-weight: 700; }
        .dz-pos-row { margin-bottom: 0.75rem; }
        .dz-pos-head { display: flex; justify-content: space-between; color: #d1d5db; font-size: 0.72rem; margin-bottom: 0.25rem; }
        .dz-bar { height: 8px; background: #1f2937; border-radius: 999px; overflow: hidden; }
        .dz-bar-fill { height: 100%; border-radius: 999px; }
        .dz-insight { color: #10b981; font-size: 0.78rem; line-height: 1.45; margin-top: 0.75rem; }
        .dz-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-top: 1rem; }
        @media (max-width: 900px) { .dz-cards { grid-template-columns: repeat(2, 1fr); } }
        .dz-card { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 0.85rem; min-height: 92px; }
        .dz-card-title { color: #fff; font-size: 0.95rem; font-weight: 700; margin: 0.35rem 0 0.15rem 0; }
        .dz-card-sub { color: #6b7280; font-size: 0.72rem; margin: 0; }
        .dz-card-badge { display: inline-block; background: #111827; border: 1px solid #374151; color: #d1d5db; font-size: 0.62rem; padding: 0.12rem 0.45rem; border-radius: 999px; margin-top: 0.35rem; }
        .dz-updated { color: #fbbf24; font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase; text-align: right; margin-bottom: 0.35rem; }
        div[data-testid="stSidebar"] button[kind="secondary"] {
            width: 100%; text-align: left; background: transparent !important; color: #d1d5db !important;
            border: 1px solid #374151 !important; margin-bottom: 0.25rem;
        }
        div[data-testid="stSidebar"] button[kind="primary"] {
            width: 100%; text-align: left; background: #111827 !important; color: #10b981 !important;
            border: 1px solid #10b981 !important; margin-bottom: 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_nav(current: str) -> None:
    st.markdown(
        '<div style="background:#000;border-bottom:1px solid #1f2937;padding:0.5rem 0 0.75rem 0;margin:-0.5rem 0 0.5rem 0;">'
        '<span style="color:#fff;font-weight:800;letter-spacing:0.08em;font-size:0.95rem;">DYNATY'
        '<span style="color:#10b981;">ZE</span></span></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(NAV_PAGES))
    for i, (key, label) in enumerate(NAV_PAGES):
        with cols[i]:
            btn_type = "primary" if key == current else "secondary"
            if st.button(label, key=f"nav_{key}", use_container_width=True, type=btn_type):
                st.session_state.page = key
                if key == "dashboard":
                    st.session_state.league_section = "Dashboard"
                st.rerun()


def render_sidebar_league(dash, counts: dict, current_section: str) -> None:
    st.markdown(f"### {dash.league_name}")
    st.caption(f"{dash.format_label} · {dash.num_teams} teams · {dash.season}")
    st.text_input("Jump to any tool…", placeholder="Search", label_visibility="collapsed", disabled=True)
    st.markdown(f"**{dash.team_name}**")
    st.caption(f"{dash.record} · #{dash.rank}")

    badges = {
        "Injury Report": counts.get("injuries", 0),
        "Waiver Wire": counts.get("waiver_adds", 0),
    }
    for label, section_key in SIDEBAR_SECTIONS:
        badge = badges.get(section_key)
        text = f"{label} ({badge})" if badge else label
        btn_type = "primary" if section_key == current_section else "secondary"
        if st.button(text, key=f"sb_{section_key}", use_container_width=True, type=btn_type):
            st.session_state.page = "dashboard"
            st.session_state.league_section = section_key
            st.rerun()

    if st.button("League Wire", key="sb_league_wire", use_container_width=True, type="secondary"):
        st.session_state.page = "league"
        st.rerun()

    if st.button("SYNC", use_container_width=True, type="primary"):
        st.session_state.sync_requested = True
    st.caption(f"Updated recently · Build {APP_BUILD}")


def _face_html(face) -> str:
    img = (
        f'<img src="{html.escape(face.headshot)}" alt="{html.escape(face.last_name)}" '
        f'onerror="this.style.display=\'none\'">'
        if face.headshot else
        f'<div style="width:68px;height:68px;border-radius:999px;background:#111827;display:grid;place-items:center;color:#fff;font-weight:700;">{html.escape(face.position)}</div>'
    )
    return (
        f'<div class="dz-face"><div class="dz-face-ring" style="--ring:{face.color}">{img}</div>'
        f'<p class="dz-face-name">{html.escape(face.last_name)}</p>'
        f'<p class="dz-face-val">{html.escape(face.value_label)}</p></div>'
    )


def render_dashboard_home(data: DynatyzeDashboard) -> None:
    faces = "".join(_face_html(f) for f in data.faces)
    pos_rows = ""
    for p in data.positions:
        pos_rows += (
            f'<div class="dz-pos-row"><div class="dz-pos-head"><span>{p.label}</span>'
            f'<span>{_ordinal_html(p.rank)} of {p.total_teams}</span></div>'
            f'<div class="dz-bar"><div class="dz-bar-fill" style="width:{p.pct:.0f}%;background:{p.color}"></div></div></div>'
        )

    html_block = f"""
    <div class="dz-updated">Updated recently</div>
    <p class="dz-kicker">{html.escape(data.storyline_kicker)}</p>
    <p class="dz-story">{html.escape(data.storyline)}</p>
    <div class="dz-team-row">
        <p class="dz-team-name">{html.escape(data.team_name)}</p>
        <span class="dz-pill">Dynasty Value</span>
    </div>
    <div class="dz-grid-main">
        <div class="dz-panel">
            <p class="dz-panel-title">The Faces</p>
            <div class="dz-faces">{faces}</div>
        </div>
        <div class="dz-panel">
            <p class="dz-panel-title">Power Order · Dynasty Value</p>
            <div class="dz-gauge-wrap">
                <div class="dz-gauge" style="--pct:{data.gauge_pct:.0f}">
                    <div class="dz-gauge-inner">
                        <div>
                            <div class="dz-gauge-rank">{_ordinal_html(data.value_rank)}<br>OF {data.total_teams}</div>
                            <div class="dz-gauge-val">{html.escape(data.total_value_label)}</div>
                        </div>
                    </div>
                </div>
            </div>
            {pos_rows}
            <p class="dz-insight">{html.escape(data.insight)}</p>
        </div>
    </div>
    <div class="dz-cards">
    """
    for card in data.quick_cards:
        html_block += (
            f'<div class="dz-card"><div>{html.escape(card.icon)}</div>'
            f'<p class="dz-card-title">{html.escape(card.title)}</p>'
            f'<p class="dz-card-sub">{html.escape(card.subtitle)}</p>'
            f'<span class="dz-card-badge">{html.escape(card.badge)}</span></div>'
        )
    html_block += "</div>"
    st.markdown(f"<style>{DASHBOARD_CSS}</style>{html_block}", unsafe_allow_html=True)


def _ordinal_html(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def init_navigation() -> None:
    st.session_state.setdefault("page", "dashboard")
    st.session_state.setdefault("league_section", "Dashboard")
