"""Trade-calculator asset pools and keeper recommendations."""

from __future__ import annotations

from dataclasses import dataclass

from src.analysis import CORE_POSITIONS
from src.adp import lookup_adp
from src.draft import keeper_names_from_draft, league_has_keepers
from src.fantasycalc import FantasyCalcClient
from src.trade_analysis import pick_label


@dataclass
class PickAsset:
    season: str
    round: int
    original_roster_id: int
    current_owner_id: int
    label: str
    fc_value: int
    is_keeper_round: bool = False
    traded: bool = False


def _draft_season(snapshot: dict) -> str:
    traded = (snapshot.get("trade_history") or {}).get("traded_picks") or []
    seasons = {str(tp.get("season")) for tp in traded if tp.get("season")}
    if seasons:
        return sorted(seasons)[-1]
    league = snapshot.get("league") or {}
    return str(league.get("season") or "2026")


def _keeper_rounds_by_roster(snapshot: dict) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {}
    draft = snapshot.get("draft") or {}
    for pick in draft.get("picks") or []:
        if pick.get("is_keeper") and pick.get("roster_id") is not None:
            rid = int(pick["roster_id"])
            out.setdefault(rid, set()).add(int(pick.get("round") or 0))
    return out


def _locked_keeper_players(snapshot: dict, my_team: dict) -> set[str]:
    return {n.lower() for n in keeper_names_from_draft(snapshot, my_team)}


def compute_pick_ownership(snapshot: dict) -> dict[tuple[str, int, int], int]:
    """Map (season, round, original_roster_id) -> current owner roster_id."""
    season = _draft_season(snapshot)
    draft = snapshot.get("draft") or {}
    rounds = int(draft.get("rounds") or 16)
    roster_ids = [int(t["roster_id"]) for t in snapshot.get("teams") or []]

    ownership: dict[tuple[str, int, int], int] = {}
    for rid in roster_ids:
        for rnd in range(1, rounds + 1):
            ownership[(season, rnd, rid)] = rid

    for tp in (snapshot.get("trade_history") or {}).get("traded_picks") or []:
        s = str(tp.get("season") or season)
        rnd = int(tp.get("round") or 0)
        orig = int(tp.get("roster_id") or 0)
        owner = int(tp.get("owner_id") or orig)
        if orig and rnd:
            ownership[(s, rnd, orig)] = owner

    # Also merge roster-held picks from Sleeper when present
    for team in snapshot.get("teams") or []:
        rid = int(team["roster_id"])
        for dp in team.get("draft_picks") or []:
            s = str(dp.get("season") or season)
            rnd = int(dp.get("round") or 0)
            orig = int(dp.get("roster_id") or dp.get("original_owner") or rid)
            owner = int(dp.get("owner_id") or rid)
            if orig and rnd:
                ownership[(s, rnd, orig)] = owner

    return ownership


def picks_for_roster(
    snapshot: dict,
    roster_id: int,
    fc: FantasyCalcClient,
    *,
    tradeable_only: bool = True,
) -> list[PickAsset]:
    season = _draft_season(snapshot)
    draft = snapshot.get("draft") or {}
    rounds = int(draft.get("rounds") or 16)
    ownership = compute_pick_ownership(snapshot)
    keeper_rounds = _keeper_rounds_by_roster(snapshot).get(roster_id, set())
    roster_ids = [int(t["roster_id"]) for t in snapshot.get("teams") or []]

    assets: list[PickAsset] = []
    for orig_rid in roster_ids:
        for rnd in range(1, rounds + 1):
            key = (season, rnd, orig_rid)
            current = ownership.get(key, orig_rid)
            if current != roster_id:
                continue
            is_keeper_round = rnd in keeper_rounds and orig_rid == roster_id
            if tradeable_only and is_keeper_round:
                continue
            traded = orig_rid != roster_id or current != orig_rid
            label = pick_label(season, rnd, orig_rid if orig_rid != roster_id else None)
            if orig_rid != roster_id:
                label = f"{season} Rd {rnd} (via trade, orig roster {orig_rid})"
            fc_v = fc.pick_value(season, rnd, orig_rid if rnd == 1 else None)
            assets.append(
                PickAsset(
                    season=season,
                    round=rnd,
                    original_roster_id=orig_rid,
                    current_owner_id=current,
                    label=label,
                    fc_value=fc_v.value if fc_v else 0,
                    is_keeper_round=is_keeper_round,
                    traded=traded or orig_rid != roster_id,
                )
            )
    assets.sort(key=lambda p: (p.round, p.original_roster_id))
    return assets


def my_tradeable_players(
    snapshot: dict,
    my_team: dict,
    fc: FantasyCalcClient,
) -> list[dict]:
    locked = _locked_keeper_players(snapshot, my_team)
    pool: list[dict] = []
    for p in my_team.get("players") or []:
        pos = p.get("position") or ""
        if pos not in CORE_POSITIONS:
            continue
        name = p.get("name") or ""
        if not name or name.lower() in locked:
            continue
        fc_v = fc.get(name, p.get("id"))
        pool.append({
            "name": name,
            "position": pos,
            "team": p.get("team") or "",
            "manager": my_team.get("owner_name") or "You",
            "age": p.get("age"),
            "fc_value": fc_v.value if fc_v else 0,
            "fc_rank": fc_v.overall_rank if fc_v else None,
            "sleeper_id": p.get("id"),
            "tradeable": True,
        })
    pool.sort(key=lambda x: x["fc_value"], reverse=True)
    return pool


def opponent_trade_pool(
    snapshot: dict,
    my_team: dict,
    fc: FantasyCalcClient,
) -> tuple[list[dict], list[dict]]:
    """Players and picks on other teams (receive side)."""
    my_rid = int(my_team["roster_id"])
    players: list[dict] = []
    picks: list[dict] = []

    for team in snapshot.get("teams") or []:
        if int(team["roster_id"]) == my_rid:
            continue
        mgr = team.get("owner_name") or "Unknown"
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in CORE_POSITIONS:
                continue
            name = p.get("name") or ""
            if not name:
                continue
            locked = _locked_keeper_players(snapshot, team)
            if name.lower() in locked:
                continue
            fc_v = fc.get(name, p.get("id"))
            players.append({
                "name": name,
                "position": pos,
                "team": p.get("team") or "",
                "manager": mgr,
                "age": p.get("age"),
                "fc_value": fc_v.value if fc_v else 0,
                "fc_rank": fc_v.overall_rank if fc_v else None,
                "sleeper_id": p.get("id"),
            })
        for asset in picks_for_roster(snapshot, int(team["roster_id"]), fc):
            picks.append({
                "name": asset.label,
                "label": asset.label,
                "manager": mgr,
                "fc_value": asset.fc_value,
                "season": asset.season,
                "round": asset.round,
                "traded": asset.traded,
            })

    players.sort(key=lambda x: x["fc_value"], reverse=True)
    picks.sort(key=lambda x: x["fc_value"], reverse=True)
    return players, picks


def my_trade_package(snapshot: dict, my_team: dict, fc: FantasyCalcClient) -> tuple[list[dict], list[dict]]:
    players = my_tradeable_players(snapshot, my_team, fc)
    picks = [
        {
            "name": a.label,
            "label": a.label,
            "manager": my_team.get("owner_name") or "You",
            "fc_value": a.fc_value,
            "season": a.season,
            "round": a.round,
            "traded": a.traded,
        }
        for a in picks_for_roster(snapshot, int(my_team["roster_id"]), fc)
    ]
    return players, picks


def _estimate_keeper_round(adp: int | None, teams: int = 12) -> int | None:
    if not adp:
        return None
    return max(1, min(16, (adp - 1) // teams + 1))


def _keeper_round_for_player(name: str, snapshot: dict, my_team: dict) -> int | None:
    draft = snapshot.get("draft") or {}
    rid = my_team.get("roster_id")
    for pick in draft.get("picks") or []:
        if pick.get("roster_id") == rid and pick.get("is_keeper") and pick.get("player_name") == name:
            return int(pick.get("round") or 0) or None
    return None


def recommend_keepers(
    snapshot: dict,
    my_team: dict,
    adp_map: dict,
    fc: FantasyCalcClient,
    config: dict,
    intel=None,
) -> list[dict]:
    """Rank keeper candidates using ADP, FantasyCalc, age, upside, and pick cost."""
    if not league_has_keepers(config, snapshot):
        return []

    max_keepers = int(
        config.get("max_keepers")
        or (snapshot.get("league") or {}).get("settings", {}).get("max_keepers")
        or 0
    )
    if max_keepers <= 0:
        return []

    current = {n.lower() for n in keeper_names_from_draft(snapshot, my_team)}
    teams = int((snapshot.get("draft") or {}).get("teams") or len(snapshot.get("teams") or []) or 12)
    season = _draft_season(snapshot)
    rows: list[dict] = []

    for p in my_team.get("players") or []:
        pos = p.get("position") or ""
        if pos not in CORE_POSITIONS:
            continue
        name = p.get("name") or ""
        adp_entry = lookup_adp(name, adp_map)
        adp = adp_entry.adp if adp_entry else None
        fc_v = fc.get(name, p.get("id"))
        fc_val = fc_v.value if fc_v else 0
        age = p.get("age")

        keeper_round = _keeper_round_for_player(name, snapshot, my_team)
        est_round = keeper_round or _estimate_keeper_round(adp, teams)
        pick_fc = fc.pick_value(season, est_round) if est_round else None
        pick_cost = pick_fc.value if pick_fc else 0

        score = 0.0
        reasons: list[str] = []

        if adp:
            score += max(0, 120 - adp * 0.8)
            if adp <= 36:
                reasons.append(f"Elite ADP ({adp})")
            elif adp <= 72:
                reasons.append(f"Strong ADP ({adp})")
        if fc_val:
            score += fc_val / 80
            reasons.append(f"FC {fc_val:,}")
        if pick_cost and fc_val:
            surplus = fc_val - pick_cost
            score += surplus / 60
            if surplus > 500:
                reasons.append(f"Big value vs R{est_round} pick (+{surplus:,})")
            elif surplus < -200:
                reasons.append(f"Below R{est_round} pick value ({surplus:+,})")
        if age:
            if age <= 25:
                score += 12
                reasons.append(f"Age {age}")
            elif age >= 29 and pos == "RB":
                score -= 18
                reasons.append(f"RB age {age}")

        upside = 0.0
        if intel:
            ctx = intel.get(name, pos)
            upside = ctx.upside_score
            if upside >= 40:
                score += upside * 0.25
                reasons.append(f"Upside {upside:.0f}")
            if ctx.injury_penalty >= 20:
                score -= ctx.injury_penalty * 0.4
                reasons.append(f"Injury concern")

        is_current = name.lower() in current
        if is_current:
            score += 5

        rows.append({
            "player": name,
            "position": pos,
            "adp": adp,
            "fc_value": fc_val,
            "age": age,
            "keeper_round": keeper_round or est_round,
            "round_estimated": keeper_round is None,
            "pick_cost_fc": pick_cost,
            "value_surplus": fc_val - pick_cost if pick_cost else None,
            "score": round(score, 1),
            "current_keeper": is_current,
            "reasons": reasons[:4],
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(rows):
        rank = i + 1
        if rank <= max_keepers:
            row["verdict"] = "Lock" if row["score"] >= 50 or row["current_keeper"] else "Keep"
        elif rank <= max_keepers + 2:
            row["verdict"] = "Consider"
        else:
            row["verdict"] = "Drop"
        if row["current_keeper"] and rank > max_keepers:
            row["verdict"] = "Review — below top tier"
        row["rank"] = rank

    return rows


def keeper_rounds_summary(snapshot: dict, my_team: dict, fc: FantasyCalcClient) -> dict:
    """Show which rounds are consumed by keepers vs available to draft/trade."""
    rid = int(my_team["roster_id"])
    keeper_rounds = _keeper_rounds_by_roster(snapshot).get(rid, set())
    tradeable = picks_for_roster(snapshot, rid, fc, tradeable_only=True)
    return {
        "consumed_rounds": sorted(keeper_rounds),
        "tradeable_count": len(tradeable),
        "tradeable_labels": [p.label for p in tradeable],
    }
