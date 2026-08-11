from __future__ import annotations

from src.adp import lookup_adp
from src.analysis import CORE_POSITIONS, analyze_team_needs
from src.models import (
    DraftBoardEntry,
    KeeperPlan,
    ManagerDraftProfile,
    PickRecommendation,
    Player,
    TeamNeeds,
)


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
    limit: int = 75,
) -> list[DraftBoardEntry]:
    news = news or []
    injuries = injuries or []
    draft = snapshot.get("draft")
    drafted = _drafted_names(draft)

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
        flag = _news_flags_for_player(player.name, news, injuries)
        entries.append(
            DraftBoardEntry(
                player=player.name,
                position=player.position,
                adp=player.adp,
                team=player.team,
                fit_score=round(fit, 1),
                fit_reason=reason,
                news_flag=flag,
                tier=_adp_tier(player.adp),
            )
        )

    entries.sort(key=lambda e: (-e.fit_score, e.adp or 999))
    return entries[:limit]


def recommend_picks(
    board: list[DraftBoardEntry],
    limit: int = 5,
) -> list[PickRecommendation]:
    recs: list[PickRecommendation] = []
    seen_pos: dict[str, int] = {}

    for entry in sorted(board, key=lambda e: (-e.fit_score, e.adp or 999)):
        if entry.news_flag.startswith("Injury"):
            continue
        pos_count = seen_pos.get(entry.position, 0)
        if pos_count >= 2 and entry.fit_score < 70:
            continue
        recs.append(
            PickRecommendation(
                player=entry.player,
                position=entry.position,
                adp=entry.adp,
                fit_score=entry.fit_score,
                reason=entry.fit_reason + (f" · {entry.news_flag}" if entry.news_flag else ""),
            )
        )
        seen_pos[entry.position] = pos_count + 1
        if len(recs) >= limit:
            break

    if len(recs) < limit:
        for entry in board:
            if any(r.player == entry.player for r in recs):
                continue
            recs.append(
                PickRecommendation(
                    player=entry.player,
                    position=entry.position,
                    adp=entry.adp,
                    fit_score=entry.fit_score,
                    reason=entry.fit_reason,
                )
            )
            if len(recs) >= limit:
                break
    return recs


def _tendency_label(counts: dict[str, int], keeper_positions: list[str]) -> str:
    rb, wr = counts.get("RB", 0), counts.get("WR", 0)
    early = keeper_positions[:2]

    if rb >= wr + 2 or early.count("RB") >= 2:
        return "RB-focused"
    if wr >= rb + 2 or early.count("WR") >= 2:
        return "WR-heavy"
    if counts.get("QB", 0) >= 2:
        return "QB depth"
    if counts.get("TE", 0) >= 2:
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

        counts = needs.position_counts
        tendency = _tendency_label(counts, keeper_positions)
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
