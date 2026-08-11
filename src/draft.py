from __future__ import annotations

from src.adp import lookup_adp
from src.analysis import CORE_POSITIONS, analyze_team_needs
from src.player_intel import positional_scarcity
from src.models import (
    DraftBoardEntry,
    KeeperPlan,
    ManagerDraftProfile,
    PickRecommendation,
    Player,
    TeamNeeds,
    UpsideTarget,
)


def pick_no_for_slot_round(slot: int, round_no: int, teams: int) -> int:
    """Snake draft pick number for a given slot and round."""
    if round_no % 2 == 1:
        return (round_no - 1) * teams + slot
    return round_no * teams - slot + 1


def round_for_pick_no(pick_no: int, teams: int) -> int:
    return (pick_no - 1) // teams + 1


def upcoming_pick_numbers(
    slot: int,
    teams: int,
    from_pick: int,
    count: int = 4,
    max_rounds: int = 16,
) -> list[int]:
    """Your next snake pick numbers starting at or after from_pick."""
    picks: list[int] = []
    for rnd in range(1, max_rounds + 1):
        p = pick_no_for_slot_round(slot, rnd, teams)
        if p >= from_pick:
            picks.append(p)
    picks.sort()
    return picks[:count]


def draft_teams(draft: dict | None, fallback: int = 12) -> int:
    if not draft:
        return fallback
    return draft.get("teams") or len(draft.get("draft_order") or {}) or fallback


def adp_window_for_pick(pick_no: int, on_clock: bool) -> tuple[int, int]:
    """ADP range likely still available at this pick."""
    if on_clock:
        return max(1, pick_no - 5), pick_no + 25
    return max(1, pick_no - 10), pick_no + 8


def format_pick_label(pick_no: int, teams: int) -> str:
    rnd = round_for_pick_no(pick_no, teams)
    slot_in_round = pick_no - (rnd - 1) * teams
    return f"Pick {pick_no} (Rd {rnd}, #{slot_in_round})"


def _adp_tier(adp: int | None) -> int:
    if not adp:
        return 99
    if adp <= 24:
        return 1
    if adp <= 48:
        return 2
    if adp <= 72:
        return 3
    if adp <= 120:
        return 4
    if adp <= 180:
        return 5
    return 6


def _drafted_names(draft: dict | None) -> set[str]:
    names: set[str] = set()
    if draft:
        for pick in draft.get("picks", []):
            if pick.get("player_name"):
                names.add(pick["player_name"].lower())
    return names


def _keeper_names_for_roster(draft: dict | None, roster_id: int) -> list[str]:
    if not draft:
        return []
    names = []
    for pick in draft.get("picks", []):
        if pick.get("roster_id") == roster_id and pick.get("is_keeper") and pick.get("player_name"):
            names.append(pick["player_name"])
    return names


def _news_flags_for_player(name: str, news: list[dict], injuries: list[dict]) -> str:
    name_lower = name.lower()
    parts = [p for p in name_lower.split() if len(p) > 2]
    flags: list[str] = []

    for inj in injuries:
        if inj.get("name", "").lower() == name_lower:
            flags.append(f"Injury: {inj.get('status', 'Unknown')}")

    for item in news:
        text = f"{item.get('headline', '')} {item.get('description', '')}".lower()
        if item.get("player", "").lower() == name_lower or (parts and all(p in text for p in parts)):
            flags.append("News")
            break

    return " · ".join(flags) if flags else ""


def _virtual_team_after_keepers(team: dict, keeper_names: set[str]) -> dict:
    kept = []
    for p in team.get("players", []):
        if p.get("name") in keeper_names and p.get("position") in CORE_POSITIONS:
            kept.append(p)
    return {**team, "players": kept}


def roster_fit_score(
    position: str,
    adp: int | None,
    needs: TeamNeeds,
    pos_counts: dict[str, int],
) -> tuple[float, str]:
    score = 45.0
    reasons: list[str] = []

    if position in needs.desperate_for:
        score += 28
        reasons.append(f"need {position}")
    elif position in needs.starter_gaps:
        score += 12 * min(needs.starter_gaps[position], 2)
        reasons.append(f"fills {position} gap")

    if position in needs.surplus:
        score -= 18 * min(needs.surplus[position], 2)
        reasons.append(f"{position} surplus")

    if adp:
        score += max(0, 35 - adp / 4)
        if adp <= 36:
            reasons.append("elite ADP")

    count = pos_counts.get(position, 0)
    if count == 0 and position in CORE_POSITIONS:
        score += 8
        reasons.append(f"no {position} yet")

    score = min(100.0, max(0.0, score))
    return score, "; ".join(reasons[:3]) or "best available"


def build_keeper_plan(
    my_team: dict,
    keeper_names: list[str],
    adp_map: dict[str, Player],
    config: dict,
    draft: dict | None = None,
) -> KeeperPlan:
    max_keepers = int(config.get("max_keepers") or config.get("league", {}).get("settings", {}).get("max_keepers") or 4)
    keeper_set = set(keeper_names)
    virtual = _virtual_team_after_keepers(my_team, keeper_set)
    needs = analyze_team_needs(virtual, config)

    keeper_rows = []
    for name in keeper_names:
        player = next((p for p in my_team.get("players", []) if p.get("name") == name), None)
        adp_entry = lookup_adp(name, adp_map)
        round_cost = None
        if draft:
            for pick in draft.get("picks", []):
                if pick.get("player_name") == name and pick.get("is_keeper"):
                    round_cost = pick.get("round")
                    break
        keeper_rows.append({
            "name": name,
            "position": player.get("position") if player else "?",
            "adp": adp_entry.adp if adp_entry else None,
            "keeper_round": round_cost,
        })

    priorities = list(needs.desperate_for) or list(needs.starter_gaps.keys()) or ["RB", "WR"]
    return KeeperPlan(
        keepers=keeper_rows,
        max_keepers=max_keepers,
        post_keeper_counts=needs.position_counts,
        remaining_needs=needs.desperate_for or [p for p, g in needs.starter_gaps.items()],
        draft_priorities=priorities,
    )


def build_draft_board(
    adp_map: dict[str, Player],
    snapshot: dict,
    config: dict,
    keeper_names: list[str],
    news: list[dict] | None = None,
    injuries: list[dict] | None = None,
    intel=None,
    limit: int = 75,
) -> list[DraftBoardEntry]:
    news = news or []
    injuries = injuries or []
    draft = snapshot.get("draft")
    drafted = _drafted_names(draft)
    scarcity = positional_scarcity(draft)

    my_team = next((t for t in snapshot["teams"] if t.get("is_mine")), None)
    if not my_team:
        return []

    virtual = _virtual_team_after_keepers(my_team, set(keeper_names))
    needs = analyze_team_needs(virtual, config)
    pos_counts = dict(needs.position_counts)

    entries: list[DraftBoardEntry] = []
    for player in sorted(adp_map.values(), key=lambda p: p.adp or 999):
        if player.name.lower() in drafted:
            continue
        if player.position not in CORE_POSITIONS:
            continue
        fit, reason = roster_fit_score(player.position, player.adp, needs, pos_counts)
        if scarcity.get(player.position, 0) > 15:
            fit += 8
            reason = f"{reason}; {player.position} run" if reason else f"{player.position} run"
        if intel:
            fit, reason = intel.adjust_fit_score(player.name, player.position, fit, reason)
        flag = intel.flags_text(player.name, player.position) if intel else _news_flags_for_player(player.name, news, injuries)
        adp_val = player.adp
        upside_score = 0.0
        upside_note = ""
        if intel:
            ctx = intel.get(player.name, player.position)
            adp_val = ctx.blended_adp or adp_val
            upside_score = ctx.upside_score
            upside_note = ctx.upside_note
        entries.append(
            DraftBoardEntry(
                player=player.name,
                position=player.position,
                adp=adp_val,
                team=player.team,
                fit_score=round(fit, 1),
                fit_reason=reason,
                news_flag=flag,
                tier=_adp_tier(adp_val),
                upside_score=round(upside_score, 1),
                upside_note=upside_note,
            )
        )

    entries.sort(key=lambda e: (-e.fit_score, e.adp or 999))
    return entries[:limit]


def build_upside_targets(
    adp_map: dict[str, Player],
    snapshot: dict,
    intel=None,
    limit: int = 25,
) -> list[UpsideTarget]:
    draft = snapshot.get("draft")
    drafted = _drafted_names(draft)
    targets: list[UpsideTarget] = []

    for player in adp_map.values():
        if player.name.lower() in drafted:
            continue
        if player.position not in CORE_POSITIONS:
            continue
        if not intel:
            continue
        ctx = intel.get(player.name, player.position)
        if ctx.injury_penalty >= 30 or ctx.upside_score < 25:
            continue
        targets.append(
            UpsideTarget(
                player=player.name,
                position=player.position,
                adp=ctx.blended_adp or player.adp,
                upside_score=ctx.upside_score,
                insight=ctx.upside_note or "High-upside profile",
                team=player.team,
            )
        )

    targets.sort(key=lambda t: (-t.upside_score, t.adp or 999))
    return targets[:limit]


def recommend_picks(
    board: list[DraftBoardEntry],
    limit: int = 5,
    target_pick: int | None = None,
    on_clock: bool = False,
    teams: int = 12,
) -> list[PickRecommendation]:
    """Recommend picks — optionally scoped to a snake pick number."""
    if target_pick:
        lo, hi = adp_window_for_pick(target_pick, on_clock)
        pool = [
            e for e in board
            if e.adp and lo <= e.adp <= hi
            and "Injury: Out" not in e.news_flag
            and "Injury: Doubtful" not in e.news_flag
        ]
        if not pool:
            pool = [e for e in board if e.adp and e.adp >= target_pick - 15]
    else:
        pool = list(board)

    def sort_key(e: DraftBoardEntry) -> tuple:
        reach_penalty = 0
        if target_pick and e.adp and e.adp < target_pick - 12:
            reach_penalty = 20
        return (-(e.fit_score + e.upside_score * 0.3 - reach_penalty), e.adp or 999)

    recs: list[PickRecommendation] = []
    seen_pos: dict[str, int] = {}

    for entry in sorted(pool, key=sort_key):
        if entry.news_flag.lower().startswith("injury: out") or "injury: doubtful" in entry.news_flag.lower():
            continue
        if "Injury: Out" in entry.news_flag or "Injury: Doubtful" in entry.news_flag:
            continue
        pos_count = seen_pos.get(entry.position, 0)
        if pos_count >= 2 and entry.fit_score < 70 and not on_clock:
            continue

        reason = entry.fit_reason
        if entry.upside_note:
            reason = f"{reason} · {entry.upside_note}" if reason else entry.upside_note
        if entry.news_flag:
            reason = f"{reason} · {entry.news_flag}" if reason else entry.news_flag
        if target_pick and entry.adp:
            delta = entry.adp - target_pick
            if on_clock and delta <= 0:
                avail = "great value at this pick"
            elif on_clock:
                avail = f"slight reach (+{delta} vs pick {target_pick})"
            elif abs(delta) <= 5:
                avail = f"should be there at pick {target_pick}"
            elif delta > 5:
                avail = f"may fall to pick {target_pick}"
            else:
                avail = f"unlikely to last until pick {target_pick}"
            reason = f"{reason} · {avail}" if reason else avail

        recs.append(
            PickRecommendation(
                player=entry.player,
                position=entry.position,
                adp=entry.adp,
                fit_score=entry.fit_score,
                reason=reason,
                target_pick=target_pick,
                upside_score=entry.upside_score,
            )
        )
        seen_pos[entry.position] = pos_count + 1
        if len(recs) >= limit:
            break

    if len(recs) < limit:
        for entry in board:
            if any(r.player == entry.player for r in recs):
                continue
            if "Injury: Out" in entry.news_flag:
                continue
            recs.append(
                PickRecommendation(
                    player=entry.player,
                    position=entry.position,
                    adp=entry.adp,
                    fit_score=entry.fit_score,
                    reason=entry.fit_reason,
                    target_pick=target_pick,
                    upside_score=entry.upside_score,
                )
            )
            if len(recs) >= limit:
                break
    return recs


def recommend_for_my_slot(
    board: list[DraftBoardEntry],
    draft: dict | None,
    my_slot: int | None,
    teams: int = 12,
    on_clock: bool = False,
    limit: int = 5,
) -> tuple[list[PickRecommendation], list[int], int | None]:
    """Pick recommendations tied to your snake draft slot."""
    teams = draft_teams(draft, teams)
    if not my_slot:
        return recommend_picks(board, limit=limit), [], None

    current_pick = 1
    if draft:
        current_pick = len(draft.get("picks", [])) + 1

    if on_clock:
        target = current_pick
    else:
        upcoming = upcoming_pick_numbers(my_slot, teams, current_pick, count=1)
        target = upcoming[0] if upcoming else pick_no_for_slot_round(my_slot, 1, teams)

    recs = recommend_picks(
        board, limit=limit, target_pick=target, on_clock=on_clock, teams=teams,
    )
    next_picks = upcoming_pick_numbers(my_slot, teams, current_pick, count=4)
    return recs, next_picks, target


def _early_draft_positions(draft: dict | None, roster_id: int) -> list[str]:
    if not draft:
        return []
    positions = []
    for pick in draft.get("picks", []):
        if pick.get("roster_id") == roster_id and not pick.get("is_keeper"):
            if pick.get("round", 99) <= 5:
                pos = pick.get("position") or pick.get("metadata", {}).get("position", "")
                if pos:
                    positions.append(pos)
    return positions


def _tendency_label(counts: dict[str, int], keeper_positions: list[str], early_picks: list[str]) -> str:
    rb, wr = counts.get("RB", 0), counts.get("WR", 0)
    early = early_picks or keeper_positions[:2]

    if early.count("RB") >= 2 or rb >= wr + 2:
        return "RB-focused"
    if early.count("WR") >= 2 or wr >= rb + 2:
        return "WR-heavy"
    if early.count("QB") >= 1 or counts.get("QB", 0) >= 2:
        return "QB depth"
    if early.count("TE") >= 1 or counts.get("TE", 0) >= 2:
        return "TE premium"
    return "Balanced"


def _draft_prediction(profile: str, slot: int | None, counts: dict[str, int]) -> str:
    if profile == "RB-focused":
        return "Expect early RB picks; WR value may fall to mid rounds"
    if profile == "WR-heavy":
        return "Likely loads WR early — RB runs create opening at RB"
    if profile == "QB depth":
        return "May take QB earlier than ADP — wait on QB if you need one"
    if slot and slot <= 4:
        return "Early pick — likely takes best elite RB/WR available"
    if slot and slot >= 10:
        return "Late slot — may reach for RB1 or take value WR/QB"
    if counts.get("RB", 0) <= 2:
        return "Thin at RB — expect RB attention in first 4 rounds"
    return "Watch for positional runs based on roster holes"


def build_manager_profiles(
    snapshot: dict,
    config: dict,
) -> list[ManagerDraftProfile]:
    draft = snapshot.get("draft")
    slot_by_user = (draft or {}).get("draft_order", {})
    profiles: list[ManagerDraftProfile] = []

    for team in snapshot.get("teams", []):
        needs = analyze_team_needs(team, config)
        owner_id = team.get("owner_id", "")
        slot = slot_by_user.get(owner_id)
        keeper_positions = []
        if draft:
            for pick in draft.get("picks", []):
                if pick.get("roster_id") == team.get("roster_id") and pick.get("is_keeper"):
                    keeper_positions.append(pick.get("position") or "?")

        early = _early_draft_positions(draft, team.get("roster_id", 0))
        counts = needs.position_counts
        tendency = _tendency_label(counts, keeper_positions, early)
        profiles.append(
            ManagerDraftProfile(
                manager=team.get("owner_name", "Unknown"),
                team=team.get("team_name", ""),
                draft_slot=slot,
                rb_count=counts.get("RB", 0),
                wr_count=counts.get("WR", 0),
                qb_count=counts.get("QB", 0),
                te_count=counts.get("TE", 0),
                tendency=tendency,
                draft_prediction=_draft_prediction(tendency, slot, counts),
                keeper_positions=keeper_positions,
            )
        )

    profiles.sort(key=lambda p: p.draft_slot or 99)
    return profiles


def sync_keepers_from_draft(my_team: dict, draft: dict | None) -> list[str]:
    if not draft or not my_team:
        return []
    return _keeper_names_for_roster(draft, my_team.get("roster_id"))
