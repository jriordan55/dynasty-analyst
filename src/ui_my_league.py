"""My League dashboard UI — Dynatyze-style lineup hub."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.draft import league_has_keepers
from src.my_league import (
    bench_ledger,
    build_dashboard,
    build_roster_rows,
    bye_week_board,
    depth_chart_rows,
    injury_report,
    section_counts,
    waiver_wire_snapshot,
)
from src.platform import start_sit_compare
from src.trade_assets import recommend_keepers
from src.ui_platform import _fc_client


def _cell(v, fallback: str = "—") -> str:
    if v is None or v == "":
        return fallback
    return str(v)


def render_my_league(analyst, config: dict, ctx: dict, grades: list[dict], section_override: str | None = None) -> None:
    snapshot, my_team = analyst._ensure_loaded()
    intel = analyst.intel()
    fc = _fc_client(analyst, config)

    dash = build_dashboard(snapshot, my_team, config)
    roster = build_roster_rows(my_team, intel, analyst.adp_map, grades)
    counts = section_counts(roster, snapshot, analyst.waiver_targets())
    wire = waiver_wire_snapshot(snapshot)

    if not section_override:
        # Header card
        h1, h2, h3, h4 = st.columns([3, 1, 1, 1])
        with h1:
            st.markdown(f"### {dash.league_name}")
            st.caption(f"{dash.format_label} · {dash.num_teams} teams · {dash.season}")
        h2.metric("Record", dash.record)
        h3.metric("Rank", f"#{dash.rank}")
        h4.metric("Points", f"{dash.fpts:.1f}" if dash.fpts else "—")

        st.markdown(f"**{dash.username}** · {dash.team_name} · _{dash.status}_")
        st.divider()

    sections = [
        ("Dashboard", None),
        ("My Team", counts["roster"]),
        ("Injury Report", counts["injuries"]),
        ("Bye Weeks", len(bye_week_board(roster))),
        ("Start/Sit", None),
        ("Depth Chart", counts["depth"]),
        ("Bench Ledger", counts["bench"]),
        ("Waiver Wire", counts["waiver_adds"]),
        ("Replacement Radar", counts["replacements"]),
        ("Roster grades", None),
        ("Sell alerts", None),
    ]
    if league_has_keepers(config, snapshot):
        sections.insert(1, ("Keepers", len(analyst.get_keepers())))

    if section_override:
        key = section_override
    else:
        labels = [f"{name} ({n})" if n is not None else name for name, n in sections]
        label_to_key = {lbl: sections[i][0] for i, lbl in enumerate(labels)}
        section = st.radio(
            "My League",
            labels,
            horizontal=True,
            label_visibility="collapsed",
        )
        key = label_to_key[section]

    if key == "Dashboard":
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Lineup snapshot")
            starters = [r for r in roster if r["starter"]]
            for r in starters[:9]:
                inj = f" · **{r['injury']}**" if r.get("injury") else ""
                st.markdown(f"- **{r['name']}** ({r['position']}, {r['nfl_team']}){inj}")
            if not starters:
                st.caption("Starters not set yet — showing top ADP players.")
                for r in roster[:8]:
                    st.markdown(f"- **{r['name']}** ({r['position']})")
        with c2:
            st.subheader("Quick counts")
            m1, m2 = st.columns(2)
            m1.metric("Roster", counts["roster"])
            m2.metric("Injuries", counts["injuries"])
            m1.metric("Bench", counts["bench"])
            m2.metric("Waiver adds (trending)", counts["waiver_adds"])
            if ctx.get("keepers"):
                st.caption("Keepers: " + " · ".join(f"`{k}`" for k in ctx["keepers"]))
            if ctx.get("plan"):
                st.caption(f"Draft needs: {', '.join(ctx['plan'].remaining_needs[:3]) or 'Balanced'}")

    elif key == "Keepers":
        recs = recommend_keepers(snapshot, my_team, analyst.adp_map, fc, config, intel)
        max_k = int(config.get("max_keepers") or (snapshot.get("league") or {}).get("settings", {}).get("max_keepers") or 0)
        if recs:
            top = [r for r in recs if r["verdict"] in ("Lock", "Keep")][:max_k]
            st.markdown(f"**Recommended {len(top)}/{max_k}:** " + ", ".join(f"**{r['player']}**" for r in top))
            kdf = pd.DataFrame([{
                "Rank": r["rank"],
                "Player": r["player"],
                "Pos": r["position"],
                "ADP": _cell(r["adp"]),
                "Keeper Rd": f"R{r['keeper_round']}{'*' if r['round_estimated'] else ''}",
                "Verdict": r["verdict"],
                "Current": "✓" if r["current_keeper"] else "",
                "Why": " · ".join(r["reasons"]),
            } for r in recs])
            st.dataframe(kdf, width="stretch", hide_index=True, height=400)
        else:
            st.info("No keeper league settings detected.")

    elif key == "My Team":
        df = pd.DataFrame([{
            "Player": r["name"],
            "Pos": r["position"],
            "NFL": r["nfl_team"],
            "Role": r["status"],
            "ADP": _cell(r["adp"]),
            "Grade": r["grade"],
            "Age": _cell(r["age"]),
            "Bye": _cell(r["bye_week"]),
            "Injury": _cell(r["injury"]),
        } for r in roster])
        st.dataframe(df, width="stretch", hide_index=True, height=480)

    elif key == "Injury Report":
        flagged = injury_report(roster)
        if not flagged:
            st.success("No injury flags on your roster.")
        else:
            df = pd.DataFrame([{
                "Player": r["name"],
                "Pos": r["position"],
                "NFL": r["nfl_team"],
                "Status": r["injury"],
                "Depth": _cell(r["depth_order"]),
                "News": _cell(r.get("news")),
            } for r in flagged])
            st.dataframe(df, width="stretch", hide_index=True, height=360)

    elif key == "Bye Weeks":
        byes = bye_week_board(roster)
        st.caption("2025 NFL bye schedule by player NFL team")
        df = pd.DataFrame([{
            "Week": r["bye_week"],
            "Player": r["name"],
            "Pos": r["position"],
            "NFL Team": r["nfl_team"],
            "Starter": "✓" if r["starter"] else "",
        } for r in byes])
        st.dataframe(df, width="stretch", hide_index=True, height=480)

    elif key == "Start/Sit":
        names = [r["name"] for r in roster if r["position"] in {"QB", "RB", "WR", "TE"}]
        if len(names) < 2:
            st.info("Need at least two players to compare.")
        else:
            c1, c2 = st.columns(2)
            a = c1.selectbox("Player A", names, key="ml_sit_a")
            b = c2.selectbox("Player B", names, index=min(1, len(names) - 1), key="ml_sit_b")
            result = start_sit_compare(grades, fc, a, b)
            st.success(f"Start **{result['winner']}**")
            c1.metric(a, f"Grade {result['a']['grade']}", f"FC {result['a']['fc']:,}")
            c2.metric(b, f"Grade {result['b']['grade']}", f"FC {result['b']['fc']:,}")

    elif key == "Depth Chart":
        rows = depth_chart_rows(roster)
        df = pd.DataFrame([{
            "Pos": r["position"],
            "Player": r["name"],
            "NFL": r["nfl_team"],
            "Depth": _cell(r["depth_order"]),
            "Role": r.get("depth_role") or r["position"],
            "ADP": _cell(r["adp"]),
            "Starter": "✓" if r["starter"] else "",
        } for r in rows])
        st.dataframe(df, width="stretch", hide_index=True, height=480)

    elif key == "Bench Ledger":
        bench = bench_ledger(roster)
        df = pd.DataFrame([{
            "Player": r["name"],
            "Pos": r["position"],
            "ADP": _cell(r["adp"]),
            "Grade": r["grade"],
            "Upside": _cell(r["upside"]),
            "Bye": _cell(r["bye_week"]),
            "News": _cell(r.get("news")),
        } for r in bench])
        st.dataframe(df, width="stretch", hide_index=True, height=480)

    elif key == "Waiver Wire":
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Trending adds")
            st.dataframe(pd.DataFrame(wire["adds"]), width="stretch", hide_index=True, height=400)
        with c2:
            st.subheader("Trending drops")
            st.dataframe(pd.DataFrame(wire["drops"]), width="stretch", hide_index=True, height=400)

    elif key == "Replacement Radar":
        waivers = analyst.waiver_targets()
        if not waivers:
            st.info("No strong waiver fits right now.")
        else:
            df = pd.DataFrame([{
                "Player": w.player,
                "Pos": w.position,
                "ADP": _cell(w.adp),
                "Why": w.reason[:90],
            } for w in waivers[:20]])
            st.dataframe(df, width="stretch", hide_index=True, height=480)

    elif key == "Roster grades":
        df = pd.DataFrame([{
            "Player": g["name"],
            "Pos": g["position"],
            "ADP": _cell(g["adp"]),
            "Age": _cell(g["age"]),
            "Grade": g["grade"],
            "Notes": "; ".join(g["notes"][:2]) if g.get("notes") else "—",
        } for g in grades])
        st.dataframe(df, width="stretch", hide_index=True, height=480)

    else:
        sells = analyst.sell_candidates()
        if not sells:
            st.success("No urgent sell candidates.")
        else:
            for s in sells:
                icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.urgency, "")
                with st.container(border=True):
                    st.markdown(f"{icon} **{s.player}** ({s.position}) · ADP {_cell(s.adp)}")
                    st.caption(s.reason)
