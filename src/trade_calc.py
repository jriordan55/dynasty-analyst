"""Interactive trade calculator — FantasyCalc values with letter grades."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.fantasycalc import FantasyCalcClient


@dataclass
class TradeAsset:
    label: str
    kind: str  # player | pick
    value: int
    position: str = ""
    manager: str | None = None


@dataclass
class TradeVerdict:
    grade: str
    send_total: int
    receive_total: int
    delta: int
    delta_pct: float
    verdict: str
    recommendation: str
    warnings: list[str] = field(default_factory=list)
    send_assets: list[TradeAsset] = field(default_factory=list)
    receive_assets: list[TradeAsset] = field(default_factory=list)


def _letter_grade(delta_pct: float) -> str:
    """Grade from receiver's perspective (positive delta = you win)."""
    if delta_pct >= 18:
        return "A+"
    if delta_pct >= 12:
        return "A"
    if delta_pct >= 7:
        return "B+"
    if delta_pct >= 3:
        return "B"
    if delta_pct >= -3:
        return "C"
    if delta_pct >= -8:
        return "D"
    if delta_pct >= -15:
        return "D-"
    return "F"


def _recommendation(grade: str, delta: int) -> str:
    tips = {
        "A+": "Smash accept — significant value edge.",
        "A": "Strong win — pull the trigger.",
        "B+": "Good deal — minor edge in your favor.",
        "B": "Slight edge — reasonable if it fills a need.",
        "C": "Fair trade — neither side wins big.",
        "D": "You lose value — counter or pass.",
        "D-": "Overpaying — only take if desperate.",
        "F": "Reject — lopsided against you.",
    }
    base = tips.get(grade, "Review manually.")
    if delta > 0 and grade in ("C", "D"):
        return f"{base} Small numeric edge may not justify roster fit cost."
    return base


def league_player_pool(snapshot: dict, fc: FantasyCalcClient) -> list[dict]:
    """All skill players in synced league with FC values."""
    pool: list[dict] = []
    seen: set[str] = set()
    for team in snapshot.get("teams") or []:
        mgr = team.get("owner_name") or "Unknown"
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in {"QB", "RB", "WR", "TE"}:
                continue
            name = p.get("name") or ""
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            fc_v = fc.get(name, p.get("id"))
            pool.append({
                "name": name,
                "position": pos,
                "team": p.get("team") or "",
                "manager": mgr,
                "age": p.get("age"),
                "fc_value": fc_v.value if fc_v else 0,
                "fc_rank": fc_v.overall_rank if fc_v else None,
                "sleeper_id": p.get("id"),
            })
    pool.sort(key=lambda x: x["fc_value"], reverse=True)
    return pool


def league_pick_pool(snapshot: dict, fc: FantasyCalcClient) -> list[dict]:
    picks: list[dict] = []
    for team in snapshot.get("teams") or []:
        mgr = team.get("owner_name") or "Unknown"
        for pk in team.get("draft_picks") or []:
            season = str(pk.get("season") or "")
            rnd = int(pk.get("round") or 0)
            slot = pk.get("roster_id")
            fc_v = fc.pick_value(season, rnd)
            label = f"{season} R{rnd}"
            if pk.get("original_owner") and pk.get("original_owner") != team.get("roster_id"):
                label += " (traded)"
            picks.append({
                "name": fc_v.name if fc_v else label,
                "label": label,
                "manager": mgr,
                "fc_value": fc_v.value if fc_v else 0,
                "season": season,
                "round": rnd,
            })
    picks.sort(key=lambda x: x["fc_value"], reverse=True)
    return picks


def evaluate_trade(
    fc: FantasyCalcClient,
    send_players: list[str],
    receive_players: list[str],
    send_picks: list[str] | None = None,
    receive_picks: list[str] | None = None,
    sleeper_ids: dict[str, str] | None = None,
    asset_meta: dict[str, dict] | None = None,
) -> TradeVerdict:
    """Grade a trade package A–F using FantasyCalc totals."""
    ids = sleeper_ids or {}
    meta = asset_meta or {}
    send_assets: list[TradeAsset] = []
    recv_assets: list[TradeAsset] = []
    send_total = 0
    recv_total = 0
    warnings: list[str] = []

    for name in send_players:
        fc_v = fc.get(name, ids.get(name))
        val = fc_v.value if fc_v else 0
        if not fc_v:
            warnings.append(f"No FantasyCalc value for {name}")
        m = meta.get(name, {})
        send_assets.append(
            TradeAsset(
                label=name,
                kind="player",
                value=val,
                position=m.get("position", fc_v.position if fc_v else ""),
                manager=m.get("manager"),
            )
        )
        send_total += val

    for name in receive_players:
        fc_v = fc.get(name, ids.get(name))
        val = fc_v.value if fc_v else 0
        if not fc_v:
            warnings.append(f"No FantasyCalc value for {name}")
        m = meta.get(name, {})
        recv_assets.append(
            TradeAsset(
                label=name,
                kind="player",
                value=val,
                position=m.get("position", fc_v.position if fc_v else ""),
                manager=m.get("manager"),
            )
        )
        recv_total += val

    for label in send_picks or []:
        fc_v = _resolve_pick(fc, label)
        val = fc_v.value if fc_v else 0
        send_assets.append(TradeAsset(label=label, kind="pick", value=val))
        send_total += val

    for label in receive_picks or []:
        fc_v = _resolve_pick(fc, label)
        val = fc_v.value if fc_v else 0
        recv_assets.append(TradeAsset(label=label, kind="pick", value=val))
        recv_total += val

    delta = recv_total - send_total
    base = max(send_total, recv_total, 1)
    delta_pct = delta / base * 100
    grade = _letter_grade(delta_pct)

    if send_total == 0 and recv_total == 0:
        grade = "—"
        verdict = "Add assets to both sides"
    elif abs(delta_pct) <= 3:
        verdict = "Fair trade"
    elif delta > 0:
        verdict = "You win"
    else:
        verdict = "You lose"

    return TradeVerdict(
        grade=grade,
        send_total=send_total,
        receive_total=recv_total,
        delta=delta,
        delta_pct=round(delta_pct, 1),
        verdict=verdict,
        recommendation=_recommendation(grade, delta) if grade != "—" else "Add players or picks to evaluate.",
        warnings=warnings,
        send_assets=send_assets,
        receive_assets=recv_assets,
    )


def _resolve_pick(fc: FantasyCalcClient, label: str):
    import re
    m = re.search(r"(\d{4}).*?[Rr](?:d)?\s*(\d+)", label)
    if m:
        return fc.pick_value(m.group(1), int(m.group(2)))
    return fc._picks.get(label.lower())
