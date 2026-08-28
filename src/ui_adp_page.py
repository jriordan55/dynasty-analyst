"""Dynatyze-style Player ADP page — mirrors dynatyze.com/football/adp."""

from __future__ import annotations

import html

from src.adp_sources import AdpBoardRow, AdpSourceCard, _headshot
from src.ui_dynatyze import _embed_html

ADP_CSS = """
body { margin: 0; background: #0a0a0a; color: #e5e7eb; font-family: Montserrat, system-ui, sans-serif; }
.dz-adp-head { margin-bottom: 1rem; }
.dz-adp-title { color: #fff; font-size: 1.5rem; font-weight: 800; margin: 0; }
.dz-adp-sub { color: #6b7280; font-size: 0.75rem; margin: 0.25rem 0 0 0; }
.dz-sources { display: grid; grid-template-columns: repeat(auto-fill, minmax(108px, 1fr)); gap: 0.5rem; margin-bottom: 1rem; }
.dz-src { background: #111827; border: 1px solid #1f2937; border-radius: 0.55rem; padding: 0.55rem 0.6rem; min-height: 72px; }
.dz-src-name { color: #f3f4f6; font-size: 0.62rem; font-weight: 700; line-height: 1.2; margin: 0 0 0.25rem 0; }
.dz-src-status { font-size: 0.52rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.08rem 0.3rem; border-radius: 0.25rem; display: inline-block; }
.dz-src-status.fresh { background: rgba(16,185,129,0.15); color: #10b981; }
.dz-src-status.degraded { background: rgba(239,68,68,0.12); color: #f87171; }
.dz-src-meta { color: #6b7280; font-size: 0.52rem; margin-top: 0.25rem; }
.dz-src-tags { margin-top: 0.2rem; }
.dz-src-tag { display: inline-block; background: #0f1115; border: 1px solid #374151; color: #9ca3af; font-size: 0.48rem; font-weight: 700; padding: 0.05rem 0.25rem; border-radius: 0.2rem; margin-right: 0.15rem; }
.dz-lens { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.85rem; flex-wrap: wrap; }
.dz-lens-label { color: #9ca3af; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.dz-lens-toggle { display: inline-flex; background: #111827; border: 1px solid #374151; border-radius: 999px; overflow: hidden; }
.dz-lens-toggle span { padding: 0.35rem 0.7rem; font-size: 0.68rem; font-weight: 700; color: #9ca3af; }
.dz-lens-toggle span.on { background: #10b981; color: #000; }
.dz-table-head { display: grid; grid-template-columns: 3.5rem 1.4fr 1fr 4.5rem 1.2fr; gap: 0.65rem; padding: 0.45rem 0.65rem; color: #6b7280; font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; border-bottom: 1px solid #1f2937; }
.dz-adp-row { display: grid; grid-template-columns: 3.5rem 1.4fr 1fr 4.5rem 1.2fr; gap: 0.65rem; align-items: center; padding: 0.65rem; background: #0f1115; border: 1px solid #1f2937; border-radius: 0.65rem; margin-bottom: 0.45rem; }
.dz-rank-num { color: #fff; font-size: 1.35rem; font-weight: 800; line-height: 1; }
.dz-rank-ovr { color: #6b7280; font-size: 0.52rem; font-weight: 700; letter-spacing: 0.08em; }
.dz-player { display: flex; align-items: center; gap: 0.55rem; min-width: 0; }
.dz-player img { width: 40px; height: 40px; border-radius: 999px; object-fit: cover; background: #111827; flex-shrink: 0; }
.dz-player-name { color: #fff; font-weight: 700; font-size: 0.88rem; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dz-player-pos { color: #6b7280; font-size: 0.65rem; margin: 0.1rem 0 0 0; }
.dz-consensus-lbl { color: #6b7280; font-size: 0.55rem; font-weight: 700; letter-spacing: 0.08em; }
.dz-consensus-num { color: #fff; font-weight: 800; font-size: 0.82rem; }
.dz-consensus-delta { color: #10b981; font-size: 0.62rem; font-weight: 700; margin-left: 0.25rem; }
.dz-consensus-delta.neg { color: #f87171; }
.dz-conf-bar { width: 100%; max-width: 120px; height: 4px; background: #1f2937; border-radius: 999px; overflow: hidden; margin-top: 0.25rem; }
.dz-conf-fill { height: 100%; background: #10b981; border-radius: 999px; }
.dz-adp-badge { width: 42px; height: 42px; border-radius: 999px; background: rgba(16,185,129,0.15); border: 2px solid #10b981; color: #10b981; font-weight: 800; font-size: 0.82rem; display: grid; place-items: center; margin: 0 auto; box-shadow: 0 0 12px rgba(16,185,129,0.25); }
.dz-signals { display: flex; flex-wrap: wrap; gap: 0.25rem; justify-content: flex-end; }
.dz-sig { font-size: 0.52rem; font-weight: 800; padding: 0.12rem 0.35rem; border-radius: 0.3rem; border: 1px solid #374151; color: #9ca3af; white-space: nowrap; }
.dz-sig.hold { color: #9ca3af; border-color: #374151; }
.dz-sig.buy { color: #10b981; border-color: #10b981; }
.dz-sig.sell { color: #f87171; border-color: #f87171; }
.dz-sig.proj { color: #d1d5db; border-color: #4b5563; }
.dz-sig.vgs { color: #10b981; border-color: rgba(16,185,129,0.45); background: rgba(16,185,129,0.08); }
@media (max-width: 760px) {
  .dz-table-head { display: none; }
  .dz-adp-row { grid-template-columns: 2.5rem 1fr auto; grid-template-rows: auto auto; }
  .dz-consensus-col { grid-column: 2 / 4; }
  .dz-signals-col { grid-column: 1 / 4; justify-content: flex-start; }
}
"""


def _img(player_id: str, name: str) -> str:
    src = _headshot(player_id)
    if src:
        return f'<img src="{html.escape(src)}" alt="{html.escape(name)}" onerror="this.style.display=\'none\'">'
    initial = name[:1] if name else "?"
    return f'<div style="width:40px;height:40px;border-radius:999px;background:#111827;display:grid;place-items:center;color:#fff;font-weight:700;">{html.escape(initial)}</div>'


def _source_card(src: AdpSourceCard) -> str:
    status_cls = "fresh" if src.status == "FRESH" else "degraded"
    tags = "".join(f'<span class="dz-src-tag">{html.escape(t)}</span>' for t in src.tags)
    return (
        f'<div class="dz-src"><p class="dz-src-name">{html.escape(src.name)}</p>'
        f'<span class="dz-src-status {status_cls}">{html.escape(src.status)}</span>'
        f'<p class="dz-src-meta">{html.escape(src.age_label)} · {src.players} players</p>'
        f'<div class="dz-src-tags">{tags}</div></div>'
    )


def _row_html(row: AdpBoardRow) -> str:
    delta = row.consensus_delta
    delta_cls = "neg" if delta and delta < 0 else ""
    delta_txt = f"+{delta:.1f}" if delta and delta > 0 else (f"{delta:.1f}" if delta else "+0.0")
    conf_pct = min(98, max(40, int(100 - abs(delta or 0) * 8)))
    adp_val = f"{row.consensus:.1f}" if row.consensus else "—"
    sig_cls = row.signal.lower()
    sig_delta = row.signal_delta
    vgs = f"VGS {row.vgs}" if row.vgs else "VGS —"
    return (
        f'<div class="dz-adp-row">'
        f'<div><div class="dz-rank-num">{row.rank}</div><div class="dz-rank-ovr">OVR</div></div>'
        f'<div class="dz-player">{_img(row.player_id, row.player)}<div>'
        f'<p class="dz-player-name">{html.escape(row.player)}</p>'
        f'<p class="dz-player-pos">{html.escape(row.pos_label)}</p></div></div>'
        f'<div class="dz-consensus-col"><span class="dz-consensus-lbl">CONSENSUS </span>'
        f'<span class="dz-consensus-num">{row.consensus_rank or row.rank}</span>'
        f'<span class="dz-consensus-delta {delta_cls}">{delta_txt}</span>'
        f'<div class="dz-conf-bar"><div class="dz-conf-fill" style="width:{conf_pct}%"></div></div></div>'
        f'<div><div class="dz-adp-badge">{html.escape(adp_val)}</div></div>'
        f'<div class="dz-signals dz-signals-col">'
        f'<span class="dz-sig {sig_cls}">{html.escape(row.signal)} {sig_delta:+d}</span>'
        f'<span class="dz-sig proj">{html.escape(row.proj_label)}</span>'
        f'<span class="dz-sig vgs">{html.escape(vgs)}</span></div></div>'
    )


def render_adp_page(
    board: list[AdpBoardRow],
    sources: list[AdpSourceCard],
    scoring: str = "Half-PPR",
    note: str = "",
) -> None:
    src_html = "".join(_source_card(s) for s in sources)
    rows_html = "".join(_row_html(r) for r in board[:75])
    scoring_opts = [("Standard", "0 / rec"), ("Half-PPR", "0.5 / rec"), ("PPR", "1 / rec")]
    lens = ""
    for opt, rec in scoring_opts:
        on = "on" if opt == scoring else ""
        abbr = "Ha" if opt == "Half-PPR" else opt[:2]
        lens += f'<span class="{on}">{html.escape(abbr)} {html.escape(opt)}<br><small style="font-weight:500;opacity:0.7">{html.escape(rec)}</small></span>'

    body = f"""
<div class="dz-adp-head">
<p class="dz-adp-title">Player ADP</p>
<p class="dz-adp-sub">Consensus average draft position · {html.escape(note[:120])}</p>
</div>
<div class="dz-sources">{src_html}</div>
<div class="dz-lens">
<span class="dz-lens-label">League lens</span>
<div class="dz-lens-toggle">{lens}</div>
</div>
<div class="dz-table-head">
<span>Rank</span><span>Player</span><span>Consensus</span><span>ADP</span><span>Signals</span>
</div>
{rows_html}
"""
    _embed_html(body, css=ADP_CSS, height=1100)
