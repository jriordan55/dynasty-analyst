"""Live draft UI — real-time Sleeper sync with pick / avoid guidance."""

from __future__ import annotations

import html
from datetime import timedelta

import streamlit as st

from src.draft import is_draft_live, is_pre_draft
from src.live_draft import LiveDraftAnalysis, analyze_live_draft, fetch_sleeper_draft, next_pick_label
from src.ui_dynatyze import _embed_html

LIVE_CSS = """
body { margin: 0; background: transparent; color: #e5e7eb; font-family: Montserrat, system-ui, sans-serif; }
.dz-live-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.85rem; }
.dz-live-title { margin: 0; color: #fff; font-size: 1.35rem; font-weight: 800; }
.dz-live-sub { color: #6b7280; font-size: 0.75rem; margin: 0.2rem 0 0 0; }
.dz-live-pulse { display: inline-flex; align-items: center; gap: 0.35rem; background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.35); color: #10b981; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; padding: 0.2rem 0.55rem; border-radius: 999px; text-transform: uppercase; }
.dz-live-pulse.off { background: #111827; border-color: #374151; color: #9ca3af; }
.dz-dot { width: 7px; height: 7px; border-radius: 999px; background: #10b981; animation: pulse 1.4s infinite; }
.dz-live-pulse.off .dz-dot { background: #6b7280; animation: none; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
.dz-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.65rem; margin-bottom: 0.85rem; }
@media (max-width: 800px) { .dz-metrics { grid-template-columns: repeat(2, 1fr); } }
.dz-metric { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.65rem; padding: 0.65rem 0.75rem; }
.dz-metric-label { color: #6b7280; font-size: 0.58rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 0.2rem 0; }
.dz-metric-val { color: #fff; font-size: 1rem; font-weight: 800; margin: 0; line-height: 1.2; }
.dz-metric-val.green { color: #10b981; }
.dz-metric-val.amber { color: #f59e0b; }
.dz-clock { border-radius: 0.75rem; padding: 0.85rem 1rem; margin-bottom: 0.85rem; border: 1px solid #374151; background: #0f1115; }
.dz-clock.on { border-color: rgba(16,185,129,0.55); background: rgba(16,185,129,0.08); }
.dz-clock.wait { border-color: #374151; }
.dz-clock-title { margin: 0; font-size: 0.95rem; font-weight: 800; color: #fff; }
.dz-clock-sub { margin: 0.25rem 0 0 0; color: #9ca3af; font-size: 0.75rem; }
.dz-grid { display: grid; grid-template-columns: 1.25fr 0.75fr; gap: 0.85rem; }
@media (max-width: 900px) { .dz-grid { grid-template-columns: 1fr; } }
.dz-panel { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 0.85rem; }
.dz-panel-title { color: #6b7280; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; margin: 0 0 0.65rem 0; }
.dz-pick { border: 1px solid #1f2937; border-radius: 0.65rem; padding: 0.65rem 0.75rem; margin-bottom: 0.55rem; background: #0a0a0a; }
.dz-pick.top { border-color: rgba(16,185,129,0.55); box-shadow: 0 0 0 1px rgba(16,185,129,0.15); }
.dz-pick-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.35rem; }
.dz-pick-name { color: #fff; font-weight: 800; font-size: 0.88rem; margin: 0; }
.dz-pick-rank { color: #10b981; font-size: 0.72rem; font-weight: 800; }
.dz-tags { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.35rem; }
.dz-tag { font-size: 0.55rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.1rem 0.35rem; border-radius: 999px; background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
.dz-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.35rem; margin-bottom: 0.35rem; }
@media (max-width: 700px) { .dz-stats { grid-template-columns: repeat(3, 1fr); } }
.dz-stat-trend { font-size: 0.48rem; font-weight: 700; margin-top: 0.05rem; }
.dz-stat-trend.green { color: #10b981; }
.dz-stat-trend.red { color: #f87171; }
.dz-movers { display: grid; grid-template-columns: 1fr 1fr; gap: 0.55rem; margin-bottom: 0.85rem; }
.dz-mover-panel { background: #0a0a0a; border: 1px solid #1f2937; border-radius: 0.55rem; padding: 0.55rem 0.65rem; }
.dz-mover-line { display: flex; justify-content: space-between; font-size: 0.62rem; padding: 0.2rem 0; color: #d1d5db; }
.dz-mover-line b { color: #fff; font-weight: 600; }
.dz-mover-up { color: #10b981; font-weight: 800; }
.dz-mover-down { color: #f87171; font-weight: 800; }
.dz-stat { text-align: center; background: #111827; border-radius: 0.45rem; padding: 0.25rem 0.15rem; }
.dz-stat-l { color: #6b7280; font-size: 0.52rem; font-weight: 700; text-transform: uppercase; }
.dz-stat-v { color: #fff; font-size: 0.78rem; font-weight: 800; }
.dz-reason { color: #9ca3af; font-size: 0.68rem; line-height: 1.4; margin: 0; }
.dz-avoid { border-left: 3px solid #ef4444; padding: 0.45rem 0.55rem; margin-bottom: 0.45rem; background: rgba(127,29,29,0.1); border-radius: 0 0.45rem 0.45rem 0; }
.dz-avoid.med { border-left-color: #f59e0b; background: rgba(120,53,15,0.12); }
.dz-avoid-name { color: #fff; font-weight: 700; font-size: 0.78rem; margin: 0; }
.dz-avoid-reason { color: #fca5a5; font-size: 0.65rem; margin: 0.15rem 0 0 0; line-height: 1.35; }
.dz-avoid.med .dz-avoid-reason { color: #fcd34d; }
.dz-needs { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.35rem; }
.dz-need { background: #111827; border: 1px solid #374151; color: #d1d5db; font-size: 0.62rem; font-weight: 700; padding: 0.15rem 0.45rem; border-radius: 999px; }
.dz-recent { max-height: 220px; overflow-y: auto; }
.dz-recent-row { display: grid; grid-template-columns: 2.5rem 1fr auto; gap: 0.45rem; padding: 0.35rem 0; border-bottom: 1px solid #1f2937; font-size: 0.68rem; }
.dz-recent-pick { color: #6b7280; font-weight: 700; }
.dz-recent-player { color: #fff; font-weight: 600; }
.dz-recent-mgr { color: #6b7280; text-align: right; white-space: nowrap; }
.dz-pos { display: inline-block; font-size: 0.58rem; font-weight: 800; padding: 0.05rem 0.3rem; border-radius: 0.25rem; margin-right: 0.25rem; }
.dz-pos-QB { background: #1e3a8a; color: #93c5fd; }
.dz-pos-RB { background: #14532d; color: #86efac; }
.dz-pos-WR { background: #581c87; color: #d8b4fe; }
.dz-pos-TE { background: #78350f; color: #fcd34d; }
.dz-hint { background: #111827; border: 1px solid #374151; border-radius: 0.55rem; padding: 0.55rem 0.75rem; color: #9ca3af; font-size: 0.68rem; line-height: 1.45; margin-bottom: 0.85rem; }
.dz-hint b { color: #10b981; }
.dz-draft-badge { display: inline-block; background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.35); color: #93c5fd; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.12rem 0.45rem; border-radius: 999px; margin-left: 0.35rem; text-transform: uppercase; }
.dz-draft-badge.mock { background: rgba(168,85,247,0.12); border-color: rgba(168,85,247,0.35); color: #d8b4fe; }
.dz-draft-badge.live { background: rgba(16,185,129,0.12); border-color: rgba(16,185,129,0.35); color: #10b981; }
"""

POS_CLASS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE"}


def _pos_span(pos: str) -> str:
    cls = POS_CLASS.get(pos, "WR")
    return f'<span class="dz-pos dz-pos-{cls}">{html.escape(pos)}</span>'


def _fmt_num(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.0f}"
    return str(val)


def _render_analysis_html(analysis) -> str:
    status = (analysis.status or "unknown").replace("_", " ").title()
    drafting = is_draft_live(analysis.draft) or analysis.status == "drafting"
    label = html.escape(analysis.draft_label or "League draft")
    badge_cls = "mock" if analysis.is_mock else ("live" if drafting else "")
    badge = f'<span class="dz-draft-badge {badge_cls}">{label}</span>'

    pulse = (
        '<span class="dz-live-pulse"><span class="dz-dot"></span> Connected</span>'
        if drafting else
        f'<span class="dz-live-pulse off">{html.escape(status)}</span>'
    )

    hint = ""
    if is_pre_draft(analysis.draft) and not analysis.is_mock:
        hint = (
            '<div class="dz-hint"><b>Ready when you are.</b> Start a '
            '<b>mock draft</b> or your <b>league draft</b> in the Sleeper app on your phone — '
            'this page stays connected once picks begin.</div>'
        )
    elif analysis.status == "complete":
        hint = '<div class="dz-hint">This draft board is complete. Start a new mock in Sleeper or wait for your league draft.</div>'

    if analysis.is_my_pick:
        clock_cls = "dz-clock on"
        clock_title = "You're on the clock — pick now"
        clock_sub = f"Pick {analysis.on_clock_pick} · Round {analysis.on_clock_round}"
    elif analysis.on_clock_pick:
        clock_cls = "dz-clock wait"
        clock_title = f"On clock: {html.escape(analysis.on_clock_manager)}"
        clock_sub = f"Pick {analysis.on_clock_pick} · Queue for {html.escape(next_pick_label(analysis))}"
    elif is_pre_draft(analysis.draft):
        clock_cls = "dz-clock wait"
        clock_title = "Waiting for draft to start on Sleeper"
        clock_sub = f"Your slot {analysis.my_slot or '—'} · Queue for {html.escape(next_pick_label(analysis))}"
    else:
        clock_cls = "dz-clock wait"
        clock_title = "Draft board syncing"
        clock_sub = next_pick_label(analysis)

    pick_title = "Pick now" if analysis.is_my_pick else f"Queue · {next_pick_label(analysis)}"

    pick_blocks = []
    for p in analysis.picks:
        top = " top" if p.rank == 1 and analysis.is_my_pick else ""
        tags = "".join(f'<span class="dz-tag">{html.escape(t)}</span>' for t in p.tags)
        ch = p.adp_change_7d
        trend_cls = "green" if ch < 0 else ("red" if ch > 0 else "")
        trend_txt = f"{p.adp_momentum_arrow}{abs(ch):.1f}" if ch else p.adp_momentum_arrow
        vgs_trend = ""
        if p.vgs_trend:
            vgs_trend = f'<div class="dz-stat-trend green">↗{p.vgs_trend:+.0f}</div>' if p.vgs_trend > 0 else f'<div class="dz-stat-trend red">↘{p.vgs_trend:+.0f}</div>'
        vegas_cell = (
            f'<div class="dz-stat"><div class="dz-stat-l">VGS</div>'
            f'<div class="dz-stat-v">{p.vgs}</div>{vgs_trend}</div>'
            if p.vgs else
            f'<div class="dz-stat"><div class="dz-stat-l">Vegas</div>'
            f'<div class="dz-stat-v">{p.vegas_edge:+.0f}</div></div>'
        )
        fc_cell = (
            f'<div class="dz-stat"><div class="dz-stat-l">FC</div>'
            f'<div class="dz-stat-v">{p.fc_value:,}</div></div>'
            if p.fc_value else
            f'<div class="dz-stat"><div class="dz-stat-l">Grade</div>'
            f'<div class="dz-stat-v">{html.escape(p.grade)}</div></div>'
        )
        pick_blocks.append(
            f'<div class="dz-pick{top}">'
            f'<div class="dz-pick-head"><p class="dz-pick-name">{_pos_span(p.position)}{html.escape(p.player)}</p>'
            f'<span class="dz-pick-rank">#{p.rank}</span></div>'
            f'<div class="dz-tags">{tags}</div>'
            f'<div class="dz-stats">'
            f'<div class="dz-stat"><div class="dz-stat-l">ADP</div><div class="dz-stat-v">{_fmt_num(p.adp)}</div>'
            f'<div class="dz-stat-trend {trend_cls}">{html.escape(trend_txt)}</div></div>'
            f'<div class="dz-stat"><div class="dz-stat-l">Fit</div><div class="dz-stat-v">{_fmt_num(p.fit_score)}</div></div>'
            f'<div class="dz-stat"><div class="dz-stat-l">Upside</div><div class="dz-stat-v">{_fmt_num(p.upside_score)}</div></div>'
            f'{vegas_cell}'
            f'{fc_cell}'
            f'</div>'
            f'<p class="dz-reason">{html.escape(p.reason)}</p></div>'
        )
    if not pick_blocks:
        pick_blocks.append('<div class="dz-empty">No recommendations — refresh or sync league data.</div>')

    avoid_blocks = []
    for a in analysis.avoids:
        cls = "dz-avoid" if a.severity == "high" else "dz-avoid med"
        avoid_blocks.append(
            f'<div class="{cls}"><p class="dz-avoid-name">{_pos_span(a.position)}{html.escape(a.player)}'
            f' <span style="color:#6b7280;font-weight:500;">ADP {_fmt_num(a.adp)}</span></p>'
            f'<p class="dz-avoid-reason">{html.escape(a.reason)}</p></div>'
        )
    if not avoid_blocks:
        avoid_blocks.append('<div class="dz-empty">No major red flags in your pick window.</div>')

    needs = "".join(f'<span class="dz-need">{html.escape(p)}</span>' for p in analysis.draft_priorities[:5])
    next_picks = " · ".join(str(p) for p in analysis.next_picks[:4]) or "—"

    recent_rows = []
    for rp in analysis.recent_picks:
        recent_rows.append(
            f'<div class="dz-recent-row">'
            f'<span class="dz-recent-pick">{rp.get("pick_no", "—")}</span>'
            f'<span class="dz-recent-player">{_pos_span(rp.get("position") or "")}{html.escape(rp.get("player_name") or "—")}</span>'
            f'<span class="dz-recent-mgr">{html.escape(rp.get("manager") or "")}</span></div>'
        )
    recent_html = "".join(recent_rows) or '<div class="dz-empty">No picks yet.</div>'

    def _mover_lines(items, cls_up: str) -> str:
        if not items:
            return '<div class="dz-mover-line"><span>—</span></div>'
        out = ""
        for m in items[:5]:
            delta = f"{m.arrow} {abs(m.change_7d):.1f}"
            out += f'<div class="dz-mover-line"><b>{html.escape(m.player)}</b><span class="{cls_up}">{html.escape(delta)}</span></div>'
        return out

    movers_html = ""
    if analysis.risers or analysis.fallers:
        movers_html = (
            f'<div class="dz-movers">'
            f'<div class="dz-mover-panel"><p class="dz-panel-title">7d ADP risers</p>{_mover_lines(analysis.risers, "dz-mover-up")}</div>'
            f'<div class="dz-mover-panel"><p class="dz-panel-title">7d ADP fallers</p>{_mover_lines(analysis.fallers, "dz-mover-down")}</div>'
            f'</div>'
        )

    progress_pct = 0
    if analysis.total_picks:
        progress_pct = round(100 * analysis.completed_picks / analysis.total_picks)

    return f"""
    <div class="dz-live-head">
      <div>
        <h2 class="dz-live-title">Live Draft Assistant {badge}</h2>
        <p class="dz-live-sub">Sleeper sync · {html.escape(analysis.draft_type or 'snake')} · Updated {html.escape(analysis.updated_at)}</p>
      </div>
      {pulse}
    </div>
    {hint}
    <div class="dz-metrics">
      <div class="dz-metric"><p class="dz-metric-label">Status</p><p class="dz-metric-val">{html.escape(status)}</p></div>
      <div class="dz-metric"><p class="dz-metric-label">Progress</p><p class="dz-metric-val">{analysis.completed_picks}/{analysis.total_picks}</p></div>
      <div class="dz-metric"><p class="dz-metric-label">Your slot</p><p class="dz-metric-val">{_fmt_num(analysis.my_slot)}</p></div>
      <div class="dz-metric"><p class="dz-metric-label">Board</p><p class="dz-metric-val">{progress_pct}%</p></div>
    </div>
    <div class="{clock_cls}">
      <p class="dz-clock-title">{clock_title}</p>
      <p class="dz-clock-sub">{clock_sub}</p>
      <div class="dz-needs"><span class="dz-need" style="border-color:#10b981;color:#10b981;">Priorities</span>{needs}</div>
      <p class="dz-clock-sub" style="margin-top:0.45rem;">Your next picks: {html.escape(next_picks)}</p>
    </div>
    {movers_html}
    <div class="dz-grid">
      <div class="dz-panel">
        <p class="dz-panel-title">{html.escape(pick_title)}</p>
        {"".join(pick_blocks)}
      </div>
      <div>
        <div class="dz-panel" style="margin-bottom:0.85rem;">
          <p class="dz-panel-title">Avoid at this pick</p>
          {"".join(avoid_blocks)}
        </div>
        <div class="dz-panel">
          <p class="dz-panel-title">Recent picks</p>
          <div class="dz-recent">{recent_html}</div>
        </div>
      </div>
    </div>
    """


def _render_on_clock_banner(analysis: LiveDraftAnalysis) -> None:
    """Native Streamlit alert — always visible outside the HTML iframe."""
    if analysis.is_my_pick:
        st.success(
            f"**YOU'RE ON THE CLOCK** — Pick **{analysis.on_clock_pick}** "
            f"(Round {analysis.on_clock_round}) · {analysis.draft_label}"
        )
    elif is_draft_live(analysis.draft) and analysis.on_clock_pick:
        st.info(
            f"On clock: **{analysis.on_clock_manager}** · Pick **{analysis.on_clock_pick}** · "
            f"Your queue below for {next_pick_label(analysis)}"
        )


def _draw_live_board(analyst, config: dict, show_fit: bool) -> LiveDraftAnalysis | None:
    try:
        draft = fetch_sleeper_draft(config["league_id"], config.get("username", ""))
        if draft and analyst._snapshot is not None:
            analyst._snapshot["draft"] = draft
        analysis = analyze_live_draft(analyst, config, draft=draft)
    except Exception as exc:
        st.error(f"Could not sync live draft: {exc}")
        return None

    if not analysis.draft:
        st.info("No Sleeper draft found for this league yet. Start a mock or league draft in the Sleeper app.")
        return analysis

    if not analysis.my_slot:
        st.warning(
            "Could not match your Sleeper username to a draft slot. "
            "Open **League settings** in the sidebar and confirm your username matches Sleeper exactly."
        )

    _render_on_clock_banner(analysis)

    live_show_fit = not is_pre_draft(analysis.draft)

    board_sig = (
        analysis.draft.get("draft_id"),
        analysis.completed_picks,
        analysis.on_clock_pick,
        analysis.is_my_pick,
        analysis.status,
    )
    prev_sig = st.session_state.get("live_draft_board_sig")
    board_changed = prev_sig != board_sig or "live_draft_board_slot" not in st.session_state
    if board_changed:
        st.session_state["live_draft_board_sig"] = board_sig
        height = 1020 if analysis.is_my_pick else 960
        if "live_draft_board_slot" not in st.session_state:
            st.session_state["live_draft_board_slot"] = st.empty()
        with st.session_state["live_draft_board_slot"].container():
            _embed_html(_render_analysis_html(analysis), css=LIVE_CSS, height=height)

    if not live_show_fit and not show_fit:
        st.caption("Roster-fit scoring turns on automatically when your mock or league draft goes live on Sleeper.")
    elif live_show_fit and not show_fit:
        st.caption("Live draft detected — roster-fit scoring is active.")

    return analysis


def render_live_draft(analyst, config: dict, *, show_fit: bool = True) -> None:
    """Live draft page — stays connected via background fragment polling."""
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Refresh now", type="primary", use_container_width=True):
            st.cache_data.clear()
            analyst.refresh_draft()
            st.session_state.pop("live_draft_board_sig", None)
            st.rerun()
    with c2:
        stay_connected = st.toggle("Stay connected", value=True, key="live_draft_stay_connected")
    with c3:
        st.caption(
            "Leave this open while drafting in Sleeper — picks and on-clock update in the background."
        )

    if stay_connected:
        try:
            @st.fragment(run_every=timedelta(seconds=5))
            def _connected_board() -> None:
                _draw_live_board(analyst, config, show_fit)

            _connected_board()
        except TypeError:
            _draw_live_board(analyst, config, show_fit)
    else:
        _draw_live_board(analyst, config, show_fit)
