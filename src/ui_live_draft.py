"""Live draft UI — Sleeper sync, available-player table, timing advice."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from src.draft import is_draft_live, is_pre_draft
from src.live_draft import LiveDraftAnalysis, analyze_live_draft, fetch_sleeper_draft, next_pick_label


def _verdict_emoji(verdict: str) -> str:
    return {"GO": "🟢", "WAIT": "🟡", "NEUTRAL": "⚪"}.get(verdict, "⚪")


def _available_dataframe(analysis: LiveDraftAnalysis) -> pd.DataFrame:
    rows = []
    for p in analysis.available:
        rows.append({
            "Pick": "★" if p.recommend else "",
            "Player": p.player,
            "Pos": p.position,
            "Team": p.team,
            "ADP": p.adp,
            "7d ADP": f"{p.adp_arrow}{abs(p.adp_change_7d):.1f}" if p.adp_change_7d else p.adp_arrow,
            "Fit": round(p.fit_score, 1) if p.fit_score else None,
            "Upside": round(p.upside_score, 1) if p.upside_score else None,
            "FC": p.fc_value,
            "VGS": p.vgs,
            "Vegas": f"{p.vegas_edge:+.0f}" if p.vegas_edge else None,
            "Grade": p.grade,
            "Tags": ", ".join(p.tags),
            "Notes": p.note,
        })
    return pd.DataFrame(rows)


def _render_status_bar(analysis: LiveDraftAnalysis) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    status = (analysis.status or "unknown").replace("_", " ").title()
    connected = is_draft_live(analysis.draft) or analysis.status == "drafting"
    progress = 0
    if analysis.total_picks:
        progress = round(100 * analysis.completed_picks / analysis.total_picks)
    c1.metric("Status", status, delta="Connected" if connected else None, delta_color="normal")
    c2.metric("Progress", f"{analysis.completed_picks}/{analysis.total_picks}")
    c3.metric("Your slot", analysis.my_slot or "—")
    c4.metric("Board", f"{progress}%")
    c5.metric("Updated", analysis.updated_at.split()[0] if analysis.updated_at else "—")


def _render_on_clock_banner(analysis: LiveDraftAnalysis) -> None:
    if analysis.is_my_pick:
        st.success(
            f"**YOU'RE ON THE CLOCK** — Pick **{analysis.on_clock_pick}** "
            f"(Round {analysis.on_clock_round}) · {analysis.draft_label}"
        )
    elif is_draft_live(analysis.draft) and analysis.on_clock_pick:
        st.info(
            f"On clock: **{analysis.on_clock_manager}** · Pick **{analysis.on_clock_pick}** · "
            f"Queue for {next_pick_label(analysis)}"
        )
    elif analysis.draft and is_pre_draft(analysis.draft):
        st.warning(
            f"Draft linked · waiting for first pick on Sleeper · "
            f"Your slot **{analysis.my_slot or '?'}** · {analysis.draft_label}"
        )


def _render_timing_advice(analysis: LiveDraftAnalysis) -> None:
    if not analysis.timing_advice:
        return
    st.subheader("Position timing")
    cols = st.columns(4)
    for col, tip in zip(cols, analysis.timing_advice[:4]):
        with col:
            st.markdown(f"**{_verdict_emoji(tip.verdict)} {tip.position} — {tip.headline}**")
            st.caption(tip.detail)


def _render_top_picks(analysis: LiveDraftAnalysis) -> None:
    if not analysis.picks:
        return
    title = "Pick now" if analysis.is_my_pick else f"Top targets · {next_pick_label(analysis)}"
    st.subheader(title)
    for p in analysis.picks[:5]:
        tags = " · ".join(p.tags) if p.tags else ""
        st.markdown(
            f"**{p.rank}. {p.player}** ({p.position}) · ADP {p.adp or '—'} · "
            f"Fit **{p.fit_score:.0f}** · Upside **{p.upside_score:.0f}**"
            + (f" · {tags}" if tags else "")
        )
        if p.reason:
            st.caption(p.reason)


def _render_my_roster(analysis: LiveDraftAnalysis) -> None:
    st.subheader("Your draft so far")
    if not analysis.my_drafted:
        st.caption("No picks yet — board updates as you draft in Sleeper.")
        return
    parts = [
        f"{'(K) ' if p.get('is_keeper') else ''}{p.get('name')} ({p.get('position')})"
        for p in analysis.my_drafted
    ]
    st.write(" · ".join(parts))
    st.caption(f"Roster: {analysis.roster_summary}")


def _render_available_table(analysis: LiveDraftAnalysis) -> None:
    st.subheader("Available players")
    df = _available_dataframe(analysis)
    if df.empty:
        st.info("No available players loaded — check league sync and refresh.")
        return

    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        pos_filter = st.multiselect(
            "Position",
            ["QB", "RB", "WR", "TE"],
            default=["QB", "RB", "WR", "TE"],
            key="live_draft_pos_filter",
        )
    with f2:
        picks_only = st.checkbox("Recommended only", value=False, key="live_draft_rec_only")
    with f3:
        search = st.text_input("Search player", key="live_draft_search", placeholder="Name…")

    view = df.copy()
    if pos_filter:
        view = view[view["Pos"].isin(pos_filter)]
    if picks_only:
        view = view[view["Pick"] == "★"]
    if search.strip():
        view = view[view["Player"].str.contains(search.strip(), case=False, na=False)]

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=min(560, 44 + len(view) * 35),
    )
    st.caption(f"{len(view)} players shown · ★ = top recommendation for your next pick")


def _render_recent_and_avoid(analysis: LiveDraftAnalysis) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Recent picks")
        if analysis.recent_picks:
            for rp in analysis.recent_picks[:12]:
                st.text(
                    f"#{rp.get('pick_no', '—')}  "
                    f"{rp.get('player_name') or '—'} ({rp.get('position') or '?'})  "
                    f"— {rp.get('manager') or ''}"
                )
        else:
            st.caption("No picks yet.")
    with c2:
        st.subheader("Avoid at this pick")
        if analysis.avoids:
            for a in analysis.avoids[:6]:
                icon = "🔴" if a.severity == "high" else "🟠"
                st.markdown(f"{icon} **{a.player}** ({a.position}) · ADP {a.adp or '—'}")
                st.caption(a.reason)
        else:
            st.caption("No major red flags in your pick window.")


def _draw_live_board(
    analyst,
    config: dict,
    show_fit: bool,
    draft_id: str | None = None,
) -> LiveDraftAnalysis | None:
    try:
        draft = fetch_sleeper_draft(
            config["league_id"],
            config.get("username", ""),
            draft_id=draft_id,
        )
        if draft and analyst._snapshot is not None:
            analyst._snapshot["draft"] = draft
        analysis = analyze_live_draft(analyst, config, draft=draft)
    except Exception as exc:
        st.error(f"Could not sync live draft: {exc}")
        return None

    if not analysis.draft:
        st.info(
            "No Sleeper draft found. Start a **mock draft** in the Sleeper app for this league, "
            "then hit **Refresh now**. Make sure your username in settings matches Sleeper."
        )
        return analysis

    if not analysis.my_slot:
        st.warning(
            "Could not match your Sleeper username to a draft slot. "
            "Confirm your username in **League settings** matches Sleeper exactly."
        )

    st.markdown(f"### Live Draft Assistant · {analysis.draft_label}")
    _render_status_bar(analysis)
    _render_on_clock_banner(analysis)

    if analysis.next_picks:
        st.caption(f"Your next picks: {' · '.join(str(p) for p in analysis.next_picks[:4])}")

    _render_timing_advice(analysis)
    _render_my_roster(analysis)
    _render_top_picks(analysis)
    _render_available_table(analysis)
    _render_recent_and_avoid(analysis)

    live_show_fit = not is_pre_draft(analysis.draft)
    if not live_show_fit and not show_fit:
        st.caption("Roster-fit scoring turns on once picks begin on Sleeper.")
    elif live_show_fit:
        st.caption("Live draft connected — fit scores use your picks from this draft session.")

    return analysis


def render_live_draft(analyst, config: dict, *, show_fit: bool = True) -> None:
    """Live draft page — background polling, full available-player table."""
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Refresh now", type="primary", use_container_width=True):
            st.cache_data.clear()
            analyst.refresh_draft()
            st.session_state.pop("live_draft_options", None)
            st.rerun()
    with c2:
        stay_connected = st.toggle("Stay connected", value=True, key="live_draft_stay_connected")
    with c3:
        st.caption("Open while drafting in Sleeper — board updates quietly in the background.")

    draft_id: str | None = st.session_state.get("live_draft_selected_id")
    options = st.session_state.get("live_draft_options") or []
    if len(options) > 1:
        labels = {str(d["draft_id"]): d.get("label", d["draft_id"]) for d in options}
        ids = list(labels.keys())
        default_idx = ids.index(str(draft_id)) if draft_id and str(draft_id) in ids else 0
        picked = st.selectbox(
            "Sleeper draft",
            options=ids,
            index=default_idx,
            format_func=lambda x: labels.get(x, x),
            key="live_draft_select_box",
        )
        if picked != draft_id:
            st.session_state["live_draft_selected_id"] = picked
            draft_id = picked

    def _run() -> LiveDraftAnalysis | None:
        analysis = _draw_live_board(analyst, config, show_fit, draft_id=draft_id)
        if analysis and analysis.draft:
            st.session_state["live_draft_options"] = analysis.draft.get("available_drafts") or []
            if not draft_id and analysis.draft.get("draft_id"):
                st.session_state["live_draft_selected_id"] = analysis.draft["draft_id"]
        return analysis

    if stay_connected:
        try:
            @st.fragment(run_every=timedelta(seconds=5))
            def _connected_board() -> None:
                _run()

            _connected_board()
        except TypeError:
            _run()
    else:
        _run()
