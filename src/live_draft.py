"""Live Sleeper draft — pick / avoid analysis from app stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.adp_momentum import lookup_momentum, top_movers
from src.draft import (
    adp_window_for_pick,
    build_draft_board,
    effective_draft_status,
    format_pick_label,
    is_pre_draft,
    recommend_for_my_slot,
)
from src.models import DraftBoardEntry, PickRecommendation
from src.sleeper import SleeperClient
from src.vegas_signals import build_vegas_index, get_vegas_signal


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
    adp_change_7d: float = 0.0
    adp_momentum_arrow: str = "→"
    vgs: int | None = None
    vgs_trend: float = 0.0
    vegas_edge: float = 0.0


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
    draft_label: str = "League draft"
    is_mock: bool = False
    draft_type: str = "snake"
    risers: list = field(default_factory=list)
    fallers: list = field(default_factory=list)


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
    *,
    vegas_index: dict | None = None,
    fc_trend_by_name: dict | None = None,
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
    if vegas_index:
        v = get_vegas_signal(vegas_index, getattr(entry, "player", "") or "")
        if v and v.edge >= 5:
            tags.append("VEGAS+")
    if fc_trend_by_name:
        name = (getattr(entry, "player", "") or "").lower()
        mom = lookup_momentum(
            getattr(entry, "player", "") or "",
            float(adp) if adp else None,
            fc_trend_30d=fc_trend_by_name.get(name, 0),
        )
        if mom.label == "RISER":
            tags.append("RISER")
    return tags[:4]


def build_avoid_list(
    board: list[DraftBoardEntry],
    *,
    target_pick: int | None,
    on_clock: bool,
    pre_draft: bool,
    limit: int = 8,
    vegas_index: dict | None = None,
    fc_trend_by_name: dict | None = None,
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

        if fc_trend_by_name:
            mom = lookup_momentum(
                entry.player,
                float(entry.adp) if entry.adp else None,
                fc_trend_30d=fc_trend_by_name.get(entry.player.lower(), 0),
            )
            if mom.label == "FALLER" and on_clock:
                reasons.append(("medium", f"7d ADP faller ({mom.arrow} {abs(mom.change_7d):.1f})"))

        if vegas_index:
            v = get_vegas_signal(vegas_index, entry.player)
            if v and v.edge <= -8 and on_clock:
                reasons.append(("medium", f"Vegas fade — books ~{v.vegas_pts:.0f} vs our {v.our_pts:.0f}"))

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
    fc_trend_by_name: dict,
    vegas_index: dict,
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
        fc_trend = fc_trend_by_name.get(rec.player.lower(), 0)
        mom = lookup_momentum(rec.player, float(rec.adp) if rec.adp else None, fc_trend_30d=fc_trend)
        vgs_sig = get_vegas_signal(vegas_index, rec.player)
        tags = _pick_tags(
            entry or rec,
            target_pick,
            on_clock,
            pre_draft,
            vegas_index=vegas_index,
            fc_trend_by_name=fc_trend_by_name,
        )
        reason = rec.reason
        if vgs_sig and abs(vgs_sig.edge) >= 3:
            reason = f"{reason} · Vegas {vgs_sig.edge:+.0f} pt edge" if reason else f"Vegas {vgs_sig.edge:+.0f} pt edge"
        if mom.label != "STABLE":
            reason = f"{reason} · 7d ADP {mom.label.lower()} ({mom.arrow}{abs(mom.change_7d):.1f})" if reason else f"7d ADP {mom.label.lower()}"
        live.append(
            LivePick(
                player=rec.player,
                position=rec.position,
                adp=rec.adp,
                fit_score=rec.fit_score,
                upside_score=rec.upside_score,
                fc_value=fc_val,
                grade=_quick_grade(rec.adp, rec.upside_score, news_flag),
                reason=reason,
                tags=tags,
                rank=i,
                adp_change_7d=mom.change_7d,
                adp_momentum_arrow=mom.arrow,
                vgs=vgs_sig.vgs if vgs_sig else None,
                vgs_trend=vgs_sig.vgs_trend if vgs_sig else 0.0,
                vegas_edge=vgs_sig.edge if vgs_sig else 0.0,
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
    is_my_pick = bool(
        on_clock
        and (
            on_clock.get("is_mine")
            or (my_user_id and str(on_clock.get("user_id")) == str(my_user_id))
        )
    )

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
    fc_trend_by_name = {name.lower(): val.trend_30d for name, val in fc._by_name.items()}

    vegas_index: dict = {}
    try:
        vegas_rows = [
            (e.player, e.position, float(e.adp) if e.adp else None)
            for e in board
        ]
        vegas_index = build_vegas_index(fc, vegas_rows)
    except Exception:
        pass

    picks = _enrich_picks(
        recs, board, fc_by_name, fc_trend_by_name, vegas_index,
        target_pick=target_pick,
        on_clock=is_my_pick,
        pre_draft=pre_draft,
    )
    avoids = build_avoid_list(
        board,
        target_pick=target_pick,
        on_clock=is_my_pick,
        pre_draft=pre_draft,
        vegas_index=vegas_index,
        fc_trend_by_name=fc_trend_by_name,
    )

    mover_rows = [(e.player, float(e.adp) if e.adp else None, fc_trend_by_name.get(e.player.lower(), 0)) for e in board[:80]]
    risers, fallers = top_movers(mover_rows, limit=6)

    plan = analyst.draft_plan(keepers)
    recent = list(reversed((draft or {}).get("picks", [])[-18:]))

    return LiveDraftAnalysis(
        draft=draft,
        status=effective_draft_status(draft) if draft else "unknown",
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
        risers=risers,
        fallers=fallers,
        updated_at=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        pre_draft=pre_draft,
        draft_label=(draft or {}).get("draft_label") or "League draft",
        is_mock=bool((draft or {}).get("is_mock")),
        draft_type=(draft or {}).get("type") or "snake",
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
