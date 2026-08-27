"""League analytics — trade wire, portfolio, screener, leaderboards."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.adp import lookup_adp
from src.fantasycalc import FantasyCalcClient
from src.rankings import RankRow


@dataclass
class TradeRecord:
    week: int
    season: str
    managers: list[str]
    side_a: list[str]
    side_b: list[str]
    picks_moved: list[str]
    transaction_id: str = ""


@dataclass
class PortfolioTeam:
    manager: str
    team_name: str
    record: str
    total_value: int
    qb_value: int
    rb_value: int
    wr_value: int
    te_value: int
    pick_value: int
    avg_age: float
    contending: bool


def _player_name_map(snapshot: dict, intel) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            pid = str(p.get("id") or "")
            if pid:
                out[pid] = {**p, "manager": team.get("owner_name")}
    if intel and hasattr(intel, "sleeper_players"):
        for pid, sp in intel.sleeper_players.items():
            if pid not in out and sp.get("full_name"):
                out[pid] = {
                    "id": pid,
                    "name": sp.get("full_name"),
                    "position": sp.get("position"),
                    "team": sp.get("team"),
                    "age": sp.get("age"),
                }
    return out


def parse_trade_records(snapshot: dict, intel) -> list[TradeRecord]:
    history = snapshot.get("trade_history") or {}
    trades = history.get("trades") or []
    chain = {lg["league_id"]: lg.get("season", "") for lg in history.get("league_chain") or []}
    roster_to_owner: dict[int, str] = {}
    owner_names: dict[str, str] = {}
    for team in snapshot.get("teams") or []:
        roster_to_owner[team["roster_id"]] = team.get("owner_id", "")
        owner_names[team.get("owner_id", "")] = team.get("owner_name", "Unknown")

    players = _player_name_map(snapshot, intel)
    records: list[TradeRecord] = []

    for txn in trades:
        rids = txn.get("roster_ids") or []
        if len(rids) < 2:
            continue
        adds = txn.get("adds") or {}
        drops = txn.get("drops") or {}
        sides: dict[int, list[str]] = {rid: [] for rid in rids[:2]}

        for pid, rid in adds.items():
            if rid in sides:
                p = players.get(str(pid), {})
                name = p.get("name") or p.get("full_name") or str(pid)
                pos = p.get("position", "")
                sides[rid].append(f"{name} ({pos})" if pos else name)

        pick_labels = []
        for pk in txn.get("draft_picks") or []:
            season = pk.get("season", "")
            rnd = pk.get("round", "")
            pick_labels.append(f"{season} R{rnd}")

        mgrs = [owner_names.get(roster_to_owner.get(rid, ""), f"Roster {rid}") for rid in rids[:2]]
        side_lists = [sides.get(rids[0], []), sides.get(rids[1], []) if len(rids) > 1 else []]
        lid = txn.get("source_league_id") or snapshot.get("league", {}).get("league_id", "")
        records.append(
            TradeRecord(
                week=int(txn.get("week") or 0),
                season=str(chain.get(lid, snapshot.get("league", {}).get("season", ""))),
                managers=mgrs,
                side_a=side_lists[0],
                side_b=side_lists[1],
                picks_moved=pick_labels,
                transaction_id=str(txn.get("transaction_id") or ""),
            )
        )
    records.sort(key=lambda r: (r.season, r.week), reverse=True)
    return records


def portfolio_managers(snapshot: dict, fc: FantasyCalcClient) -> list[PortfolioTeam]:
    teams: list[PortfolioTeam] = []
    pos_keys = {"QB": "qb_value", "RB": "rb_value", "WR": "wr_value", "TE": "te_value"}
    for team in snapshot.get("teams") or []:
        totals = {"qb_value": 0, "rb_value": 0, "wr_value": 0, "te_value": 0, "pick_value": 0}
        ages: list[float] = []
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in pos_keys:
                continue
            fc_v = fc.get(p.get("name", ""), p.get("id"))
            val = fc_v.value if fc_v else 0
            totals[pos_keys[pos]] += val
            if p.get("age"):
                ages.append(float(p["age"]))
        for pk in team.get("draft_picks") or []:
            fc_v = fc.pick_value(str(pk.get("season", "")), int(pk.get("round") or 0))
            totals["pick_value"] += fc_v.value if fc_v else 0

        total = sum(totals.values())
        wins = team.get("wins", 0)
        losses = team.get("losses", 0)
        teams.append(
            PortfolioTeam(
                manager=team.get("owner_name") or "Unknown",
                team_name=team.get("team_name") or "",
                record=f"{wins}-{losses}",
                total_value=total,
                qb_value=totals["qb_value"],
                rb_value=totals["rb_value"],
                wr_value=totals["wr_value"],
                te_value=totals["te_value"],
                pick_value=totals["pick_value"],
                avg_age=round(sum(ages) / len(ages), 1) if ages else 0,
                contending=wins >= losses,
            )
        )
    teams.sort(key=lambda t: t.total_value, reverse=True)
    return teams


def trade_pulse(snapshot: dict, fc: FantasyCalcClient, limit: int = 25) -> list[dict]:
    """Biggest 30-day FC movers on league rosters."""
    movers: list[dict] = []
    seen: set[str] = set()
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in {"QB", "RB", "WR", "TE"}:
                continue
            name = p.get("name") or ""
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            fc_v = fc.get(name, p.get("id"))
            if not fc_v or abs(fc_v.trend_30d) < 30:
                continue
            movers.append({
                "player": name,
                "position": pos,
                "manager": team.get("owner_name"),
                "fc_value": fc_v.value,
                "trend": fc_v.trend_30d,
                "trend_label": fc_v.trend_label,
                "direction": "Riser" if fc_v.trend_30d > 0 else "Faller",
            })
    movers.sort(key=lambda x: abs(x["trend"]), reverse=True)
    return movers[:limit]


def contract_room(snapshot: dict, fc: FantasyCalcClient, manager: str | None = None) -> list[dict]:
    """Dynasty 'contract' view — value vs age on a roster."""
    rows: list[dict] = []
    for team in snapshot.get("teams") or []:
        mgr = team.get("owner_name") or ""
        if manager and mgr != manager:
            continue
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in {"QB", "RB", "WR", "TE"}:
                continue
            fc_v = fc.get(p.get("name", ""), p.get("id"))
            age = p.get("age")
            val = fc_v.value if fc_v else 0
            value_per_year = round(val / max(age or 25, 22), 0) if val else 0
            tag = "Core" if val >= 5000 else ("Trade chip" if val >= 3000 else "Depth")
            if age and age >= 29 and pos == "RB":
                tag = "Aging RB"
            rows.append({
                "manager": mgr,
                "player": p.get("name"),
                "position": pos,
                "age": age or "—",
                "fc_value": val,
                "value_per_year": value_per_year,
                "tag": tag,
                "trend": fc_v.trend_30d if fc_v else 0,
            })
    rows.sort(key=lambda x: x["fc_value"], reverse=True)
    return rows


def what_winning_costs(snapshot: dict, fc: FantasyCalcClient, records: list[TradeRecord]) -> list[dict]:
    """Avg FC value acquired by top-record teams in trade history."""
    teams = snapshot.get("teams") or []
    sorted_teams = sorted(teams, key=lambda t: t.get("wins", 0), reverse=True)
    top_mgrs = {t.get("owner_name") for t in sorted_teams[:4]}
    stats: dict[str, dict] = {}

    roster_to_mgr: dict[int, str] = {}
    for t in teams:
        roster_to_mgr[t["roster_id"]] = t.get("owner_name", "")

    history = snapshot.get("trade_history") or {}
    for txn in history.get("trades") or []:
        adds = txn.get("adds") or {}
        for pid, rid in adds.items():
            mgr = roster_to_mgr.get(rid, "")
            if mgr not in top_mgrs:
                continue
            st = stats.setdefault(mgr, {"count": 0, "total": 0, "players": []})
            # resolve name from teams
            name = str(pid)
            for team in teams:
                for p in team.get("players") or []:
                    if str(p.get("id")) == str(pid):
                        name = p.get("name", name)
                        break
            fc_v = fc.get(name)
            val = fc_v.value if fc_v else 0
            st["count"] += 1
            st["total"] += val
            st["players"].append(name)

    rows: list[dict] = []
    for mgr in top_mgrs:
        st = stats.get(mgr, {"count": 0, "total": 0, "players": []})
        avg = round(st["total"] / st["count"]) if st["count"] else 0
        rows.append({
            "manager": mgr,
            "trades": st["count"],
            "avg_fc_acquired": avg,
            "total_fc_acquired": st["total"],
            "sample": ", ".join(st["players"][:4]) or "—",
        })
    rows.sort(key=lambda x: x["avg_fc_acquired"], reverse=True)
    return rows


def screener_pool(snapshot: dict, fc: FantasyCalcClient, adp_map: dict) -> list[dict]:
    """All NFL-relevant players from Sleeper + league with filter fields."""
    pool: list[dict] = []
    rostered: dict[str, str] = {}
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            if p.get("name"):
                rostered[p["name"].lower()] = team.get("owner_name", "")

    trending = snapshot.get("trending") or {}
    add_counts = {str(x.get("player_id")): x.get("count", 0) for x in trending.get("adds") or []}

    seen: set[str] = set()
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            name = p.get("name") or ""
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            fc_v = fc.get(name, p.get("id"))
            pool.append(_screener_row(p, fc_v, adp_map, rostered, add_counts))

    # Free agents from trending adds not on rosters
    intel_players = snapshot.get("_sleeper_players")
    if not intel_players:
        return sorted(pool, key=lambda x: x["fc_value"], reverse=True)

    return sorted(pool, key=lambda x: x["fc_value"], reverse=True)


def _screener_row(p, fc_v, adp_map, rostered, add_counts) -> dict:
    name = p.get("name") or ""
    adp_entry = lookup_adp(name, adp_map)
    adp = adp_entry.adp if adp_entry else None
    return {
        "player": name,
        "position": p.get("position"),
        "team": p.get("team"),
        "age": p.get("age"),
        "fc_value": fc_v.value if fc_v else 0,
        "fc_rank": fc_v.overall_rank if fc_v else None,
        "trend": fc_v.trend_30d if fc_v else 0,
        "adp": adp,
        "owner": rostered.get(name.lower(), "FA"),
        "trending_adds": add_counts.get(str(p.get("id")), 0),
    }


def scatter_players(snapshot: dict, fc: FantasyCalcClient, adp_map: dict) -> list[dict]:
    points: list[dict] = []
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in {"QB", "RB", "WR", "TE"}:
                continue
            name = p.get("name") or ""
            fc_v = fc.get(name, p.get("id"))
            adp_entry = lookup_adp(name, adp_map)
            adp = adp_entry.adp if adp_entry else None
            if not fc_v or not adp:
                continue
            points.append({
                "player": name,
                "position": pos,
                "manager": team.get("owner_name"),
                "x_adp": float(adp),
                "y_value": fc_v.value,
                "age": p.get("age"),
            })
    return points


def aging_curve(snapshot: dict, fc: FantasyCalcClient, position: str = "RB") -> list[dict]:
    buckets: dict[int, list[int]] = {}
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            if p.get("position") != position:
                continue
            age = p.get("age")
            if not age:
                continue
            fc_v = fc.get(p.get("name", ""), p.get("id"))
            buckets.setdefault(int(age), []).append(fc_v.value if fc_v else 0)

    rows: list[dict] = []
    for age in sorted(buckets):
        vals = buckets[age]
        rows.append({
            "age": age,
            "avg_value": round(sum(vals) / len(vals)),
            "count": len(vals),
            "max_value": max(vals),
        })
    return rows


def game_pulse(snapshot: dict) -> dict:
    trending = snapshot.get("trending") or {}
    adds = trending.get("adds") or []
    drops = trending.get("drops") or []
    players = snapshot.get("_sleeper_players") or {}

    def enrich(items: list) -> list[dict]:
        out: list[dict] = []
        for item in items[:20]:
            pid = str(item.get("player_id", ""))
            sp = players.get(pid, {})
            out.append({
                "player": sp.get("full_name") or pid,
                "position": sp.get("position", ""),
                "team": sp.get("team", ""),
                "count": item.get("count", 0),
            })
        return out

    return {"adds": enrich(adds), "drops": enrich(drops)}


def leaderboards(snapshot: dict, fc: FantasyCalcClient) -> dict[str, list[dict]]:
    by_pos: dict[str, list[dict]] = {"QB": [], "RB": [], "WR": [], "TE": []}
    for team in snapshot.get("teams") or []:
        for p in team.get("players") or []:
            pos = p.get("position") or ""
            if pos not in by_pos:
                continue
            fc_v = fc.get(p.get("name", ""), p.get("id"))
            by_pos[pos].append({
                "player": p.get("name"),
                "manager": team.get("owner_name"),
                "fc_value": fc_v.value if fc_v else 0,
                "age": p.get("age"),
            })
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: x["fc_value"], reverse=True)
        by_pos[pos] = by_pos[pos][:15]
    return by_pos


def season_prep(snapshot: dict, draft: dict | None, config: dict) -> dict:
    league = snapshot.get("league") or {}
    settings = league.get("settings") or {}
    return {
        "season": league.get("season", "2026"),
        "teams": settings.get("num_teams") or len(snapshot.get("teams") or []),
        "draft_status": (draft or {}).get("status", "pre_draft"),
        "my_slot": (draft or {}).get("my_slot"),
        "format": config.get("format", "keeper"),
        "scoring": config.get("scoring", "ppr"),
        "max_keepers": settings.get("max_keepers") or config.get("max_keepers", 0),
    }


def start_sit_compare(
    analyst_grades: list[dict],
    fc: FantasyCalcClient,
    player_a: str,
    player_b: str,
) -> dict:
    grade_map = {g["name"]: g for g in analyst_grades}
    ga = grade_map.get(player_a, {})
    gb = grade_map.get(player_b, {})
    fc_a = fc.get(player_a)
    fc_b = fc.get(player_b)
    score_a = (fc_a.value if fc_a else 0) + _grade_bonus(ga.get("grade", "C"))
    score_b = (fc_b.value if fc_b else 0) + _grade_bonus(gb.get("grade", "C"))
    winner = player_a if score_a >= score_b else player_b
    return {
        "a": {"name": player_a, "grade": ga.get("grade"), "fc": fc_a.value if fc_a else 0, "notes": ga.get("notes", [])},
        "b": {"name": player_b, "grade": gb.get("grade"), "fc": fc_b.value if fc_b else 0, "notes": gb.get("notes", [])},
        "winner": winner,
        "margin": abs(score_a - score_b),
    }


def _grade_bonus(grade: str) -> int:
    return {"A": 400, "B": 200, "C": 0, "D": -200, "F": -400}.get(grade, 0)
