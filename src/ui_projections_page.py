"""Dynatyze-style 2026 NFL Projections Board."""

from __future__ import annotations

import html

from src.adp_sources import _headshot
from src.projections_board import ProjectionsPage, ProjectionRow, SOURCE_COLORS
from src.ui_dynatyze import _embed_html

PROJ_CSS = """
body { margin: 0; background: #0a0a0a; color: #e5e7eb; font-family: Montserrat, system-ui, sans-serif; }
.dz-proj-title { color: #fff; font-size: 1.55rem; font-weight: 800; margin: 0; }
.dz-proj-sub { color: #6b7280; font-size: 0.75rem; margin: 0.25rem 0 0.75rem 0; max-width: 42rem; line-height: 1.45; }
.dz-alert { background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.35); border-radius: 0.65rem; padding: 0.65rem 0.85rem; color: #a7f3d0; font-size: 0.68rem; line-height: 1.45; margin-bottom: 0.85rem; }
.dz-consensus-bar { background: #111827; border: 1px solid #1f2937; border-radius: 0.65rem; padding: 0.75rem 0.85rem; margin-bottom: 0.85rem; }
.dz-consensus-meta { display: flex; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 0.55rem; color: #9ca3af; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.dz-consensus-meta b { color: #fff; font-size: 0.82rem; display: block; margin-top: 0.1rem; }
.dz-blend-label { color: #6b7280; font-size: 0.55rem; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 0.35rem; }
.dz-blend-bar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: #1f2937; }
.dz-blend-seg { height: 100%; }
.dz-insight { color: #10b981; font-size: 0.72rem; margin-top: 0.55rem; line-height: 1.4; }
.dz-bg-label { color: #6b7280; font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; margin: 0.85rem 0 0.45rem 0; }
.dz-bg-scroll { display: flex; gap: 0.55rem; overflow-x: auto; padding-bottom: 0.35rem; margin-bottom: 0.85rem; }
.dz-bg-card { flex: 0 0 210px; background: #0f1115; border: 1px solid #1f2937; border-radius: 0.65rem; padding: 0.65rem; }
.dz-bg-top { display: flex; align-items: center; gap: 0.45rem; margin-bottom: 0.35rem; }
.dz-bg-top img { width: 32px; height: 32px; border-radius: 999px; object-fit: cover; background: #111827; }
.dz-bg-name { color: #fff; font-weight: 700; font-size: 0.72rem; margin: 0; }
.dz-bg-meta { color: #6b7280; font-size: 0.58rem; margin: 0; }
.dz-bg-delta { color: #10b981; font-weight: 800; font-size: 0.75rem; margin-left: auto; }
.dz-spread-track { position: relative; height: 28px; background: #111827; border-radius: 999px; margin: 0.35rem 0; }
.dz-spread-dot { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 8px; height: 8px; border-radius: 999px; }
.dz-bg-foot { color: #6b7280; font-size: 0.52rem; line-height: 1.35; }
.dz-toolbar { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.65rem; align-items: center; }
.dz-pill { background: #111827; border: 1px solid #374151; color: #9ca3af; font-size: 0.58rem; font-weight: 700; padding: 0.2rem 0.45rem; border-radius: 999px; }
.dz-pill.on { background: rgba(16,185,129,0.15); border-color: #10b981; color: #10b981; }
.dz-src-row { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; margin-bottom: 0.65rem; }
.dz-src-pill { font-size: 0.55rem; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 999px; border: 1px solid; }
.dz-count { color: #6b7280; font-size: 0.62rem; margin-left: auto; }
.dz-table-head { display: grid; grid-template-columns: 2rem 1.5fr 4rem 1.2fr 3.5rem 4rem 4rem 4.5rem 3.5rem; gap: 0.45rem; padding: 0.4rem 0.55rem; color: #6b7280; font-size: 0.52rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; border-bottom: 1px solid #1f2937; }
.dz-proj-row { display: grid; grid-template-columns: 2rem 1.5fr 4rem 1.2fr 3.5rem 4rem 4rem 4.5rem 3.5rem; gap: 0.45rem; align-items: center; padding: 0.55rem; background: #0f1115; border: 1px solid #1f2937; border-radius: 0.55rem; margin-bottom: 0.35rem; font-size: 0.72rem; }
.dz-rank { color: #6b7280; font-weight: 700; }
.dz-player { display: flex; align-items: center; gap: 0.45rem; min-width: 0; }
.dz-player img { width: 34px; height: 34px; border-radius: 999px; object-fit: cover; background: #111827; flex-shrink: 0; }
.dz-pname { color: #fff; font-weight: 700; font-size: 0.78rem; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dz-pmeta { color: #6b7280; font-size: 0.58rem; margin: 0.08rem 0 0 0; }
.dz-badge { display: inline-block; background: rgba(251,191,36,0.12); border: 1px solid rgba(251,191,36,0.35); color: #fbbf24; font-size: 0.48rem; font-weight: 800; padding: 0.05rem 0.25rem; border-radius: 0.2rem; margin-left: 0.2rem; }
.dz-half { color: #fff; font-weight: 800; font-size: 0.88rem; }
.dz-spread-row { position: relative; height: 22px; background: #111827; border-radius: 999px; overflow: visible; }
.dz-num { color: #d1d5db; font-weight: 600; font-size: 0.68rem; text-align: center; }
.dz-num.green { color: #10b981; }
.dz-conf-wrap { text-align: center; }
.dz-conf-num { color: #fff; font-weight: 700; font-size: 0.68rem; }
.dz-conf-bar { width: 100%; height: 3px; background: #1f2937; border-radius: 999px; margin-top: 0.15rem; overflow: hidden; }
.dz-conf-fill { height: 100%; background: #10b981; border-radius: 999px; }
.dz-drift { color: #6b7280; font-size: 0.62rem; text-align: center; }
@media (max-width: 900px) {
  .dz-table-head { display: none; }
  .dz-proj-row { grid-template-columns: 1.5rem 1fr auto; grid-template-areas: "r p pts" "r spread spread" "r meta meta"; }
  .dz-rank { grid-area: r; }
  .dz-player { grid-area: p; }
  .dz-half { grid-area: pts; }
}
"""


def _img(player_id: str, name: str, size: int = 34) -> str:
    src = _headshot(player_id)
    if src:
        return f'<img src="{html.escape(src)}" alt="{html.escape(name)}" onerror="this.style.display=\'none\'">'
    return f'<div style="width:{size}px;height:{size}px;border-radius:999px;background:#111827;display:grid;place-items:center;color:#fff;font-weight:700;font-size:0.65rem;">{html.escape(name[:1])}</div>'


def _spread_dots(row: ProjectionRow, wide: bool = False) -> str:
    if not row.source_values:
        return ""
    lo, hi = row.spread_min, row.spread_max
    span = max(hi - lo, 1)
    dots = ""
    for src, val in row.source_values.items():
        left = (val - lo) / span * 100
        color = SOURCE_COLORS.get(src, "#6b7280")
        dots += f'<div class="dz-spread-dot" style="left:{left:.1f}%;background:{color}"></div>'
    cls = "dz-spread-row" if not wide else "dz-spread-track"
    return f'<div class="{cls}">{dots}</div>'


def _battleground_card(row: ProjectionRow) -> str:
    badge = f'<span class="dz-bg-delta">+{row.spread_pct:.1f}</span>'
    foot = f"{row.spread_min:.1f} – {row.spread_max:.1f} HALF · {row.confidence}% of consensus"
    return (
        f'<div class="dz-bg-card"><div class="dz-bg-top">{_img(row.player_id, row.player, 32)}'
        f'<div><p class="dz-bg-name">{html.escape(row.player)}</p>'
        f'<p class="dz-bg-meta">{html.escape(row.pos_label)}</p></div>{badge}</div>'
        f'{_spread_dots(row, wide=True)}<p class="dz-bg-foot">{html.escape(foot)}</p></div>'
    )


def _table_row(row: ProjectionRow) -> str:
    badge = f'<span class="dz-badge">{html.escape(row.badge)}</span>' if row.badge else ""
    adp = f"{row.adp:.1f}" if row.adp else "—"
    drift = f"{row.drift_pct:+.1f}%"
    return (
        f'<div class="dz-proj-row">'
        f'<div class="dz-rank">{row.rank}</div>'
        f'<div class="dz-player">{_img(row.player_id, row.player)}<div>'
        f'<p class="dz-pname">{html.escape(row.player)}{badge}</p>'
        f'<p class="dz-pmeta">{html.escape(row.pos_label)}</p></div></div>'
        f'<div class="dz-half">{row.half_points:.1f}</div>'
        f'{_spread_dots(row)}'
        f'<div class="dz-num">{html.escape(adp)}</div>'
        f'<div class="dz-num green">{row.dz_value:.3f}</div>'
        f'<div class="dz-num">{row.vegas_delta:+.1f}</div>'
        f'<div class="dz-conf-wrap"><div class="dz-conf-num">{row.confidence}</div>'
        f'<div class="dz-conf-bar"><div class="dz-conf-fill" style="width:{row.confidence}%"></div></div></div>'
        f'<div class="dz-drift">{html.escape(drift)}</div></div>'
    )


def render_projections_page(data: ProjectionsPage, scoring: str = "Half-PPR") -> None:
    blend = ""
    for src in data.sources:
        blend += f'<div class="dz-blend-seg" style="width:{src.weight_pct}%;background:{src.color}"></div>'

    bg = "".join(_battleground_card(r) for r in data.battleground)
    rows = "".join(_table_row(r) for r in data.rows[:75])

    src_pills = ""
    for src in data.sources:
        src_pills += (
            f'<span class="dz-src-pill" style="color:{src.color};border-color:{src.color}">'
            f'{html.escape(src.name)}</span>'
        )

    scoring_opts = [("PPR", "PPR"), ("HALF", "Half-PPR"), ("STD", "Standard")]
    lens = ""
    for abbr, label in scoring_opts:
        on = " on" if label == scoring or abbr == scoring.upper()[:4] else ""
        if label == scoring:
            on = " on"
        elif abbr == "HALF" and scoring == "Half-PPR":
            on = " on"
        lens += f'<span class="dz-pill{on}">{html.escape(abbr)}</span>'

    body = f"""
<div class="dz-proj-title">2026 NFL Projections Board</div>
<p class="dz-proj-sub">Sources weighted by the accuracy they've earned — see exactly where they fight.</p>
<div class="dz-alert">Draft season — preseason underway. Season-long 2026 sheets covering the 17-game regular season — preseason snaps do not count toward them. Refreshed every Monday.</div>
<div class="dz-consensus-bar">
<div class="dz-consensus-meta">
<div><span>Players</span><b>{data.player_count}</b></div>
<div><span>Live sources</span><b>{data.source_count}</b></div>
</div>
<div class="dz-blend-label">Blend weights (observed accuracy)</div>
<div class="dz-blend-bar">{blend}</div>
<p class="dz-insight">{html.escape(data.insight)}</p>
</div>
<div class="dz-bg-label">Battleground players: widest spread — consensus</div>
<div class="dz-bg-scroll">{bg}</div>
<div class="dz-toolbar">
<span class="dz-pill on">QB</span><span class="dz-pill on">RB</span><span class="dz-pill on">WR</span><span class="dz-pill on">TE</span>
<span class="dz-pill">ALL TEAMS</span>
{lens}
<span class="dz-pill on">SEASON</span><span class="dz-pill">PER GAME</span>
</div>
<div class="dz-src-row"><span class="dz-pill" style="border:none;background:transparent;color:#6b7280">SOURCES</span>{src_pills}
<span class="dz-count">{len(data.rows)} of {data.player_count} players</span></div>
<div class="dz-table-head">
<span>#</span><span>Player</span><span>Half</span><span>Source spread</span><span>ADP</span><span>DZ Value</span><span>Vegas Δ</span><span>Confidence</span><span>Drift</span>
</div>
{rows}
"""
    _embed_html(body, css=PROJ_CSS, height=1400)
