from __future__ import annotations

import re

from src.adp import lookup_adp
from src.analysis import CORE_POSITIONS, FLEX_POSITIONS, analyze_team_needs, grade_roster
from src.models import (
    ManagerTendency,
    PlayerValue,
    PositionUnit,
    TeamNeeds,
    TeamTradeProfile,
    TradeMatch,
    TradeProposal,
)
from src.player_intel import PlayerIntel

PICK_LABEL = re.compile(r"(?P<season>\d{4}).*?[Rr]d?\s*(?P<round>\d+)")


def _player_sleeper_id(player: dict, intel: PlayerIntel) -> str | None:
    pid = player.get("id")
    if pid:
        return str(pid)
    sp = intel._lookup_sleeper(player.get("name", ""))
    if sp:
        return str(sp.get("player_id") or "")
    return None


def _fc_player_value(
    name: str,
    player: dict | None,
    intel: PlayerIntel,
    fc_client,
) -> int:
    if not fc_client:
        return 0
    sid = _player_sleeper_id(player, intel) if player else None
    fc = fc_client.get(name, sid)
    return fc.value if fc else 0


def _parse_pick_label(label: str) -> tuple[str, int, int | None] | None:
    m = PICK_LABEL.search(label)
    if not m:
        return None
    slot = None
    orig = re.search(r"orig R(\d+)", label, re.I)
    if orig:
        slot = int(orig.group(1))
    return m.group("season"), int(m.group("round")), slot


def _fc_pick_value(label: str, fc_client) -> int:
    if not fc_client:
        return 0
    parsed = _parse_pick_label(label)
    if not parsed:
        return 0
    season, rnd, slot = parsed
    fc = fc_client.pick_value(season, rnd, slot)
    return fc.value if fc else 0


def _enrich_player_value(
    pv: PlayerValue,
    player: dict,
    intel: PlayerIntel,
    fc_client=None,
    fp_client=None,
) -> None:
    if fc_client:
        fc = fc_client.get(pv.name, _player_sleeper_id(player, intel))
        if fc:
            pv.fc_value = fc.value
            pv.fc_trend = fc.trend_label
            if fc.trend_label not in pv.summary:
                pv.summary = f"FantasyCalc {fc.display_value} · {fc.trend_label} · {pv.summary}".strip(" · ")
    if fp_client and fp_client.available:
        fp = fp_client.get(pv.name)
        if fp and fp.summary:
            pv.fp_summary = fp.summary
            if fp.summary not in pv.summary:
                pv.summary = f"{fp.summary} · {pv.summary}".strip(" · ")

QUALITY_TIERS = [
    (82, "Elite"),
    (70, "Strong"),
    (58, "Solid"),
    (45, "Average"),
    (30, "Thin"),
    (0, "Empty"),
]

ROUND_BASE_VALUE = {1: 72, 2: 42, 3: 26, 4: 17, 5: 11, 6: 7, 7: 5}
CURRENT_SEASON = 2025


def _quality_label(value: float) -> str:
    for threshold, label in QUALITY_TIERS:
        if value >= threshold:
            return label
    return "Empty"


def _grade_from_value(value: float) -> str:
    if value >= 88:
        return "A"
    if value >= 78:
        return "B+"
    if value >= 68:
        return "B"
    if value >= 58:
        return "C+"
    if value >= 48:
        return "C"
    if value >= 35:
        return "D"
    return "F"


def compute_player_value(
    player: dict,
    intel: PlayerIntel,
    *,
    is_starter: bool = False,
    contending: bool = True,
    fc_client=None,
    fp_client=None,
) -> PlayerValue:
    name = player["name"]
    pos = player["position"]
    ctx = intel.get(name, pos)
    adp = ctx.blended_adp or ctx.adp
    age = player.get("age") or (intel._lookup_sleeper(name) or {}).get("age")

    if adp:
        if adp <= 12:
            base = 94
        elif adp <= 24:
            base = 86
        elif adp <= 48:
            base = 76
        elif adp <= 72:
            base = 66
        elif adp <= 96:
            base = 56
        elif adp <= 120:
            base = 48
        elif adp <= 150:
            base = 40
        elif adp <= 180:
            base = 32
        else:
            base = max(12, 28 - (adp - 180) * 0.08)
    else:
        base = 22

    value = base
    value += min(8, ctx.vor * 0.18)
    value += min(10, ctx.upside_score * 0.14)
    value -= ctx.injury_penalty * 0.28

    trend = ctx.trending_signal or ""
    if trend == "Hot add":
        value += 4
    elif trend == "Trending drop":
        value -= 6

    if ctx.sleeper_rank and adp and ctx.sleeper_rank < adp - 18:
        value += 5
    elif ctx.sleeper_rank and adp and ctx.sleeper_rank > adp + 18:
        value -= 4

    if age:
        if age <= 24:
            value += 5 if not contending else 2
        elif age <= 26:
            value += 2
        if pos == "RB" and age >= 28:
            value -= 7 if contending else 3
        elif pos == "WR" and age >= 30:
            value -= 5
        elif pos == "QB" and age >= 34:
            value -= 4

    if is_starter and value >= 70:
        value += 2

    value = max(5, min(98, round(value, 1)))
    grade = _grade_from_value(value)

    summary_parts = []
    if adp:
        summary_parts.append(f"ADP {adp}")
    if ctx.vor >= 10:
        summary_parts.append(f"VOR +{ctx.vor:.0f}")
    if ctx.upside_score >= 35:
        summary_parts.append(f"Upside {ctx.upside_score:.0f}")
    if trend:
        summary_parts.append(trend)
    if ctx.injury_status:
        summary_parts.append(f"Injury: {ctx.injury_status}")
    if age:
        summary_parts.append(f"Age {age}")

    pv = PlayerValue(
        name=name,
        position=pos,
        dynasty_value=value,
        adp=adp,
        grade=grade,
        upside_score=ctx.upside_score,
        vor=ctx.vor,
        age=age,
        trend=trend,
        injury=ctx.injury_status or "",
        summary=" · ".join(summary_parts[:5]),
        tradeable=True,
    )
    _enrich_player_value(pv, player, intel, fc_client, fp_client)
    return pv


def pick_label(season: str, round_no: int, original_roster_id: int | None = None) -> str:
    base = f"{season} Rd {round_no}"
    if original_roster_id:
        return f"{base} (orig R{original_roster_id})"
    return base


def compute_pick_value(season: str, round_no: int, slot_hint: int | None = None) -> float:
    val = float(ROUND_BASE_VALUE.get(round_no, max(3, 9 - round_no)))
    if round_no == 1 and slot_hint:
        if slot_hint <= 4:
            val += 18
        elif slot_hint <= 8:
            val += 10
        elif slot_hint >= 10:
            val -= 6
    try:
        season_i = int(season)
    except (TypeError, ValueError):
        season_i = CURRENT_SEASON
    if season_i > CURRENT_SEASON:
        val *= 0.9 ** (season_i - CURRENT_SEASON)
    elif season_i < CURRENT_SEASON:
        val *= 0.75
    return round(max(3, val), 1)


def _roster_by_id(snapshot: dict) -> dict[int, dict]:
    return {t["roster_id"]: t for t in snapshot["teams"]}


def _owner_roster_map(snapshot: dict) -> dict[str, dict]:
    return {t["owner_id"]: t for t in snapshot["teams"] if t.get("owner_id")}


def build_manager_tendencies(snapshot: dict, intel: PlayerIntel) -> dict[str, ManagerTendency]:
    trade_history = snapshot.get("trade_history") or {}
    trades = trade_history.get("trades") or []
    draft_history = trade_history.get("draft_history") or []
    teams = snapshot["teams"]

    roster_to_owner: dict[int, str] = {}
    owner_names: dict[str, str] = {}
    for team in teams:
        rid = team["roster_id"]
        oid = team.get("owner_id", "")
        roster_to_owner[rid] = oid
        owner_names[oid] = team["owner_name"]

    # Draft tendencies per owner
    early_by_owner: dict[str, list[str]] = {}
    ages_by_owner: dict[str, list[float]] = {}
    for block in draft_history:
        for pick in block.get("picks") or []:
            if pick.get("is_keeper"):
                continue
            rnd = pick.get("round") or 99
            if rnd > 5:
                continue
            owner_id = pick.get("picked_by") or pick.get("owner_id") or ""
            if not owner_id:
                continue
            meta = pick.get("metadata") or {}
            pos = meta.get("position") or ""
            if pos in CORE_POSITIONS:
                early_by_owner.setdefault(owner_id, []).append(pos)
            pid = pick.get("player_id")
            if pid:
                sp = intel.sleeper_players.get(str(pid), {})
                if sp.get("age"):
                    ages_by_owner.setdefault(owner_id, []).append(float(sp["age"]))

    trade_stats: dict[str, dict] = {}
    for txn in trades:
        for rid in txn.get("roster_ids") or []:
            oid = roster_to_owner.get(rid, "")
            if not oid:
                continue
            stats = trade_stats.setdefault(oid, {
                "count": 0, "picks": 0, "ages": [], "acquired_pos": [], "sent_pos": [],
            })
            stats["count"] += 1
            stats["picks"] += len(txn.get("draft_picks") or [])

        adds = txn.get("adds") or {}
        drops = txn.get("drops") or {}
        for pid, rid in adds.items():
            oid = roster_to_owner.get(rid, "")
            if not oid:
                continue
            sp = intel.sleeper_players.get(str(pid), {})
            pos = sp.get("position", "")
            if pos in CORE_POSITIONS:
                trade_stats.setdefault(oid, {"count": 0, "picks": 0, "ages": [], "acquired_pos": [], "sent_pos": []})
                trade_stats[oid]["acquired_pos"].append(pos)
            if sp.get("age"):
                trade_stats[oid]["ages"].append(float(sp["age"]))
        for pid, rid in drops.items():
            oid = roster_to_owner.get(rid, "")
            if not oid:
                continue
            sp = intel.sleeper_players.get(str(pid), {})
            pos = sp.get("position", "")
            if pos in CORE_POSITIONS:
                trade_stats.setdefault(oid, {"count": 0, "picks": 0, "ages": [], "acquired_pos": [], "sent_pos": []})
                trade_stats[oid]["sent_pos"].append(pos)

    tendencies: dict[str, ManagerTendency] = {}
    for team in teams:
        oid = team.get("owner_id", "")
        early = early_by_owner.get(oid, [])
        early_total = len(early) or 1
        rb_pct = sum(1 for p in early if p == "RB") / early_total * 100
        wr_pct = sum(1 for p in early if p == "WR") / early_total * 100
        draft_ages = ages_by_owner.get(oid, [])
        youth_pct = (sum(1 for a in draft_ages if a <= 25) / len(draft_ages) * 100) if draft_ages else 0

        stats = trade_stats.get(oid, {"count": 0, "picks": 0, "ages": [], "acquired_pos": [], "sent_pos": []})
        avg_trade_age = sum(stats["ages"]) / len(stats["ages"]) if stats["ages"] else 0

        likes: list[str] = []
        archetype_parts: list[str] = []
        if rb_pct >= 45:
            archetype_parts.append("RB-heavy drafter")
            likes.append("RB depth")
        if wr_pct >= 45:
            archetype_parts.append("WR-focused")
            likes.append("WR talent")
        if youth_pct >= 55:
            archetype_parts.append("Youth builder")
            likes.append("young upside")
        if stats["picks"] >= 2:
            archetype_parts.append("Pick mover")
            likes.append("draft capital")
        if stats["count"] >= 3:
            archetype_parts.append("Active trader")
        if not archetype_parts:
            archetype_parts.append("Balanced")

        acquired = stats.get("acquired_pos") or []
        if acquired:
            top_acq = max(set(acquired), key=acquired.count)
            likes.append(f"often adds {top_acq}")

        notes = []
        if early:
            notes.append(f"Early picks (R1-5): {', '.join(early[:8])}")
        if stats["count"]:
            notes.append(f"{stats['count']} trades tracked · {stats['picks']} picks moved")
        if draft_ages:
            notes.append(f"Avg draft age: {sum(draft_ages)/len(draft_ages):.1f}")

        tendencies[oid] = ManagerTendency(
            manager=team["owner_name"],
            team=team["team_name"],
            owner_id=oid,
            trade_count=stats["count"],
            picks_traded=stats["picks"],
            avg_trade_age=round(avg_trade_age, 1),
            draft_rb_early_pct=round(rb_pct, 0),
            draft_wr_early_pct=round(wr_pct, 0),
            draft_youth_pct=round(youth_pct, 0),
            archetype=" · ".join(archetype_parts[:3]),
            likes=list(dict.fromkeys(likes))[:5],
            notes=" · ".join(notes) if notes else "Limited history in synced seasons",
        )
    return tendencies


def analyze_position_unit(
    team: dict,
    position: str,
    intel: PlayerIntel,
    needs: TeamNeeds,
    *,
    contending: bool = True,
    fc_client=None,
    fp_client=None,
) -> PositionUnit:
    players = [p for p in team["players"] if p["position"] == position]
    values = [
        compute_player_value(
            p, intel, is_starter=p.get("is_starter", False),
            contending=contending, fc_client=fc_client, fp_client=fp_client,
        )
        for p in players
    ]
    values.sort(key=lambda v: v.dynasty_value, reverse=True)

    starter_val = values[0].dynasty_value if values else 0
    depth_vals = values[1:]
    depth_avg = sum(v.dynasty_value for v in depth_vals) / len(depth_vals) if depth_vals else 0
    total = sum(v.dynasty_value for v in values)
    ages = [v.age for v in values if v.age]

    need_score = 0.0
    if position in needs.desperate_for:
        need_score += 3
    if position in needs.starter_gaps:
        need_score += needs.starter_gaps[position] * 1.5
    if starter_val < 55:
        need_score += 2
    if len(values) <= 1:
        need_score += 2

    surplus_score = needs.surplus.get(position, 0)
    if len(values) >= 5 and depth_avg >= 45:
        surplus_score += 1
    if starter_val >= 75 and depth_avg >= 50:
        surplus_score += 1

    notes_parts = []
    if values:
        notes_parts.append(f"Top: {values[0].name} ({values[0].dynasty_value:.0f})")
    if depth_vals:
        notes_parts.append(f"Depth avg {depth_avg:.0f}")
    if any(v.injury for v in values):
        notes_parts.append("Injury risk on unit")
    if any(v.trend == "Hot add" for v in values):
        notes_parts.append("Rising assets")

    return PositionUnit(
        position=position,
        count=len(values),
        quality=_quality_label(starter_val),
        starter_value=round(starter_val, 1),
        depth_value=round(depth_avg, 1),
        total_value=round(total, 1),
        top_player=values[0].name if values else "—",
        top_value=values[0].dynasty_value if values else 0,
        weakest=values[-1].name if values else "—",
        avg_age=round(sum(ages) / len(ages), 1) if ages else 0,
        need_score=round(need_score, 1),
        surplus_score=round(surplus_score, 1),
        notes=" · ".join(notes_parts),
    )


def build_team_trade_profile(
    team: dict,
    needs: TeamNeeds,
    intel: PlayerIntel,
    tendency: ManagerTendency,
    config: dict,
    fc_client=None,
    fp_client=None,
) -> TeamTradeProfile:
    contending = config.get("notes", {}).get("contending", True)
    units = [
        analyze_position_unit(
            team, pos, intel, needs, contending=contending,
            fc_client=fc_client, fp_client=fp_client,
        )
        for pos in CORE_POSITIONS
    ]

    graded = grade_roster(team, intel.adp_map, intel=intel)
    grade_map = {g["name"]: g["grade"] for g in graded}

    all_values = [
        compute_player_value(
            p, intel, is_starter=p.get("is_starter", False), contending=contending,
            fc_client=fc_client, fp_client=fp_client,
        )
        for p in team["players"]
        if p["position"] in CORE_POSITIONS
    ]
    for pv in all_values:
        pv.grade = grade_map.get(pv.name, pv.grade)

    tradeable = []
    keeper_set = set(config.get("keepers") or [])
    for pv in all_values:
        if pv.name in keeper_set:
            pv.tradeable = False
            continue
        player = next(p for p in team["players"] if p["name"] == pv.name)
        if player.get("is_starter") and pv.dynasty_value >= 72:
            pv.tradeable = False
        elif pv.dynasty_value < 25:
            pv.tradeable = False
        else:
            tradeable.append(pv)
    tradeable.sort(key=lambda v: v.dynasty_value, reverse=True)

    targets = sorted(all_values, key=lambda v: v.dynasty_value, reverse=True)[:6]

    pick_labels: list[str] = []
    pick_values: list[tuple[str, float]] = []
    for dp in team.get("draft_picks") or []:
        season = str(dp.get("season", CURRENT_SEASON + 1))
        rnd = int(dp.get("round") or 1)
        orig = dp.get("roster_id")
        label = pick_label(season, rnd, orig)
        if fc_client:
            fc = fc_client.pick_value(season, rnd, orig)
            val = float(fc.value if fc else compute_pick_value(season, rnd, orig))
        else:
            val = compute_pick_value(season, rnd, orig)
        pick_labels.append(label)
        pick_values.append((label, val))

    desperate = [u.position for u in units if u.need_score >= 3]
    if not desperate:
        desperate = list(needs.desperate_for)
    surplus = [u.position for u in units if u.surplus_score >= 2]
    if not surplus:
        surplus = list(needs.overloaded_at)

    win_mode = "Contending" if contending else "Rebuilding"
    if team.get("wins", 0) >= 8:
        win_mode = "Win-now"
    elif team.get("wins", 0) <= 4:
        win_mode = "Rebuild"

    return TeamTradeProfile(
        manager=team["owner_name"],
        team=team["team_name"],
        owner_id=team.get("owner_id", ""),
        record=f"{team.get('wins', 0)}-{team.get('losses', 0)}",
        win_mode=win_mode,
        units=units,
        desperate_for=desperate,
        surplus_at=surplus,
        tradeable_assets=tradeable,
        targets_on_roster=targets,
        draft_picks=pick_labels,
        pick_values=pick_values,
        tendency=tendency,
    )


def _effective_gaps(profile: TeamTradeProfile, needs: TeamNeeds, config: dict) -> set[str]:
    gaps = set(needs.desperate_for) | set(needs.starter_gaps.keys())
    gaps.discard("FLEX")
    for unit in profile.units:
        if unit.need_score >= 2.5:
            gaps.add(unit.position)
        if unit.starter_value < 62:
            gaps.add(unit.position)
    for pos in config.get("notes", {}).get("target_positions") or []:
        if pos in CORE_POSITIONS:
            gaps.add(pos)
    return gaps


def _they_want_position(other: TeamTradeProfile, position: str) -> bool:
    if position in other.desperate_for:
        return True
    unit = next((u for u in other.units if u.position == position), None)
    if not unit:
        return False
    return unit.need_score >= 2 or unit.starter_value < 58 or unit.count <= 2


def _my_untouchables(my_team: dict, intel: PlayerIntel, config: dict) -> set[str]:
    contending = config.get("notes", {}).get("contending", True)
    protected = set(config.get("keepers") or [])
    for p in my_team["players"]:
        if p.get("is_starter"):
            pv = compute_player_value(p, intel, is_starter=True, contending=contending)
            if pv.dynasty_value >= 80:
                protected.add(p["name"])
    return protected


def _fairness_label(delta: float) -> str:
    if abs(delta) <= 3:
        return "Fair"
    if delta > 3:
        return "You win value"
    return "Pay premium"


def _confidence(leverage: float, delta: float, tendency_match: bool) -> str:
    score = leverage
    if abs(delta) <= 5:
        score += 1
    if tendency_match:
        score += 1
    if score >= 5:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def build_trade_proposals(
    my_team: dict,
    my_needs: TeamNeeds,
    my_profile: TeamTradeProfile,
    other_profile: TeamTradeProfile,
    intel: PlayerIntel,
    config: dict,
    *,
    max_proposals: int = 3,
    fc_client=None,
    fp_client=None,
) -> list[TradeProposal]:
    if other_profile.owner_id == my_profile.owner_id:
        return []

    untouchable = _my_untouchables(my_team, intel, config)
    proposals: list[TradeProposal] = []

    my_gaps = _effective_gaps(my_profile, my_needs, config)
    my_surplus_positions = set(my_profile.surplus_at)

    my_assets = [
        v for v in my_profile.tradeable_assets
        if v.name not in untouchable and _they_want_position(other_profile, v.position)
    ]
    # Also offer from positional surplus even if not flagged desperate
    my_assets.extend(
        v for v in my_profile.tradeable_assets
        if v.name not in untouchable
        and v.position in my_surplus_positions
        and v not in my_assets
    )

    their_assets = [
        v for v in other_profile.targets_on_roster
        if v.position in my_gaps
    ]
    # Upgrade targets: their starter beats yours by 8+ value
    for unit in my_profile.units:
        their_unit = next((u for u in other_profile.units if u.position == unit.position), None)
        if their_unit and their_unit.starter_value >= unit.starter_value + 8:
            for v in other_profile.targets_on_roster:
                if v.position == unit.position and v not in their_assets:
                    their_assets.append(v)

    if not my_assets or not their_assets:
        return []

    my_assets.sort(key=lambda v: v.dynasty_value, reverse=True)
    their_assets.sort(key=lambda v: v.dynasty_value, reverse=True)

    attempts: list[tuple[list, list, list, list]] = []

    # 1-for-1 same position or need fill
    for give in my_assets[:5]:
        for get in their_assets[:5]:
            if get.position not in my_gaps:
                my_unit = next((u for u in my_profile.units if u.position == get.position), None)
                if not my_unit or get.dynasty_value < my_unit.starter_value + 5:
                    continue
            delta = get.dynasty_value - give.dynasty_value
            if abs(delta) <= 12:
                attempts.append(([give], [], [get], []))

    # 2-for-1 upgrade
    for i, give1 in enumerate(my_assets[:4]):
        for give2 in my_assets[i + 1:6]:
            for get in their_assets[:4]:
                if get.dynasty_value < give1.dynasty_value:
                    continue
                send_val = give1.dynasty_value + give2.dynasty_value
                if get.dynasty_value - send_val > 8:
                    continue
                if abs(get.dynasty_value - send_val) <= 15:
                    attempts.append(([give1, give2], [], [get], []))

    # Pick sweeteners — they hoard picks or need value balance
    my_picks = list(my_profile.pick_values)
    their_picks = list(other_profile.pick_values)
    if my_picks and their_assets:
        for give in my_assets[:3]:
            for get in their_assets[:3]:
                for plabel, pval in my_picks[:2]:
                    delta = get.dynasty_value - (give.dynasty_value + pval)
                    if -5 <= delta <= 8:
                        attempts.append(([give], [plabel], [get], []))
    if their_picks and my_assets:
        for give in my_assets[:3]:
            for get in their_assets[:3]:
                for plabel, pval in their_picks[:2]:
                    delta = (get.dynasty_value + pval) - give.dynasty_value
                    if -5 <= delta <= 10:
                        attempts.append(([give], [], [get], [plabel]))

    seen: set[str] = set()
    for give_list, send_picks, get_list, recv_picks in attempts:
        give_names = [g.name for g in give_list]
        get_names = [g.name for g in get_list]
        key = "|".join(give_names + send_picks + get_names + recv_picks)
        if key in seen:
            continue
        seen.add(key)

        send_val = sum(g.dynasty_value for g in give_list)
        send_val += sum(v for l, v in my_profile.pick_values if l in send_picks)
        recv_val = sum(g.dynasty_value for g in get_list)
        recv_val += sum(v for l, v in other_profile.pick_values if l in recv_picks)

        fc_eval = None
        if fc_client:
            fc_eval = fc_client.evaluate_trade(
                give_names,
                get_names,
                send_picks=[parsed for p in send_picks if (parsed := _parse_pick_label(p))],
                receive_picks=[parsed for p in recv_picks if (parsed := _parse_pick_label(p))],
                sleeper_ids={
                    p["name"]: sid for p in my_team["players"]
                    if (sid := _player_sleeper_id(p, intel))
                },
            )
            if fc_eval["send_total"] or fc_eval["receive_total"]:
                send_val = fc_eval["send_total"]
                recv_val = fc_eval["receive_total"]

        delta = recv_val - send_val

        leverage = 0.0
        for g in give_list:
            if g.position in other_profile.desperate_for:
                leverage += 2.0
            if other_profile.units and any(
                u.position == g.position and u.need_score >= 3 for u in other_profile.units
            ):
                leverage += 1.0
        for g in get_list:
            if g.position in my_gaps:
                leverage += 1.5

        tendency_match = (
            give_list[0].position in other_profile.tendency.likes
            or ("young upside" in other_profile.tendency.likes and (give_list[0].age or 99) <= 25)
        )
        if tendency_match:
            leverage += 0.8

        their_unit = next((u for u in other_profile.units if u.position == give_list[0].position), None)
        why_accept = (
            f"Fills {give_list[0].position} need ({their_unit.quality if their_unit else 'thin unit'}) "
            f"with {give_list[0].grade}-grade value ({give_list[0].dynasty_value:.0f}). "
        )
        if other_profile.tendency.archetype:
            why_accept += f"They profile as {other_profile.tendency.archetype.lower()}."

        why_win = (
            f"You upgrade {get_list[0].position} with {get_names[0]} "
            f"({get_list[0].summary})."
        )
        if fc_eval and fc_eval["receive_total"]:
            why_win += f" FantasyCalc: {fc_eval['verdict']} ({fc_eval['delta']:+,})."

        fp_bits = [g.fp_summary for g in get_list if g.fp_summary]
        fp_insight = fp_bits[0] if fp_bits else ""

        risks = []
        if any(g.injury for g in get_list):
            risks.append("Injury risk on incoming player")
        if fc_eval and fc_eval["delta"] < -max(200, fc_eval["send_total"] * 0.05):
            risks.append("FantasyCalc flags this as an overpay")
        if delta < -5 and not fc_eval:
            risks.append("You pay a premium — needs counter-move")
        if not risks:
            risks.append("Monitor news before sending")

        fairness_label = fc_eval["verdict"] if fc_eval and fc_eval["receive_total"] else _fairness_label(delta)

        proposals.append(
            TradeProposal(
                target_manager=other_profile.manager,
                target_team=other_profile.team,
                you_send_players=give_names,
                you_send_picks=send_picks,
                you_receive_players=get_names,
                you_receive_picks=recv_picks,
                send_value=round(send_val, 1),
                receive_value=round(recv_val, 1),
                value_delta=round(delta, 1),
                fairness=fairness_label,
                leverage_score=round(leverage, 1),
                confidence=_confidence(leverage, delta, tendency_match),
                why_they_accept=why_accept,
                why_you_win=why_win,
                risk_notes=" · ".join(risks),
                fc_send_total=fc_eval["send_total"] if fc_eval else 0,
                fc_receive_total=fc_eval["receive_total"] if fc_eval else 0,
                fc_delta=fc_eval["delta"] if fc_eval else 0,
                fc_verdict=fc_eval["verdict"] if fc_eval else "",
                fp_insight=fp_insight,
            )
        )

    proposals.sort(key=lambda p: (p.leverage_score, p.receive_value - p.send_value), reverse=True)
    return proposals[:max_proposals]


def analyze_league_trades(
    snapshot: dict,
    my_team: dict,
    config: dict,
    intel: PlayerIntel,
    keeper_plan=None,
    fc_client=None,
    fp_client=None,
) -> tuple[list[TeamTradeProfile], list[TradeProposal], dict[str, ManagerTendency]]:
    all_needs = [analyze_team_needs(t, config) for t in snapshot["teams"]]
    tendencies = build_manager_tendencies(snapshot, intel)
    needs_by_owner = {n.owner_id: n for n in all_needs}

    profiles: list[TeamTradeProfile] = []
    my_profile: TeamTradeProfile | None = None
    for team in snapshot["teams"]:
        oid = team.get("owner_id", "")
        needs = needs_by_owner.get(oid) or analyze_team_needs(team, config)
        tendency = tendencies.get(oid) or ManagerTendency(
            manager=team["owner_name"],
            team=team["team_name"],
            owner_id=oid,
            trade_count=0,
            picks_traded=0,
            avg_trade_age=0,
            draft_rb_early_pct=0,
            draft_wr_early_pct=0,
            draft_youth_pct=0,
            archetype="Unknown",
            likes=[],
            notes="",
        )
        profile = build_team_trade_profile(
            team, needs, intel, tendency, config,
            fc_client=fc_client, fp_client=fp_client,
        )
        if team.get("is_mine"):
            my_profile = profile
        profiles.append(profile)

    if not my_profile:
        return profiles, [], tendencies

    my_needs = needs_by_owner.get(my_profile.owner_id) or analyze_team_needs(my_team, config)
    if keeper_plan and keeper_plan.remaining_needs:
        config = {
            **config,
            "notes": {
                **config.get("notes", {}),
                "target_positions": list(dict.fromkeys(
                    (config.get("notes", {}).get("target_positions") or [])
                    + keeper_plan.remaining_needs
                )),
            },
        }
    all_proposals: list[TradeProposal] = []
    for other in profiles:
        if other.owner_id == my_profile.owner_id:
            continue
        match_score = 0.0
        for pos in my_profile.desperate_for:
            if pos in other.surplus_at:
                match_score += 2
        for pos in my_profile.surplus_at:
            if pos in other.desperate_for:
                match_score += 3
        other.best_match_score = match_score
        proposals = build_trade_proposals(
            my_team, my_needs, my_profile, other, intel, config,
            max_proposals=2, fc_client=fc_client, fp_client=fp_client,
        )
        all_proposals.extend(proposals)

    all_proposals.sort(key=lambda p: (p.leverage_score, p.value_delta), reverse=True)
    profiles.sort(key=lambda p: p.best_match_score, reverse=True)
    return profiles, all_proposals[:20], tendencies


def proposals_to_legacy_matches(proposals: list[TradeProposal]) -> list[TradeMatch]:
    matches: list[TradeMatch] = []
    for p in proposals:
        give = p.you_send_players + [f"Pick: {x}" for x in p.you_send_picks]
        get = p.you_receive_players + [f"Pick: {x}" for x in p.you_receive_picks]
        matches.append(
            TradeMatch(
                target_manager=p.target_manager,
                target_team=p.target_team,
                you_give=give,
                you_get=get,
                rationale=f"{p.why_they_accept} {p.why_you_win}",
                leverage_score=p.leverage_score,
                you_give_value=p.send_value,
                you_get_value=p.receive_value,
                value_delta=p.value_delta,
                confidence=p.confidence,
                offer_picks=p.you_send_picks,
                receive_picks=p.you_receive_picks,
            )
        )
    return matches
