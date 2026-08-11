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
    you_give_value: float = 0.0
    you_get_value: float = 0.0
    value_delta: float = 0.0
    confidence: str = ""
    offer_picks: list[str] = field(default_factory=list)
    receive_picks: list[str] = field(default_factory=list)


@dataclass
class PlayerValue:
    name: str
    position: str
    dynasty_value: float
    adp: int | None
    grade: str
    upside_score: float
    vor: float
    age: float | None
    trend: str
    injury: str
    summary: str
    tradeable: bool = True
    fc_value: int | None = None
    fc_trend: str = ""
    fp_summary: str = ""


@dataclass
class PositionUnit:
    position: str
    count: int
    quality: str
    starter_value: float
    depth_value: float
    total_value: float
    top_player: str
    top_value: float
    weakest: str
    avg_age: float
    need_score: float
    surplus_score: float
    notes: str


@dataclass
class ManagerTendency:
    manager: str
    team: str
    owner_id: str
    trade_count: int
    picks_traded: int
    avg_trade_age: float
    draft_rb_early_pct: float
    draft_wr_early_pct: float
    draft_youth_pct: float
    archetype: str
    likes: list[str]
    notes: str


@dataclass
class TeamTradeProfile:
    manager: str
    team: str
    owner_id: str
    record: str
    win_mode: str
    units: list[PositionUnit]
    desperate_for: list[str]
    surplus_at: list[str]
    tradeable_assets: list[PlayerValue]
    targets_on_roster: list[PlayerValue]
    draft_picks: list[str]
    pick_values: list[tuple[str, float]]
    tendency: ManagerTendency
    best_match_score: float = 0.0


@dataclass
class TradeProposal:
    target_manager: str
    target_team: str
    you_send_players: list[str]
    you_send_picks: list[str]
    you_receive_players: list[str]
    you_receive_picks: list[str]
    send_value: float
    receive_value: float
    value_delta: float
    fairness: str
    leverage_score: float
    confidence: str
    why_they_accept: str
    why_you_win: str
    risk_notes: str
    fc_send_total: int = 0
    fc_receive_total: int = 0
    fc_delta: int = 0
    fc_verdict: str = ""
    fp_insight: str = ""


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
