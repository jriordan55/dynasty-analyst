"""Dynatyze-style UI renderers for Streamlit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.adp import load_adp
from src.draft import format_pick_label
from src.fantasycalc import FantasyCalcClient
from src.platform import (
    aging_curve,
    contract_room,
    game_pulse,
    leaderboards,
    parse_trade_records,
    portfolio_managers,
    scatter_players,
    screener_pool,
    season_prep,
    start_sit_compare,
    trade_pulse,
    what_winning_costs,
)
from src.rankings import (
    adp_rankings,
    expert_consensus,
    fc_rankings,
    fetch_dynatyze_rankings,
    overlay_league,
    pick_rankings,
    where_we_disagree,
)
from src.trade_calc import evaluate_trade, league_pick_pool, league_player_pool


POS_COLORS = {"QB": "#3b82f6", "RB": "#22c55e", "WR": "#a855f7", "TE": "#f59e0b", "PICK": "#94a3b8"}


def inject_dynatyze_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; max-width: 1200px; }
        div[data-testid="stMetric"] {
            background: #12151a;
            padding: 0.6rem 0.85rem;
            border-radius: 0.45rem;
            border: 1px solid #2a2f38;
        }
        .nav-section {
            color: #8b949e;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0.75rem 0 0.25rem 0;
        }
        .grade-a { color: #1DB954; font-size: 2rem; font-weight: 800; }
        .grade-b { color: #86efac; font-size: 2rem; font-weight: 800; }
        .grade-c { color: #fbbf24; font-size: 2rem; font-weight: 800; }
        .grade-d { color: #f97316; font-size: 2rem; font-weight: 800; }
        .grade-f { color: #ef4444; font-size: 2rem; font-weight: 800; }
        .signal-buy { color: #1DB954; font-weight: 700; }
        .signal-sell { color: #ef4444; font-weight: 700; }
        .signal-hold { color: #94a3b8; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _cell(v, fallback: str = "—") -> str:
    if v is None or v == "":
        return fallback
    return str(v)


def _rankings_df(rows) -> pd.DataFrame:
    return pd.DataFrame([{
        "Rank": r.rank,
        "Player": r.player,
        "Pos": r.position,
        "Team": r.team,
        "Value": f"{r.value:,}" if isinstance(r.value, int) and r.value > 999 else r.value,
        "FC": f"{r.fc_value:,}" if r.fc_value else "—",
        "FC #": _cell(r.fc_rank),
        "LL #": _cell(r.ll_rank),
        "ADP": _cell(r.adp),
        "In league": _cell(r.on_roster, "—"),
        "Signal": r.signal or "—",
    } for r in rows])


def _fc_client(analyst, config: dict) -> FantasyCalcClient:
    snapshot = analyst._ensure_snapshot()
    cfg = {**config, "league": snapshot.get("league") or {}}
    fc = FantasyCalcClient(cfg)
    fc.load()
    return fc


def render_rankings(analyst, config: dict) -> None:
    section = st.radio(
        "Rankings",
        [
            "Dynasty Player Rankings",
            "Current Season Rankings",
            "Player ADP",
            "Projections Board",
            "Draft Big Board",
            "Pick Rankings",
            "Expert Consensus",
            "Where We Disagree",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )
    snapshot = analyst._ensure_snapshot()
    fc = _fc_client(analyst, config)

    if section == "Dynasty Player Rankings":
        rows, updated = fetch_dynatyze_rankings("dynasty")
        rows = overlay_league(rows, snapshot, config)
        st.caption(f"Dynatyze dynasty board · updated {updated} · [source](https://dynatyze.com/football/nfl-rankings)")
        st.dataframe(_rankings_df(rows), width="stretch", hide_index=True, height=520)

    elif section == "Current Season Rankings":
        rows, updated = fetch_dynatyze_rankings("redraft")
        rows = overlay_league(rows, snapshot, config)
        st.caption(f"Dynatyze redraft board · updated {updated}")
        st.dataframe(_rankings_df(rows), width="stretch", hide_index=True, height=520)

    elif section == "Player ADP":
        rows = adp_rankings(100)
        rows = overlay_league(rows, snapshot, config)
        st.caption("4for4 ADP from bundled data")
        st.dataframe(_rankings_df(rows), width="stretch", hide_index=True, height=520)

    elif section == "Projections Board":
        rows = fc_rankings({**config, "league": snapshot.get("league") or {}}, limit=75)
        rows = overlay_league(rows, snapshot, config)
        st.caption("Market projection proxy — FantasyCalc value + 30d trend (free sources)")
        df = pd.DataFrame([{
            "Rank": r.rank,
            "Player": r.player,
            "Pos": r.position,
            "FC Value": f"{r.fc_value:,}" if r.fc_value else "—",
            "Signal": r.signal,
            "In league": _cell(r.on_roster, "—"),
        } for r in rows])
        st.dataframe(df, width="stretch", hide_index=True, height=520)

    elif section == "Draft Big Board":
        keepers = analyst.get_keepers()
        board = analyst.draft_board(keeper_names=keepers, limit=75)
        st.caption("Sorted by roster fit for your league build")
        df = pd.DataFrame([{
            "Player": b.player,
            "Pos": b.position,
            "ADP": _cell(b.adp),
            "Fit": b.fit_score,
            "Upside": b.upside_score or "—",
        } for b in board])
        st.dataframe(df, width="stretch", hide_index=True, height=520)

    elif section == "Pick Rankings":
        rows = pick_rankings({**config, "league": snapshot.get("league") or {}})
        st.caption("FantasyCalc draft pick values for your league settings")
        df = pd.DataFrame([{"Rank": r.rank, "Pick": r.player, "Value": f"{r.value:,}"} for r in rows[:48]])
        st.dataframe(df, width="stretch", hide_index=True, height=520)

    elif section == "Expert Consensus":
        rows = expert_consensus({**config, "league": snapshot.get("league") or {}}, limit=75)
        rows = overlay_league(rows, snapshot, config)
        st.caption("FantasyCalc anchor + LeagueLogs overlay")
        st.dataframe(_rankings_df(rows), width="stretch", hide_index=True, height=520)

    else:
        rows = where_we_disagree({**config, "league": snapshot.get("league") or {}})
        st.caption("Largest rank gaps between FantasyCalc and LeagueLogs")
        df = pd.DataFrame([{
            "Player": r.player,
            "Pos": r.position,
            "FC #": r.fc_rank,
            "LL #": r.ll_rank,
            "Gap": r.signal,
            "Direction": r.source,
        } for r in rows])
        st.dataframe(df, width="stretch", hide_index=True, height=520)


def render_analytics(analyst, config: dict) -> None:
    tab_numbers, tab_money = st.tabs(["The Numbers", "Money & Movement"])

    snapshot = analyst._ensure_snapshot()
    fc = _fc_client(analyst, config)
    adp_map = load_adp()
    intel = analyst.intel()
    records = parse_trade_records(snapshot, intel)

    with tab_numbers:
        numbers = st.radio(
            "numbers",
            ["Screener", "Player Scatterplot", "Aging Curve Atlas", "Game Pulse", "Team Explorer", "Leaderboards"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if numbers == "Screener":
            pool = screener_pool(snapshot, fc, adp_map)
            c1, c2, c3, c4 = st.columns(4)
            pos = c1.selectbox("Position", ["All", "QB", "RB", "WR", "TE"])
            min_val = c2.number_input("Min FC value", 0, 15000, 0, step=500)
            max_age = c3.number_input("Max age", 20, 40, 40)
            owner = c4.selectbox("Owner", ["All"] + sorted({x["owner"] for x in pool if x["owner"]}))
            filtered = pool
            if pos != "All":
                filtered = [x for x in filtered if x["position"] == pos]
            filtered = [x for x in filtered if x["fc_value"] >= min_val]
            filtered = [x for x in filtered if not x["age"] or x["age"] <= max_age]
            if owner != "All":
                filtered = [x for x in filtered if x["owner"] == owner]
            st.dataframe(pd.DataFrame(filtered[:80]), width="stretch", hide_index=True, height=480)

        elif numbers == "Player Scatterplot":
            pts = scatter_players(snapshot, fc, adp_map)
            if not pts:
                st.info("Need ADP + FantasyCalc overlap on roster players.")
            else:
                try:
                    import plotly.express as px
                    fig = px.scatter(
                        pts, x="x_adp", y="y_value", color="position",
                        hover_name="player", hover_data=["manager", "age"],
                        labels={"x_adp": "ADP", "y_value": "FantasyCalc Value"},
                        color_discrete_map=POS_COLORS,
                    )
                    fig.update_layout(template="plotly_dark", height=480)
                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    st.dataframe(pd.DataFrame(pts), width="stretch", hide_index=True, height=480)

        elif numbers == "Aging Curve Atlas":
            pos = st.selectbox("Position", ["RB", "WR", "QB", "TE"])
            curve = aging_curve(snapshot, fc, pos)
            if curve:
                try:
                    import plotly.express as px
                    fig = px.line(curve, x="age", y="avg_value", markers=True, title=f"{pos} value by age (your league)")
                    fig.update_layout(template="plotly_dark", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    pass
            st.dataframe(pd.DataFrame(curve), width="stretch", hide_index=True)

        elif numbers == "Game Pulse":
            snap = dict(snapshot)
            snap["_sleeper_players"] = intel.sleeper_players
            pulse = game_pulse(snap)
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Trending adds")
                st.dataframe(pd.DataFrame(pulse["adds"]), width="stretch", hide_index=True, height=360)
            with c2:
                st.subheader("Trending drops")
                st.dataframe(pd.DataFrame(pulse["drops"]), width="stretch", hide_index=True, height=360)

        elif numbers == "Team Explorer":
            profiles = analyst.team_trade_profiles()
            mgr = st.selectbox("Team", [p.manager for p in profiles])
            p = next(x for x in profiles if x.manager == mgr)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Record", p.record)
            m2.metric("Mode", p.win_mode)
            m3.metric("Desperate", ", ".join(p.desperate_for) or "None")
            m4.metric("Surplus", ", ".join(p.surplus_at) or "None")
            df = pd.DataFrame([{
                "Pos": u.position, "Count": u.count, "Quality": u.quality,
                "Starter Val": u.starter_value, "Top": u.top_player, "Need": u.need_score,
            } for u in p.units])
            st.dataframe(df, width="stretch", hide_index=True, height=400)

        else:
            boards = leaderboards(snapshot, fc)
            pos = st.selectbox("Position board", list(boards.keys()))
            st.dataframe(pd.DataFrame(boards[pos]), width="stretch", hide_index=True, height=480)

    with tab_money:
        money = st.radio(
            "money",
            ["Trade Wire", "Trade Pulse", "The Contract Room", "What Winning Costs", "Trade Database"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if money == "Trade Wire":
            recent = records[:12]
            if not recent:
                st.info("No completed trades in league history yet.")
            for t in recent:
                with st.container(border=True):
                    st.markdown(f"**Week {t.week}** ({t.season}) · {' ↔ '.join(t.managers)}")
                    c1, c2 = st.columns(2)
                    c1.markdown("**Side A:** " + (" · ".join(t.side_a) if t.side_a else "—"))
                    c2.markdown("**Side B:** " + (" · ".join(t.side_b) if t.side_b else "—"))
                    if t.picks_moved:
                        st.caption("Picks: " + ", ".join(t.picks_moved))

        elif money == "Trade Pulse":
            st.dataframe(pd.DataFrame(trade_pulse(snapshot, fc)), width="stretch", hide_index=True, height=420)

        elif money == "The Contract Room":
            mgrs = [t.get("owner_name") for t in snapshot.get("teams") or []]
            sel = st.selectbox("Roster", mgrs, key="contract_mgr")
            st.dataframe(pd.DataFrame(contract_room(snapshot, fc, sel)), width="stretch", hide_index=True, height=420)

        elif money == "What Winning Costs":
            rows = what_winning_costs(snapshot, fc, records)
            st.caption("Avg FantasyCalc value acquired via trade by top-record teams")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)

        else:
            if not records:
                st.info("No trades in database.")
            else:
                df = pd.DataFrame([{
                    "Season": r.season,
                    "Week": r.week,
                    "Managers": " ↔ ".join(r.managers),
                    "Side A": " · ".join(r.side_a) or "—",
                    "Side B": " · ".join(r.side_b) or "—",
                    "Picks": ", ".join(r.picks_moved) or "—",
                } for r in records])
                st.dataframe(df, width="stretch", hide_index=True, height=480)


def render_tools(analyst, config: dict, ctx: dict) -> None:
    section = st.radio(
        "Tools",
        ["Portfolio Manager", "Mock Draft", "2026 Season Prep", "Start or Sit"],
        horizontal=True,
        label_visibility="collapsed",
    )
    snapshot = analyst._ensure_snapshot()
    fc = _fc_client(analyst, config)

    if section == "Portfolio Manager":
        portfolios = portfolio_managers(snapshot, fc)
        df = pd.DataFrame([{
            "Manager": p.manager,
            "Record": p.record,
            "Total FC": f"{p.total_value:,}",
            "QB": f"{p.qb_value:,}",
            "RB": f"{p.rb_value:,}",
            "WR": f"{p.wr_value:,}",
            "TE": f"{p.te_value:,}",
            "Picks": f"{p.pick_value:,}",
            "Avg Age": p.avg_age,
        } for p in portfolios])
        st.dataframe(df, width="stretch", hide_index=True, height=480)
        try:
            import plotly.express as px
            fig = px.bar(portfolios, x="manager", y="total_value", title="Portfolio value by manager")
            fig.update_layout(template="plotly_dark", height=320)
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass

    elif section == "Mock Draft":
        st.caption("Quick mock from your draft board — top fits at each of your snake picks")
        keepers = ctx.get("keepers") or []
        board = analyst.draft_board(keeper_names=keepers, limit=60)
        draft = ctx.get("draft") or {}
        teams = ctx.get("teams") or 12
        my_slot = ctx.get("my_slot")
        _, next_picks, _ = analyst.pick_recommendations(keeper_names=keepers, limit=5, draft=draft, my_slot=my_slot)
        picks_taken = {b.player for b in board[:20]}
        mock: list[dict] = []
        for pick_no in next_picks[:6]:
            avail = [b for b in board if b.player not in picks_taken]
            if not avail:
                break
            choice = avail[0]
            picks_taken.add(choice.player)
            mock.append({
                "Pick": format_pick_label(pick_no, teams),
                "Player": choice.player,
                "Pos": choice.position,
                "Fit": choice.fit_score,
            })
        st.dataframe(pd.DataFrame(mock), width="stretch", hide_index=True)

    elif section == "2026 Season Prep":
        prep = season_prep(snapshot, ctx.get("draft"), config)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Season", prep["season"])
        c2.metric("Teams", prep["teams"])
        c3.metric("Draft slot", prep["my_slot"] or "—")
        c4.metric("Format", f"{prep['format']} · {prep['scoring'].upper()}")
        st.subheader("Draft plan")
        plan = ctx.get("plan")
        if plan:
            st.markdown(f"**Needs:** {', '.join(plan.remaining_needs) or 'Balanced'}")
            st.markdown(f"**Priorities:** {', '.join(plan.draft_priorities[:4]) or '—'}")
        if ctx.get("keepers"):
            st.caption("Keepers: " + " · ".join(f"`{k}`" for k in ctx["keepers"]))

    else:
        _, my_team = analyst._ensure_loaded()
        names = sorted(
            p["name"] for p in my_team.get("players", [])
            if p.get("position") in {"QB", "RB", "WR", "TE"}
        )
        c1, c2 = st.columns(2)
        a = c1.selectbox("Player A", names, key="sit_a")
        b = c2.selectbox("Player B", names, index=min(1, len(names) - 1), key="sit_b")
        grades = analyst.grade_my_roster()
        result = start_sit_compare(grades, fc, a, b)
        st.success(f"Start **{result['winner']}**")
        c1, c2 = st.columns(2)
        with c1:
            st.metric(a, f"Grade {result['a']['grade']}", f"FC {result['a']['fc']:,}")
        with c2:
            st.metric(b, f"Grade {result['b']['grade']}", f"FC {result['b']['fc']:,}")


def render_trade_calculator(analyst, config: dict) -> None:
    snapshot = analyst._ensure_snapshot()
    fc = _fc_client(analyst, config)
    pool = league_player_pool(snapshot, fc)
    picks = league_pick_pool(snapshot, fc)

    st.caption(
        "Values from [FantasyCalc](https://www.fantasycalc.com/trade-calculator) "
        f"· {config.get('format', 'dynasty')} · {config.get('scoring', 'ppr').upper()} · "
        f"{len(snapshot.get('teams') or [])}-team · synced from Sleeper"
    )

    player_labels = [f"{p['name']} ({p['position']}, {p['manager']}) — {p['fc_value']:,}" for p in pool]
    label_to_name = {lbl: p["name"] for lbl, p in zip(player_labels, pool)}
    meta = {p["name"]: p for p in pool}

    pick_labels = [f"{p['label']} ({p['manager']}) — {p['fc_value']:,}" for p in picks]
    pick_label_map = {lbl: p["label"] for lbl, p in zip(pick_labels, picks)}

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Side A — You send")
        send_sel = st.multiselect("Players", player_labels, key="tc_send", label_visibility="collapsed")
        send_picks = st.multiselect("Picks", pick_labels, key="tc_send_picks", label_visibility="collapsed")
    with c2:
        st.subheader("Side B — You receive")
        recv_sel = st.multiselect("Players", player_labels, key="tc_recv", label_visibility="collapsed")
        recv_picks = st.multiselect("Picks", pick_labels, key="tc_recv_picks", label_visibility="collapsed")

    send_players = [label_to_name[x] for x in send_sel]
    recv_players = [label_to_name[x] for x in recv_sel]
    send_pk = [pick_label_map[x] for x in send_picks]
    recv_pk = [pick_label_map[x] for x in recv_picks]

    verdict = evaluate_trade(
        fc, send_players, recv_players,
        send_picks=send_pk, receive_picks=recv_pk,
        asset_meta=meta,
    )

    st.divider()
    gclass = "grade-c"
    if verdict.grade.startswith("A"):
        gclass = "grade-a"
    elif verdict.grade.startswith("B"):
        gclass = "grade-b"
    elif verdict.grade.startswith("D"):
        gclass = "grade-d"
    elif verdict.grade == "F":
        gclass = "grade-f"

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<p class="{gclass}">{verdict.grade}</p>', unsafe_allow_html=True)
        st.caption("Trade grade")
    m2.metric("You send", f"{verdict.send_total:,}")
    m3.metric("You receive", f"{verdict.receive_total:,}")
    m4.metric("Value gap", f"{verdict.delta:+,}")

    st.info(f"**{verdict.verdict}** — {verdict.recommendation}")
    if verdict.warnings:
        for w in verdict.warnings:
            st.warning(w)

    proposals = analyst.trade_proposals()
    if proposals:
        st.subheader("Suggested league trades")
        for p in proposals[:5]:
            with st.container(border=True):
                send = p.you_send_players + p.you_send_picks
                recv = p.you_receive_players + p.you_receive_picks
                st.markdown(f"**{p.target_manager}** · {p.acceptance} accept · FC Δ {p.fc_delta:+,}")
                st.caption(f"Send {' · '.join(send)} → Get {' · '.join(recv)}")
