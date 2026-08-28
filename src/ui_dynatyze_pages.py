"""Dynatyze-style HTML renderers for league hub pages."""

from __future__ import annotations

import html

from src.dynatyze_pages import (
    DepthChartPage,
    InjuryPage,
    MyTeamPage,
    PlayerCard,
    StartSitPage,
    injury_badge,
)
from src.ui_dynatyze import _embed_html

PAGE_CSS = """
body { margin: 0; background: transparent; color: #e5e7eb; font-family: Montserrat, system-ui, sans-serif; }
.dz-page-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.dz-page-title { display: flex; align-items: center; gap: 0.65rem; margin: 0; color: #fff; font-size: 1.35rem; font-weight: 800; }
.dz-page-icon { width: 34px; height: 34px; border-radius: 0.45rem; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.35); display: grid; place-items: center; color: #10b981; font-size: 0.9rem; }
.dz-badge { background: #111827; border: 1px solid #374151; color: #9ca3af; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; padding: 0.15rem 0.5rem; border-radius: 999px; text-transform: uppercase; }
.dz-sub { color: #6b7280; font-size: 0.78rem; margin: 0.15rem 0 0 0; }
.dz-toggle { display: inline-flex; background: #111827; border: 1px solid #374151; border-radius: 999px; overflow: hidden; }
.dz-toggle span { padding: 0.35rem 0.75rem; font-size: 0.68rem; font-weight: 700; color: #9ca3af; }
.dz-toggle .on { background: #10b981; color: #000; }
.dz-optimal { color: #d1d5db; font-size: 0.78rem; }
.dz-optimal b { color: #10b981; font-size: 1rem; }
.dz-card { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }
.dz-card.green { border-color: rgba(16,185,129,0.45); }
.dz-card.amber { border: 2px solid #f59e0b; }
.dz-card.red { border: 1px solid rgba(239,68,68,0.55); background: rgba(127,29,29,0.12); }
.dz-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.65rem; }
.dz-card-head h3 { margin: 0; color: #fff; font-size: 0.82rem; font-weight: 700; letter-spacing: 0.04em; }
.dz-count { background: #10b981; color: #000; font-size: 0.62rem; font-weight: 800; padding: 0.1rem 0.4rem; border-radius: 999px; }
.dz-move { display: grid; grid-template-columns: auto 1fr auto; gap: 0.65rem; align-items: center; padding: 0.55rem 0; border-top: 1px solid #1f2937; }
.dz-move:first-of-type { border-top: none; }
.dz-arrow { color: #6b7280; font-size: 0.85rem; }
.dz-move-name { color: #fff; font-weight: 700; font-size: 0.82rem; }
.dz-move-reason { color: #6b7280; font-size: 0.68rem; margin-top: 0.1rem; }
.dz-gain { color: #10b981; font-weight: 800; font-size: 0.78rem; white-space: nowrap; }
.dz-bench-row { display: grid; grid-template-columns: 5rem 1fr; gap: 1rem; align-items: center; }
.dz-bench-num { color: #f59e0b; font-size: 2rem; font-weight: 800; line-height: 1; }
.dz-bench-label { color: #f59e0b; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em; }
.dz-bench-msg { color: #fff; font-size: 0.88rem; font-weight: 700; margin: 0 0 0.25rem 0; }
.dz-bench-sub { color: #9ca3af; font-size: 0.72rem; margin: 0; }
.dz-alert-title { color: #f87171; font-weight: 700; font-size: 0.82rem; margin: 0 0 0.25rem 0; }
.dz-alert-body { color: #fca5a5; font-size: 0.72rem; margin: 0; line-height: 1.4; }
.dz-grid-2 { display: grid; grid-template-columns: 1.4fr 0.6fr; gap: 0.85rem; }
@media (max-width: 900px) { .dz-grid-2 { grid-template-columns: 1fr; } }
.dz-lineup-row { display: grid; grid-template-columns: 2.5rem 1fr auto auto; gap: 0.65rem; align-items: center; padding: 0.65rem 0; border-bottom: 1px solid #1f2937; }
.dz-pos-tag { color: #6b7280; font-size: 0.72rem; font-weight: 700; }
.dz-player-cell { display: flex; align-items: center; gap: 0.55rem; min-width: 0; }
.dz-player-cell img { width: 36px; height: 36px; border-radius: 999px; object-fit: cover; background: #111827; flex-shrink: 0; }
.dz-player-name { color: #fff; font-weight: 700; font-size: 0.82rem; margin: 0; }
.dz-player-meta { color: #6b7280; font-size: 0.65rem; margin: 0.1rem 0 0 0; }
.dz-pos-pill { display: inline-block; background: rgba(16,185,129,0.15); color: #10b981; font-size: 0.58rem; font-weight: 700; padding: 0.08rem 0.35rem; border-radius: 999px; margin-right: 0.25rem; }
.dz-tier { font-size: 0.62rem; font-weight: 700; padding: 0.15rem 0.45rem; border-radius: 999px; white-space: nowrap; }
.dz-tier.green { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.35); }
.dz-tier.amber { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.35); }
.dz-tier.muted { background: #111827; color: #6b7280; border: 1px solid #374151; }
.dz-pts { text-align: right; }
.dz-pts-val { color: #fff; font-weight: 800; font-size: 0.88rem; }
.dz-pts-sub { color: #6b7280; font-size: 0.62rem; }
.dz-conf-bar { width: 64px; height: 5px; background: #1f2937; border-radius: 999px; overflow: hidden; margin-top: 0.2rem; margin-left: auto; }
.dz-conf-fill { height: 100%; background: #10b981; border-radius: 999px; }
.dz-empty { text-align: center; padding: 2.5rem 1rem; color: #6b7280; }
.dz-empty-title { color: #d1d5db; font-weight: 700; margin: 0.5rem 0 0.25rem 0; }
.dz-info { border: 1px solid #374151; background: #0f1115; border-radius: 0.65rem; padding: 0.75rem 0.85rem; color: #9ca3af; font-size: 0.72rem; line-height: 1.45; margin-bottom: 0.75rem; }
.dz-callout { color: #10b981; font-size: 0.78rem; font-weight: 600; margin: 0.5rem 0 0.85rem 0; }
.dz-injury-card { display: grid; grid-template-columns: auto 1fr auto; gap: 0.75rem; align-items: center; border-left: 3px solid #f59e0b; padding: 0.75rem; background: #0f1115; border-radius: 0.65rem; margin-bottom: 0.65rem; }
.dz-injury-card img { width: 48px; height: 48px; border-radius: 999px; object-fit: cover; background: #111827; }
.dz-status { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.12rem 0.4rem; border-radius: 0.35rem; border: 1px solid; margin-left: 0.35rem; }
.dz-status.questionable { color: #fbbf24; border-color: #fbbf24; }
.dz-status.doubtful { color: #f59e0b; border-color: #f59e0b; }
.dz-status.out, .dz-status.ir { color: #f87171; border-color: #f87171; }
.dz-status.probable { color: #10b981; border-color: #10b981; }
.dz-status.pup { color: #a78bfa; border-color: #a78bfa; }
.dz-status.muted { color: #9ca3af; border-color: #374151; }
.dz-legend { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.45rem 1rem; margin-top: 0.85rem; }
.dz-legend-item { display: flex; gap: 0.45rem; align-items: flex-start; font-size: 0.68rem; color: #6b7280; line-height: 1.35; }
.dz-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
.dz-table-wrap { overflow-x: auto; border: 1px solid #1f2937; border-radius: 0.75rem; }
.dz-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.dz-table th { text-align: left; color: #6b7280; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; padding: 0.65rem 0.55rem; border-bottom: 1px solid #1f2937; background: #0a0a0a; white-space: nowrap; }
.dz-table td { padding: 0.55rem; border-bottom: 1px solid #1f2937; vertical-align: top; min-width: 110px; }
.dz-team-cell { min-width: 140px; }
.dz-team-name { color: #fff; font-weight: 700; margin: 0; font-size: 0.78rem; }
.dz-team-mgr { color: #6b7280; font-size: 0.62rem; margin: 0.1rem 0 0 0; }
.dz-pcard { background: #111827; border: 1px solid #374151; border-radius: 0.45rem; padding: 0.35rem 0.45rem; min-width: 100px; }
.dz-pcard.high { border-color: #a855f7; }
.dz-pcard.mid { border-color: #f59e0b; }
.dz-pcard.low { border-color: #10b981; }
.dz-pcard-top { display: flex; align-items: center; gap: 0.35rem; }
.dz-pcard img { width: 22px; height: 22px; border-radius: 999px; object-fit: cover; background: #0a0a0a; }
.dz-pcard-name { color: #fff; font-weight: 700; font-size: 0.68rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 90px; }
.dz-pcard-meta { color: #6b7280; font-size: 0.58rem; margin-top: 0.15rem; }
.dz-dash { color: #374151; text-align: center; }
.dz-room-head { display: flex; align-items: center; justify-content: space-between; border-left: 3px solid var(--room); padding: 0.45rem 0.65rem; margin: 0.85rem 0 0.35rem 0; background: rgba(255,255,255,0.02); border-radius: 0 0.45rem 0.45rem 0; }
.dz-room-title { color: #fff; font-weight: 700; font-size: 0.78rem; margin: 0; }
.dz-room-val { color: #10b981; font-size: 0.72rem; font-weight: 700; }
.dz-timeline { background: #0f1115; border: 1px solid #1f2937; border-radius: 0.75rem; padding: 0.85rem; margin-bottom: 0.85rem; }
.dz-timeline-row { display: grid; grid-template-columns: 7rem 1fr; gap: 0.65rem; align-items: center; margin-bottom: 0.55rem; }
.dz-timeline-label { color: #d1d5db; font-size: 0.68rem; font-weight: 700; }
.dz-timeline-track { position: relative; height: 34px; background: #111827; border-radius: 999px; overflow: hidden; }
.dz-timeline-dot { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 28px; height: 28px; border-radius: 999px; border: 2px solid var(--c); background: #0a0a0a; overflow: hidden; }
.dz-timeline-dot img { width: 100%; height: 100%; object-fit: cover; }
.dz-ledger-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.65rem; flex-wrap: wrap; gap: 0.5rem; }
.dz-live-btn { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.35); color: #10b981; font-size: 0.62rem; font-weight: 700; padding: 0.25rem 0.55rem; border-radius: 999px; }
.dz-filters { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.75rem; }
.dz-filter-grp { display: flex; align-items: center; gap: 0.25rem; flex-wrap: wrap; }
.dz-filter-lbl { color: #6b7280; font-size: 0.58rem; font-weight: 700; letter-spacing: 0.08em; margin-right: 0.25rem; }
.dz-filter { background: #111827; border: 1px solid #374151; color: #9ca3af; font-size: 0.62rem; font-weight: 600; padding: 0.2rem 0.45rem; border-radius: 999px; }
.dz-filter.on { background: rgba(16,185,129,0.15); border-color: #10b981; color: #10b981; }
.dz-row { display: grid; grid-template-columns: 1fr auto auto auto auto; gap: 0.65rem; align-items: center; padding: 0.55rem 0.35rem; border-bottom: 1px solid #1f2937; }
.dz-signal { font-size: 0.58rem; font-weight: 800; padding: 0.15rem 0.4rem; border-radius: 0.35rem; border: 1px solid; }
.dz-signal.BUY { color: #10b981; border-color: #10b981; }
.dz-signal.SELL { color: #f87171; border-color: #f87171; }
.dz-signal.HOLD { color: #9ca3af; border-color: #374151; }
.dz-val-col { text-align: right; color: #10b981; font-weight: 700; font-size: 0.78rem; }
.dz-rank-col { color: #6b7280; font-size: 0.68rem; text-align: center; }
.dz-age-col { color: #10b981; font-size: 0.68rem; font-weight: 700; text-align: right; }
.dz-wire-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem; }
@media (max-width: 800px) { .dz-wire-grid { grid-template-columns: 1fr; } }
.dz-wire-item { display: flex; justify-content: space-between; align-items: center; padding: 0.45rem 0; border-bottom: 1px solid #1f2937; font-size: 0.78rem; }
.dz-wire-name { color: #fff; font-weight: 600; }
.dz-wire-meta { color: #6b7280; font-size: 0.65rem; }
"""


def _img(src: str, alt: str, size: int = 36) -> str:
    if src:
        return f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" onerror="this.style.display=\'none\'">'
    initial = alt[:1] if alt else "?"
    return f'<div style="width:{size}px;height:{size}px;border-radius:999px;background:#111827;display:grid;place-items:center;color:#fff;font-weight:700;font-size:0.72rem;">{html.escape(initial)}</div>'


def _player_row(p: PlayerCard, show_pos: bool = True) -> str:
    tier_cls = p.tier_color if p.tier_color in ("green", "amber") else "muted"
    conf = min(96, max(55, int(p.projection * 4)))
    rank_txt = f"#{p.fc_rank} BOARD" if p.fc_rank else "—"
    return f"""
    <div class="dz-lineup-row">
        <div class="dz-pos-tag">{html.escape(p.position)}</div>
        <div class="dz-player-cell">
            {_img(p.headshot, p.name)}
            <div>
                <p class="dz-player-name"><span class="dz-pos-pill">{html.escape(p.position)}</span>{html.escape(p.name)}</p>
                <p class="dz-player-meta">{html.escape(p.team or "FA")} · proj {p.projection:.1f}</p>
            </div>
        </div>
        <div><span class="dz-tier {tier_cls}">{html.escape(p.tier or "Start")}</span></div>
        <div class="dz-pts">
            <div class="dz-pts-val">{p.projection:.1f} pts</div>
            <div class="dz-pts-sub">{rank_txt}</div>
            <div class="dz-conf-bar"><div class="dz-conf-fill" style="width:{conf}%"></div></div>
        </div>
    </div>
    """


def _pcard_tier(value: int) -> str:
    if value >= 5000:
        return "high"
    if value >= 2500:
        return "mid"
    return "low"


def _depth_cell(card: PlayerCard | None) -> str:
    if not card:
        return '<td class="dz-dash">—</td>'
    tier = _pcard_tier(card.value)
    age = f"{card.age:.1f}y" if card.age else "—"
    return f"""<td><div class="dz-pcard {tier}">
        <div class="dz-pcard-top">{_img(card.headshot, card.name, 22)}<span class="dz-pcard-name">{html.escape(card.name)}</span></div>
        <div class="dz-pcard-meta">{html.escape(card.team or "FA")} · {html.escape(card.value_label)} · {age}</div>
    </div></td>"""


def render_start_sit_page(data: StartSitPage) -> None:
    moves_html = ""
    for m in data.recommended_moves:
        moves_html += f"""
        <div class="dz-move">
            <div class="dz-arrow">{html.escape(m['out_last'])} →</div>
            <div>
                <div class="dz-move-name">{html.escape(m['in_name'])} ({html.escape(m['position'])})</div>
                <div class="dz-move-reason">{html.escape(m['reason'])}</div>
            </div>
            <div class="dz-gain">+{m['gain']:.1f} PTS</div>
        </div>
        """
    if not moves_html:
        moves_html = '<p style="color:#6b7280;font-size:0.72rem;margin:0;">No bench upgrades found — your lineup looks optimal.</p>'

    alerts_html = ""
    for a in data.alerts:
        alerts_html += f'<div class="dz-card red"><p class="dz-alert-title">⚠ {html.escape(a.split("—")[0].strip())}</p><p class="dz-alert-body">{html.escape(a)}</p></div>'

    lineup_html = "".join(_player_row(p) for p in data.lineup)

    body = f"""
    <div class="dz-page-head">
        <div>
            <h1 class="dz-page-title"><span class="dz-page-icon">⚡</span> Start/Sit Optimizer <span class="dz-badge">{html.escape(data.week_label)}</span></h1>
        </div>
        <div class="dz-toggle"><span class="on">Weekly projection</span><span>Dynasty value</span></div>
        <div class="dz-optimal">🏆 Optimal projection <b>{data.optimal_projection:.1f}</b> pts</div>
    </div>
    <div class="dz-card green">
        <div class="dz-card-head"><h3>Recommended moves</h3><span class="dz-count">{len(data.recommended_moves)}</span></div>
        {moves_html}
    </div>
    <div class="dz-card amber">
        <div class="dz-bench-row">
            <div><div class="dz-bench-num">{data.bench_left:.1f}</div><div class="dz-bench-label">PTS ON BENCH</div></div>
            <div>
                <p class="dz-bench-msg">Your team is leaving points on the bench</p>
                <p class="dz-bench-sub">Current <b>{data.current_projection:.1f}</b> → Optimal <b>{data.optimal_projection:.1f}</b> pts</p>
                <div class="dz-conf-bar" style="width:100%;margin-top:0.5rem;height:6px;"><div class="dz-conf-fill" style="width:{min(100, int(data.current_projection / max(data.optimal_projection, 1) * 100))}%;background:#f59e0b"></div></div>
            </div>
        </div>
    </div>
    {alerts_html}
    <div class="dz-grid-2">
        <div class="dz-card">
            <div class="dz-card-head"><h3>Lineup Board</h3><span class="dz-badge">{html.escape(data.week_label)}</span></div>
            <p class="dz-sub">Your optimal starting lineup for this week.</p>
            {lineup_html}
        </div>
        <div class="dz-card">
            <div class="dz-empty">
                <div class="dz-page-icon" style="margin:0 auto;">▦</div>
                <p class="dz-empty-title">Tap a player</p>
                <p>See their matchup, projection, and market value.</p>
            </div>
        </div>
    </div>
    """
    _embed_html(body, css=PAGE_CSS, height=920)


def render_depth_chart_page(data: DepthChartPage) -> None:
    cols = "".join(f"<th>{html.escape(c)}</th>" for c in data.columns)
    rows_html = ""
    for row in data.rows:
        cells = "".join(_depth_cell(row.slots.get(c)) for c in data.columns)
        rows_html += f"""<tr>
            <td class="dz-team-cell"><p class="dz-team-name">{html.escape(row.team_name)}</p><p class="dz-team-mgr">{html.escape(row.manager)}</p></td>
            {cells}
        </tr>"""
    body = f"""
    <div class="dz-page-head">
        <div>
            <h1 class="dz-page-title"><span class="dz-page-icon">▤</span> Depth Chart</h1>
            <p class="dz-sub">League-wide roster depth by position</p>
        </div>
    </div>
    <div class="dz-toolbar">
        <span style="color:#d1d5db;font-size:0.78rem;font-weight:600;">League Depth Chart ({data.teams} teams)</span>
        <div class="dz-toggle"><span class="on">By Fantasy Team</span><span>By NFL Team</span></div>
    </div>
    <div class="dz-table-wrap"><table class="dz-table"><thead><tr><th>Team</th>{cols}</tr></thead><tbody>{rows_html}</tbody></table></div>
    """
    _embed_html(body, css=PAGE_CSS, height=780)


def render_injury_page(data: InjuryPage) -> None:
    cards = ""
    for p in data.bench_injured or data.flagged:
        badge, cls = injury_badge(p.injury)
        cards += f"""
        <div class="dz-injury-card">
            {_img(p.headshot, p.name, 48)}
            <div>
                <p class="dz-player-name">{html.escape(p.name)}<span class="dz-status {cls}">{html.escape(badge.upper())}</span></p>
                <p class="dz-player-meta">{html.escape(p.position)} · {html.escape(p.team or "FA")}</p>
                <p class="dz-player-meta">{html.escape(p.depth_note or "Bench / reserves")}</p>
            </div>
            <div class="dz-val-col">{html.escape(p.value_label)}<br><span style="color:#6b7280;font-weight:400;font-size:0.62rem;">dynasty value</span></div>
        </div>
        """
    if not cards:
        cards = '<p style="color:#10b981;font-size:0.82rem;">No injury flags on your roster.</p>'

    legend = [
        ("IR", "ir", "Injured Reserve — out a minimum of 4 games."),
        ("PUP", "pup", "Physically Unable to Perform — sidelined at least 4 weeks."),
        ("Out", "out", "Out — will not play this week."),
        ("Doubtful", "doubtful", "Doubtful — roughly 75% unlikely to play."),
        ("Questionable", "questionable", "Questionable — a true 50/50 chance to play."),
        ("Probable", "probable", "Probable — expected to play barring setback."),
    ]
    legend_html = "".join(
        f'<div class="dz-legend-item"><span class="dz-status {cls}">{lbl}</span><span>{html.escape(desc)}</span></div>'
        for lbl, cls, desc in legend
    )

    callout = f'<p class="dz-callout">{html.escape(data.callout)}</p>' if data.callout else ""

    body = f"""
    <div class="dz-page-head">
        <div>
            <h1 class="dz-page-title"><span class="dz-page-icon">♡</span> Injury Report</h1>
            <p class="dz-sub">Statuses from your platform roster feed</p>
        </div>
    </div>
    <div class="dz-info">Statuses come from your platform's roster feed. During the offseason they can run stale — treat tags as last-known, not live.</div>
    {callout}
    <p style="color:#9ca3af;font-size:0.72rem;font-weight:700;letter-spacing:0.08em;margin:0 0 0.5rem 0;">BENCH & RESERVES</p>
    {cards}
    <div class="dz-card"><p style="color:#fff;font-weight:700;font-size:0.82rem;margin:0 0 0.35rem 0;">Designation guide</p><div class="dz-legend">{legend_html}</div></div>
    """
    _embed_html(body, css=PAGE_CSS, height=820)


def _timeline_html(rooms) -> str:
    rows = ""
    for room in rooms:
        dots = ""
        for i, p in enumerate(room.players):
            left = min(92, max(8, (p.age or 24) / 35 * 100))
            dots += f'<div class="dz-timeline-dot" style="left:{left}%;--c:{room.color}">{_img(p.headshot, p.name, 28)}</div>'
        rows += f"""
        <div class="dz-timeline-row">
            <div class="dz-timeline-label">{html.escape(room.position)} {html.escape(room.label.split()[0])}<br><span style="color:#10b981">{html.escape(str(room.total_value // 1000))}.{room.total_value % 1000 // 100}K</span> {room.pct}% · {len(room.players)}</div>
            <div class="dz-timeline-track">{dots}</div>
        </div>
        """
    return rows


def render_my_team_page(data: MyTeamPage) -> None:
    ledger = ""
    for room in data.rooms:
        ledger += f'<div class="dz-room-head" style="--room:{room.color}"><p class="dz-room-title">{html.escape(room.position)} {html.escape(room.label)} · {len(room.players)} players</p><span class="dz-room-val">{html.escape(str(room.total_value // 1000))}.{room.total_value % 1000 // 100}K · {room.pct}% of team</span></div>'
        for p in room.players:
            rank = f"#{p.fc_rank} BOARD" if p.fc_rank else "—"
            ledger += f"""
            <div class="dz-row">
                <div class="dz-player-cell">{_img(p.headshot, p.name)}<div>
                    <p class="dz-player-name">{html.escape(p.name)}</p>
                    <p class="dz-player-meta">{html.escape(p.team or "FA")} · {html.escape(p.position)}</p>
                </div></div>
                <div class="dz-val-col">{html.escape(p.value_label)}<br><span style="color:#6b7280;font-weight:400;font-size:0.58rem;">{round(p.value / max(data.total_value, 1) * 100, 1)}% of team</span></div>
                <div class="dz-rank-col">{rank}</div>
                <span class="dz-signal {html.escape(p.signal)}">{html.escape(p.signal)}</span>
                <div class="dz-age-col">{html.escape(p.age and str(int(p.age)) or "—")} PRIME</div>
            </div>
            """

    body = f"""
    <div class="dz-page-head">
        <div>
            <h1 class="dz-page-title"><span class="dz-page-icon">★</span> My Team</h1>
            <p class="dz-sub">Dynasty roster value and composition</p>
        </div>
        <span class="dz-live-btn">⚡ Live values</span>
    </div>
    <div class="dz-timeline">{_timeline_html(data.rooms)}</div>
    <div class="dz-ledger-head">
        <div>
            <p style="color:#fff;font-weight:800;font-size:0.95rem;margin:0;">The Roster Ledger</p>
            <p class="dz-sub">{data.shown} of {data.total_players} players shown · dynasty values · worth {data.total_value // 1000}.{data.total_value % 1000 // 100}K together</p>
        </div>
    </div>
    <div class="dz-filters">
        <div class="dz-filter-grp"><span class="dz-filter-lbl">ROOM</span><span class="dz-filter on">QB</span><span class="dz-filter on">RB</span><span class="dz-filter on">WR</span><span class="dz-filter on">TE</span></div>
        <div class="dz-filter-grp"><span class="dz-filter-lbl">SIGNAL</span><span class="dz-filter">Buy</span><span class="dz-filter">Sell</span><span class="dz-filter on">Hold</span></div>
        <div class="dz-filter-grp"><span class="dz-filter-lbl">SORT</span><span class="dz-filter on">Value ↓</span><span class="dz-filter">Age</span><span class="dz-filter">Rank</span></div>
    </div>
    {ledger}
    """
    _embed_html(body, css=PAGE_CSS, height=960)


def render_player_list_page(title: str, icon: str, subtitle: str, players: list[PlayerCard], empty_msg: str = "Nothing to show.") -> None:
    rows = ""
    for p in players:
        rows += f"""
        <div class="dz-row" style="grid-template-columns:1fr auto auto;">
            <div class="dz-player-cell">{_img(p.headshot, p.name)}<div>
                <p class="dz-player-name">{html.escape(p.name)}</p>
                <p class="dz-player-meta">{html.escape(p.position)} · {html.escape(p.team or "FA")} · {html.escape(p.depth_note)}</p>
            </div></div>
            <div class="dz-val-col">{html.escape(p.value_label)}</div>
            <span class="dz-signal {html.escape(p.signal)}">{html.escape(p.signal)}</span>
        </div>
        """
    if not rows:
        rows = f'<p style="color:#6b7280;font-size:0.78rem;">{html.escape(empty_msg)}</p>'

    body = f"""
    <div class="dz-page-head">
        <div><h1 class="dz-page-title"><span class="dz-page-icon">{icon}</span> {html.escape(title)}</h1><p class="dz-sub">{html.escape(subtitle)}</p></div>
    </div>
    <div class="dz-card">{rows}</div>
    """
    _embed_html(body, css=PAGE_CSS, height=640)


def render_waiver_wire_page(adds: list[dict], drops: list[dict]) -> None:
    def _items(rows: list[dict]) -> str:
        if not rows:
            return '<p style="color:#6b7280;font-size:0.72rem;">No trending data.</p>'
        out = ""
        for r in rows[:15]:
            name = r.get("player") or r.get("name") or "—"
            meta = r.get("position") or r.get("pos") or ""
            out += f'<div class="dz-wire-item"><div><div class="dz-wire-name">{html.escape(str(name))}</div><div class="dz-wire-meta">{html.escape(str(meta))}</div></div></div>'
        return out

    body = f"""
    <div class="dz-page-head">
        <div><h1 class="dz-page-title"><span class="dz-page-icon">＋</span> Waiver Wire</h1><p class="dz-sub">Trending adds and drops across the league</p></div>
    </div>
    <div class="dz-wire-grid">
        <div class="dz-card"><h3 style="color:#fff;font-size:0.82rem;margin:0 0 0.65rem 0;">Trending adds</h3>{_items(adds)}</div>
        <div class="dz-card"><h3 style="color:#fff;font-size:0.82rem;margin:0 0 0.65rem 0;">Trending drops</h3>{_items(drops)}</div>
    </div>
    """
    _embed_html(body, css=PAGE_CSS, height=620)


def render_replacement_radar_page(targets: list) -> None:
    rows = ""
    for w in targets[:20]:
        rows += f"""
        <div class="dz-row" style="grid-template-columns:1fr auto;">
            <div><p class="dz-player-name">{html.escape(w.player)}</p><p class="dz-player-meta">{html.escape(w.position)} · ADP {w.adp or "—"} · {html.escape(w.reason[:80])}</p></div>
            <div class="dz-val-col">{html.escape(w.reason.split()[0] if w.reason else "Fit")}</div>
        </div>
        """
    if not rows:
        rows = '<p style="color:#6b7280;font-size:0.78rem;">No strong waiver fits right now.</p>'

    body = f"""
    <div class="dz-page-head">
        <div><h1 class="dz-page-title"><span class="dz-page-icon">◎</span> Replacement Radar</h1><p class="dz-sub">Waiver targets that fit your roster holes</p></div>
    </div>
    <div class="dz-card">{rows}</div>
    """
    _embed_html(body, css=PAGE_CSS, height=620)
