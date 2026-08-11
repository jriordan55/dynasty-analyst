from __future__ import annotations

import json
import re
from pathlib import Path

from src.models import Player, Position

POSITION_MAP = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "K": "K",
    "DEF": "DEF",
}


def _normalize_position(raw: str) -> Position | None:
    prefix = raw.split("-")[0].strip().upper()
    return POSITION_MAP.get(prefix)  # type: ignore[return-value]


def parse_adp_markdown(text: str) -> list[Player]:
    """Parse 4for4 ADP markdown table into Player objects."""
    players: list[Player] = []
    row_pattern = re.compile(
        r"^\|\s*(\d+)\s*\|\s*([A-Z]+-\d+)\s*\|\s*\[([^\]]+)\]",
        re.MULTILINE,
    )
    team_pattern = re.compile(r"\|\s*([A-Z]{2,3}|)\s*\|")

    for match in row_pattern.finditer(text):
        adp = int(match.group(1))
        pos_rank = match.group(2)
        name = match.group(3).strip()
        position = _normalize_position(pos_rank)
        if not position:
            continue

        # Extract team from the line after the player name link
        line_start = match.start()
        line_end = text.find("\n", line_start)
        line = text[line_start:line_end] if line_end != -1 else text[line_start:]
        parts = [p.strip() for p in line.split("|")]
        team = parts[4] if len(parts) > 4 and parts[4] not in ("-", "") else ""

        players.append(
            Player(
                name=name,
                position=position,
                team=team,
                adp=adp,
                adp_position_rank=pos_rank,
            )
        )

    return players


def load_adp(path: Path | None = None) -> dict[str, Player]:
    """Load ADP data keyed by lowercase player name."""
    if path is None:
        path = Path(__file__).resolve().parents[1] / "data" / "adp.json"

    if path.suffix == ".json" and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            entry["name"].lower(): Player(**entry)
            for entry in raw
        }

    if path.suffix == ".md" or not path.exists():
        md_path = path if path.exists() else Path(__file__).resolve().parents[2] / "uploads" / "adp-0.md"
        alt = Path(__file__).resolve().parents[1] / "data" / "adp-source.md"
        for candidate in (md_path, alt):
            if candidate.exists():
                players = parse_adp_markdown(candidate.read_text(encoding="utf-8"))
                return {p.name.lower(): p for p in players}

    raise FileNotFoundError(f"No ADP data found at {path}")


def save_adp_json(players: list[Player], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "name": p.name,
            "position": p.position,
            "team": p.team,
            "adp": p.adp,
            "adp_position_rank": p.adp_position_rank,
        }
        for p in players
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def lookup_adp(name: str, adp_map: dict[str, Player]) -> Player | None:
    key = name.lower()
    if key in adp_map:
        return adp_map[key]

    # Fuzzy: strip suffixes like Jr., III
    cleaned = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", key, flags=re.I)
    for k, v in adp_map.items():
        k_clean = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", k, flags=re.I)
        if cleaned == k_clean or cleaned in k or k in cleaned:
            return v
    return None
