"""Live Sleeper draft — pick / avoid analysis from app stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.draft import (
    adp_window_for_pick,
    build_draft_board,
    format_pick_label,
    is_pre_draft,
    recommend_for_my_slot,
)
from src.models import DraftBoardEntry, PickRecommendation
from src.sleeper import SleeperClient


@dataclass
class LivePick:
    player: str
    position: str
    adp: int | None
    fit_score: float
    upside_score: float
    fc_value: int | None
    grade: str
    reason: str
    tags: list[str] = field(default_factory=list)
    rank: int = 0


@dataclass
class AvoidPlayer:
    player: str
    position: str
    adp: int | None
    reason: str
    severity: str  # high | medium


@dataclass
class LiveDraftAnalysis:
    draft: dict | None
    status: str
    is_my_pick: bool
    on_clock_manager: str
    on_clock_pick: int | None
    on_clock_round: int | None
    my_slot: int | None
    teams: int
    completed_picks: int
    total_picks: int
    picks: list[LivePick]
    avoids: list[AvoidPlayer]
    next_picks: list[int]
    target_pick: int | None
    draft_priorities: list[str]
    recent_picks: list[dict]
    updated_at: str
    pre_draft: bool


def fetch_sleeper_draft(league_id: str, username: str) -> dict | None:
    """Fresh draft state from Sleeper (no Streamlit cache)."""
    with SleeperClient(league_id) as sleeper:
        user = sleeper.resolve_user(username=username)
        my_id = user["user_id"] if user else None
        return sleeper.get_draft_state(my_id)


def _quick_grade(adp: int | None, upside: float, news_flag: str) -> str:
    flag = (news_flag or "").lower()
    if "injury: out" in flag or "injury: doubtful" in flag:
        return "F"
    if not adp:
        return "C"
    if adp <= 36:
        grade = "A"
    elif adp <= 72:
        grade = "B+"
    elif adp <= 120:
        grade = "B"
    elif adp <= 180:
        grade = "C+"
    else:
        grade = "D"
    if upside >= 45 and grade not in ("A", "B+"):
        grade = {"D": "C", "C+": "B", "B": "B+", "B+": "A"}.get(grade, grade)
    return grade


def _pick_tags(
    entry: DraftBoardEntry | PickRecommendation,
    target_pick: int | None,
    on_clock: bool,
    pre_draft: bool,
) -> list[str]:
    tags: list[str] = []
    fit = getattr(entry, "fit_score", 0) or 0
    adp = getattr(entry, "adp", None)
    upside = getattr(entry, "upside_score", 0) or 0
    reason = (getattr(entry, "fit_reason", None) or getattr(entry, "reason", "") or "").lower()

    if not pre_draft and fit >= 75:
        tags.append("BEST FIT")
    if not pre_draft and "need" in reason:
        tags.append("NEED")
    if on_clock and target_pick and adp and adp <= target_pick:
        tags.append("VALUE")
    elif target_pick and adp and adp <= target_pick - 3:
        tags.append("VALUE")
    if upside >= 40:
        tags.append("UPSIDE")
    return tags[:3]


def build_avoid_list(
    board: list[DraftBoardEntry],
    *,
    target_pick: int | None,
    on_clock: bool,
    pre_draft: bool,
    limit: int = 8,
) -> list[AvoidPlayer]:
    """Players to skip at the current pick window."""
    avoids: list[AvoidPlayer] = []
    if not board:
        return avoids

    lo, hi = (1, 999)
    if target_pick:
        lo, hi = adp_window_for_pick(target_pick, on_clock)

    for entry in board[:60]:
        flag = (entry.news_flag or "").lower()
        reasons: list[tuple[str, str]] = []

        if "injury: out" in flag:
            reasons.append(("high", "Injured — ruled out"))
        elif "injury: doubtful" in flag:
            reasons.append(("high", "Doubtful — avoid until cleared"))
        elif "injury:" in flag and on_clock:
            reasons.append(("medium", entry.news_flag))

        if on_clock and target_pick and entry.adp and entry.adp < target_pick - 14:
            reasons.append((
                "medium",
                f"Reach — ADP {entry.adp} is ~{target_pick - entry.adp} picks early",
            ))

        if not pre_draft:
            if entry.fit_score < 35 and "surplus" in (entry.fit_reason or "").lower():
                reasons.append(("high", f"Position surplus — {entry.fit_reason}"))
            elif entry.fit_score < 30:
                reasons.append(("medium", f"Poor roster fit ({entry.fit_score:.0f})"))

        if entry.adp and target_pick and entry.adp > hi + 12 and on_clock:
            reasons.append(("medium", f"Can wait — ADP {entry.adp} may fall"))

        if entry.upside_score < 12 and entry.adp and target_pick and entry.adp >= target_pick:
            reasons.append(("medium", "Low upside profile at this stage"))

        if not reasons:
            continue
        sev, reason = sorted(reasons, key=lambda x: 0 if x[0] == "high" else 1)[0]
        avoids.append(
            AvoidPlayer(
                player=entry.player,
                position=entry.position,
                adp=entry.adp,
                reason=reason,
                severity=sev,
            )
        )

    avoids.sort(key=lambda a: (0 if a.severity == "high" else 1, a.adp or 999))
    seen: set[str] = set()
    out: list[AvoidPlayer] = []
    for a in avoids:
        key = a.player.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
        if len(out) >= limit:
            break
    return out


def _enrich_picks(
    recs: list[PickRecommendation],
    board: list[DraftBoardEntry],
    fc_by_name: dict,
    *,
    target_pick: int | None,
    on_clock: bool,
    pre_draft: bool,
) -> list[LivePick]:
    board_map = {e.player.lower(): e for e in board}
    live: list[LivePick] = []
    for i, rec in enumerate(recs, 1):
        entry = board_map.get(rec.player.lower())
        news_flag = entry.news_flag if entry else ""
        fc = fc_by_name.get(rec.player.lower())
        fc_val = fc.value if fc else None
        tags = _pick_tags(
            entry or rec,
            target_pick,
            on_clock,
            pre_draft,
        )
        live.append(
            LivePick(
                player=rec.player,
                position=rec.position,
                adp=rec.adp,
                fit_score=rec.fit_score,
                upside_score=rec.upside_score,
                fc_value=fc_val,
                grade=_quick_grade(rec.adp, rec.upside_score, news_flag),
                reason=rec.reason,
                tags=tags,
                rank=i,
            )
        )
    return live


def analyze_live_draft(analyst, config: dict, draft: dict | None = None) -> LiveDraftAnalysis:
    """Build pick / avoid lists from Sleeper draft + analyst board."""
    if draft is None:
        draft = fetch_sleeper_draft(config["league_id"], config.get("username", ""))

    snapshot = analyst._ensure_snapshot()
    if draft and analyst._snapshot is not None:
        analyst._snapshot["draft"] = draft

    keepers = analyst.get_keepers()
    intel = analyst.intel()
    board = build_draft_board(
        analyst.adp_map, snapshot, config, keepers, intel=intel, limit=100,
    )

    my_team = next((t for t in snapshot.get("teams", []) if t.get("is_mine")), None)
    roster_id = my_team.get("roster_id") if my_team else None
    my_slot = (draft or {}).get("my_slot")
    teams = (draft or {}).get("teams") or 12
    pre_draft = is_pre_draft(draft)

    on_clock = (draft or {}).get("on_clock") or {}
    my_user_id = snapshot.get("my_user_id") or (draft or {}).get("my_user_id")
    is_my_pick = bool(on_clock and on_clock.get("user_id") == my_user_id)

    recs, next_picks, target_pick = recommend_for_my_slot(
        board,
        draft,
        my_slot,
        teams=teams,
        on_clock=is_my_pick,
        limit=6,
        roster_id=roster_id,
    )

    fc, _ = analyst._market_clients()
    fc_by_name = {name.lower(): val for name, val in fc._by_name.items()}

    picks = _enrich_picks(
        recs, board, fc_by_name,
        target_pick=target_pick,
        on_clock=is_my_pick,
        pre_draft=pre_draft,
    )
    avoids = build_avoid_list(
        board,
        target_pick=target_pick,
        on_clock=is_my_pick,
        pre_draft=pre_draft,
    )

    plan = analyst.draft_plan(keepers)
    recent = list(reversed((draft or {}).get("picks", [])[-18:]))

    return LiveDraftAnalysis(
        draft=draft,
        status=(draft or {}).get("status") or "unknown",
        is_my_pick=is_my_pick,
        on_clock_manager=on_clock.get("manager") or "—",
        on_clock_pick=on_clock.get("pick_no"),
        on_clock_round=on_clock.get("round"),
        my_slot=my_slot,
        teams=teams,
        completed_picks=(draft or {}).get("completed_picks") or 0,
        total_picks=(draft or {}).get("total_picks") or teams * 16,
        picks=picks,
        avoids=avoids,
        next_picks=next_picks,
        target_pick=target_pick,
        draft_priorities=list(plan.draft_priorities or []),
        recent_picks=recent,
        updated_at=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        pre_draft=pre_draft,
    )


def next_pick_label(analysis: LiveDraftAnalysis) -> str:
    if analysis.is_my_pick and analysis.on_clock_pick:
        return format_pick_label(analysis.on_clock_pick, analysis.teams)
    if analysis.target_pick:
        return format_pick_label(analysis.target_pick, analysis.teams)
    if analysis.my_slot:
        from src.draft import pick_no_for_slot_round
        return format_pick_label(pick_no_for_slot_round(analysis.my_slot, 1, analysis.teams), analysis.teams)
    return "your next pick"
