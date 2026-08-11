from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Position = Literal["QB", "RB", "WR", "TE", "K", "DEF"]


@dataclass
class Player:
    name: str
    position: Position
    team: str = ""
    age: float | None = None
    sleeper_id: str | None = None
    adp: int | None = None
    adp_position_rank: str | None = None
    dynasty_value: float | None = None
    injury_status: str | None = None
    news_snippet: str | None = None


@dataclass
class RosterPlayer(Player):
    owner_id: str = ""
    owner_name: str = ""
    team_name: str = ""
    is_starter: bool = False
    is_taxi: bool = False
    is_ir: bool = False


@dataclass
class TeamNeeds:
    owner_id: str
    owner_name: str
    team_name: str
    position_counts: dict[str, int] = field(default_factory=dict)
    starter_gaps: dict[str, int] = field(default_factory=dict)
    surplus: dict[str, int] = field(default_factory=dict)
    desperate_for: list[str] = field(default_factory=list)
    overloaded_at: list[str] = field(default_factory=list)
    roster: list[RosterPlayer] = field(default_factory=list)


@dataclass
class TradeMatch:
    target_manager: str
    target_team: str
    you_give: list[str]
    you_get: list[str]
    rationale: str
    leverage_score: float


@dataclass
class SellCandidate:
    player: str
    position: str
    adp: int | None
    reason: str
    urgency: Literal["high", "medium", "low"]


@dataclass
class WaiverTarget:
    player: str
    position: str
    adp: int | None
    owned_pct: float | None
    reason: str
    priority: int


@dataclass
class DraftBoardEntry:
    player: str
    position: str
    adp: int | None
    team: str
    fit_score: float
    fit_reason: str
    news_flag: str
    tier: int
    upside_score: float = 0.0
    upside_note: str = ""


@dataclass
class UpsideTarget:
    player: str
    position: str
    adp: int | None
    upside_score: float
    insight: str
    team: str = ""


@dataclass
class PickRecommendation:
    player: str
    position: str
    adp: int | None
    fit_score: float
    reason: str
    target_pick: int | None = None
    upside_score: float = 0.0


@dataclass
class ManagerDraftProfile:
    manager: str
    team: str
    draft_slot: int | None
    rb_count: int
    wr_count: int
    qb_count: int
    te_count: int
    tendency: str
    draft_prediction: str
    keeper_positions: list[str]


@dataclass
class KeeperPlan:
    keepers: list[dict]
    max_keepers: int
    post_keeper_counts: dict[str, int]
    remaining_needs: list[str]
    draft_priorities: list[str]
