from __future__ import annotations

from src.adp import lookup_adp
from src.models import Player, RosterPlayer, SellCandidate, TeamNeeds, TradeMatch, WaiverTarget

CORE_POSITIONS = ["QB", "RB", "WR", "TE"]
FLEX_POSITIONS = ["RB", "WR", "TE"]


def _starter_requirements(config: dict) -> dict[str, int]:
    starters = config.get("starters", {})
    reqs = {pos: starters.get(pos, 0) for pos in CORE_POSITIONS}
    flex = starters.get("FLEX", 0)
    sf = starters.get("SUPERFLEX", 0)
    reqs["FLEX"] = flex
    reqs["SUPERFLEX"] = sf
    return reqs


def analyze_team_needs(team: dict, config: dict) -> TeamNeeds:
    reqs = _starter_requirements(config)
    counts: dict[str, int] = {p: 0 for p in CORE_POSITIONS}
    roster: list[RosterPlayer] = []

    for p in team["players"]:
        pos = p["position"]
        if pos not in CORE_POSITIONS:
            continue
        counts[pos] = counts.get(pos, 0) + 1
        roster.append(
            RosterPlayer(
                name=p["name"],
                position=pos,
                team=p.get("team", ""),
                age=p.get("age"),
                owner_id=team.get("owner_id", ""),
                owner_name=team.get("owner_name", ""),
                team_name=team.get("team_name", ""),
                is_starter=p.get("is_starter", False),
                is_taxi=p.get("is_taxi", False),
                is_ir=p.get("is_ir", False),
                injury_status=p.get("injury_status"),
            )
        )

    starter_gaps: dict[str, int] = {}
    for pos in CORE_POSITIONS:
        gap = reqs.get(pos, 0) - counts.get(pos, 0)
        if gap > 0:
            starter_gaps[pos] = gap

    flex_pool = sum(counts.get(p, 0) for p in FLEX_POSITIONS)
    flex_needed = reqs.get("FLEX", 0)
    if flex_pool < sum(reqs.get(p, 0) for p in CORE_POSITIONS) + flex_needed:
        starter_gaps["FLEX"] = starter_gaps.get("FLEX", 0) + 1

    if reqs.get("SUPERFLEX", 0) > 0 and counts.get("QB", 0) < reqs["QB"] + reqs["SUPERFLEX"]:
        starter_gaps["QB"] = starter_gaps.get("QB", 0) + 1

    bench = config.get("bench_spots", 10)
    ideal_depth = {p: reqs.get(p, 0) + 2 for p in CORE_POSITIONS}
    surplus: dict[str, int] = {}
    for pos in CORE_POSITIONS:
        extra = counts.get(pos, 0) - ideal_depth.get(pos, 2)
        if extra > 1:
            surplus[pos] = extra

    desperate = [p for p, g in starter_gaps.items() if g >= 2]
    if not desperate:
        desperate = [p for p, g in starter_gaps.items() if g >= 1]

    overloaded = [p for p, s in surplus.items() if s >= 2]

    return TeamNeeds(
        owner_id=team.get("owner_id", ""),
        owner_name=team.get("owner_name", ""),
        team_name=team.get("team_name", ""),
        position_counts=counts,
        starter_gaps=starter_gaps,
        surplus=surplus,
        desperate_for=desperate,
        overloaded_at=overloaded,
        roster=roster,
    )


def grade_roster(
    team: dict,
    adp_map: dict[str, Player],
    news_client=None,
) -> list[dict]:
    grades = []
    news = news_client.get_news(limit=40) if news_client else []
    injuries = news_client.get_injuries() if news_client else []

    for p in team["players"]:
        pos = p["position"]
        if pos not in CORE_POSITIONS:
            continue

        adp_entry = lookup_adp(p["name"], adp_map)
        adp = adp_entry.adp if adp_entry else None

        age = p.get("age")
        grade = "C"
        notes: list[str] = []

        if adp:
            if adp <= 36:
                grade = "A"
                notes.append(f"Top-tier asset (ADP {adp})")
            elif adp <= 72:
                grade = "B+"
                notes.append(f"Strong starter (ADP {adp})")
            elif adp <= 120:
                grade = "B"
                notes.append(f"Solid contributor (ADP {adp})")
            elif adp <= 180:
                grade = "C+"
                notes.append(f"Depth piece (ADP {adp})")
            else:
                grade = "D"
                notes.append(f"Replaceable (ADP {adp})")
        else:
            notes.append("Not in top 300 ADP")

        if age:
            if pos == "RB" and age >= 28:
                grade = _downgrade(grade)
                notes.append(f"RB age cliff concern ({age})")
            elif pos == "WR" and age >= 30:
                grade = _downgrade(grade)
                notes.append(f"WR aging ({age})")
            elif age <= 24:
                notes.append(f"Youth upside ({age})")

        if news_client:
            inj = news_client.injury_for_player(p["name"], injuries)
            if inj:
                grade = _downgrade(grade)
                notes.append(f"Injury: {inj['status']} — {inj.get('detail', '')}")
            headline = news_client.news_for_player(p["name"], news)
            if headline:
                notes.append(f"News: {headline}")

        grades.append({
            "name": p["name"],
            "position": pos,
            "team": p.get("team", ""),
            "age": age,
            "adp": adp,
            "grade": grade,
            "notes": notes,
            "is_starter": p.get("is_starter", False),
        })

    grades.sort(key=lambda g: g["adp"] or 999)
    return grades


def _downgrade(grade: str) -> str:
    ladder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
    try:
        idx = ladder.index(grade)
        return ladder[min(idx + 1, len(ladder) - 1)]
    except ValueError:
        return "C"


def find_sell_candidates(
    my_team: dict,
    adp_map: dict[str, Player],
    config: dict,
) -> list[SellCandidate]:
    candidates: list[SellCandidate] = []
    contending = config.get("notes", {}).get("contending", True)

    for p in my_team["players"]:
        pos = p["position"]
        if pos not in CORE_POSITIONS:
            continue

        adp_entry = lookup_adp(p["name"], adp_map)
        adp = adp_entry.adp if adp_entry else None
        age = p.get("age")
        reasons: list[str] = []
        urgency: str = "low"

        if pos == "RB" and age and age >= 29:
            reasons.append(f"RB age {age} — sell before value cliff")
            urgency = "high"
        elif pos == "RB" and age and age >= 27 and adp and adp <= 60:
            reasons.append(f"Peak-value RB ({age}) — sell high in dynasty")
            urgency = "medium"

        if pos == "WR" and age and age >= 31:
            reasons.append(f"Aging WR ({age})")
            urgency = "high" if urgency != "high" else urgency

        if adp and adp <= 50 and contending is False:
            reasons.append("Rebuild mode — convert win-now asset to picks/youth")

        if p.get("injury_status") in ("Out", "IR", "PUP", "Doubtful"):
            reasons.append(f"Injury status: {p['injury_status']}")
            urgency = "high"

        if reasons:
            candidates.append(
                SellCandidate(
                    player=p["name"],
                    position=pos,
                    adp=adp,
                    reason="; ".join(reasons),
                    urgency=urgency,  # type: ignore[arg-type]
                )
            )

    order = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda c: (order[c.urgency], c.adp or 999))
    return candidates


def find_trade_matches(
    my_needs: TeamNeeds,
    all_needs: list[TeamNeeds],
    adp_map: dict[str, Player],
    my_team: dict,
) -> list[TradeMatch]:
    matches: list[TradeMatch] = []
    my_surplus = my_needs.surplus
    my_gaps = my_needs.starter_gaps

    my_player_names = {p["name"] for p in my_team["players"]}

    for other in all_needs:
        if other.owner_id == my_needs.owner_id:
            continue

        # They need what I have surplus
        for pos in my_surplus:
            if pos not in other.desperate_for and pos not in other.starter_gaps:
                continue

            my_tradeable = [
                p for p in my_needs.roster
                if p.position == pos and not p.is_starter and p.name in my_player_names
            ]
            my_tradeable.sort(
                key=lambda p: lookup_adp(p.name, adp_map).adp if lookup_adp(p.name, adp_map) else 999,
                reverse=True,
            )

            for gap_pos in my_gaps:
                if gap_pos == "FLEX":
                    target_positions = FLEX_POSITIONS
                else:
                    target_positions = [gap_pos]

                their_tradeable = [
                    p for p in other.roster
                    if p.position in target_positions
                ]
                their_tradeable.sort(
                    key=lambda p: lookup_adp(p.name, adp_map).adp if lookup_adp(p.name, adp_map) else 999,
                )

                if not my_tradeable or not their_tradeable:
                    continue

                give = my_tradeable[0]
                get = their_tradeable[0]
                give_adp = lookup_adp(give.name, adp_map)
                get_adp = lookup_adp(get.name, adp_map)

                leverage = 0.0
                if pos in other.desperate_for:
                    leverage += 2.0
                if gap_pos in my_needs.desperate_for:
                    leverage += 1.5
                if other.surplus.get(gap_pos, 0) >= 2:
                    leverage -= 0.5

                rationale = (
                    f"{other.owner_name} is desperate at {pos} "
                    f"({other.position_counts.get(pos, 0)} on roster) and overloaded elsewhere. "
                    f"You need {gap_pos}. "
                    f"They likely value {give.name} higher than market because it fills a starting hole."
                )

                matches.append(
                    TradeMatch(
                        target_manager=other.owner_name,
                        target_team=other.team_name,
                        you_give=[give.name],
                        you_get=[get.name],
                        rationale=rationale,
                        leverage_score=leverage,
                    )
                )

    matches.sort(key=lambda m: m.leverage_score, reverse=True)
    seen: set[tuple[str, str, str]] = set()
    unique: list[TradeMatch] = []
    for m in matches:
        key = (m.target_manager, m.you_give[0], m.you_get[0])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique[:15]


def find_waiver_targets(
    league_snapshot: dict,
    my_team: dict,
    adp_map: dict[str, Player],
    trending: dict,
    my_needs: TeamNeeds,
) -> list[WaiverTarget]:
    owned_ids = set()
    for team in league_snapshot["teams"]:
        for p in team["players"]:
            owned_ids.add(p.get("id", p["name"]))

    gap_positions = list(my_needs.starter_gaps.keys()) or my_needs.desperate_for
    if not gap_positions:
        gap_positions = ["RB", "WR"]

    targets: list[WaiverTarget] = []
    adds = trending.get("adds", [])

    for entry in adds:
        player_id = str(entry.get("player_id", ""))
        count = entry.get("count", 0)
        # We don't have full player pool in trending — use count as signal
        targets.append({
            "player_id": player_id,
            "add_count": count,
        })

    # Best available = high ADP players not on any roster
    available: list[WaiverTarget] = []
    team_names = {p["name"].lower() for p in my_team["players"]}
    all_owned = set()
    for team in league_snapshot["teams"]:
        for p in team["players"]:
            all_owned.add(p["name"].lower())

    for name, adp_player in adp_map.items():
        if name in all_owned:
            continue
        if adp_player.position not in gap_positions and adp_player.position not in CORE_POSITIONS:
            continue
        if adp_player.adp and adp_player.adp > 200:
            continue

        priority = 1 if adp_player.position in gap_positions else 2
        reason = f"Top-{adp_player.adp} ADP {adp_player.position} available — fills {', '.join(gap_positions)} need"

        available.append(
            WaiverTarget(
                player=adp_player.name,
                position=adp_player.position,
                adp=adp_player.adp,
                owned_pct=None,
                reason=reason,
                priority=priority,
            )
        )

    available.sort(key=lambda w: (w.priority, w.adp or 999))
    return available[:20]
