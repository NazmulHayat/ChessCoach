"""Self-contained HTML report for a review_game() result (inline SVG chart, no external assets)."""

from __future__ import annotations

import html
from typing import Any

LABEL_ORDER = ["best", "excellent", "good", "inaccuracy", "mistake", "blunder"]


def _white_to_move_series(r: dict[str, Any], key: str) -> list[tuple[int, float]]:
    """(move_number, white expected score) at each white-to-move position: one perspective, no zig-zag."""
    out = []
    for ply_idx, v in enumerate(r[key]):
        if ply_idx % 2 == 0:
            out.append((ply_idx // 2 + 1, v))
    return out


def _chart_svg(r: dict[str, Any]) -> str:
    w, h, pad_l, pad_r, pad_t, pad_b = 760, 260, 44, 12, 12, 28
    ep = _white_to_move_series(r, "white_ep_by_ply")
    li = _white_to_move_series(r, "white_lichess_by_ply")
    n = max(len(ep), 2)

    def x(i: int) -> float:
        return pad_l + (w - pad_l - pad_r) * i / (n - 1)

    def y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1.0 - v)

    def path(series: list[tuple[int, float]]) -> str:
        return " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(series))

    grid = []
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        grid.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid{" mid" if v == 0.5 else ""}"/>')
        grid.append(f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" class="axis" text-anchor="end">{int(v * 100)}%</text>')
    step = max(1, n // 10)
    for i in range(0, n, step):
        grid.append(f'<text x="{x(i):.1f}" y="{h - 8}" class="axis" text-anchor="middle">{ep[i][0] if i < len(ep) else ""}</text>')

    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="White expected score by move">'
        + "".join(grid)
        + f'<path d="{path(li)}" class="line lichess"/>'
        + f'<path d="{path(ep)}" class="line ep"/>'
        + "</svg>"
    )


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{100 * v:.1f}%"


def render_html(r: dict[str, Any]) -> str:
    hd = r["headers"]
    esc = html.escape
    white, black = esc(hd.get("White", "White")), esc(hd.get("Black", "Black"))
    title = f"{white} vs {black}"

    cards = []
    for side, name, elo in (("white", white, r["white_elo"]), ("black", black, r["black_elo"])):
        s = r["summary"][side]
        chips = "".join(
            f'<span class="chip {lab}">{s["labels"][lab]} {lab}</span>' for lab in LABEL_ORDER if s["labels"].get(lab)
        )
        cards.append(
            f'<div class="card"><div class="side">{side}</div><div class="name">{name} <span class="muted">({elo})</span></div>'
            f'<div class="stat">{_pct(s["avg_ep_loss"])}<span class="muted"> avg EP loss / move</span></div>'
            f'<div class="chips">{chips}</div></div>'
        )

    rows = []
    for m in r["moves"]:
        num = f"{m['move_number']}{'.' if m['mover'] == 'white' else '…'}"
        differs = m["ep_label"] != m["lichess_label"]
        best = "" if m["ep_label"] == "best" else esc(m["best_san"] or "")
        rows.append(
            f'<tr class="{"differs" if differs else ""}"><td class="num">{num}</td><td class="san">{esc(m["san"])}</td>'
            f'<td class="r">{_pct(m["ep_best"])}</td><td class="r">{_pct(m["ep_after"])}</td>'
            f'<td class="r">{_pct(m["ep_loss"])}</td>'
            f'<td><span class="chip {m["ep_label"]}">{m["ep_label"]}</span></td>'
            f'<td><span class="chip {m["lichess_label"]} ghost">{m["lichess_label"]}</span></td>'
            f'<td class="san muted">{best}</td></tr>'
        )

    n_diff = sum(1 for m in r["moves"] if m["ep_label"] != m["lichess_label"])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EP Game Review</title>
<style>
:root {{
  --bg:#f7f6f3; --surface:#ffffff; --text:#1d1d1f; --muted:#6b6b70; --line:#e4e2dc;
  --ep:#2f6fdb; --lichess:#a3a3a8; --hl:#fff6dc;
  --best:#1e8e5a; --excellent:#3aa676; --good:#7a8b99; --inaccuracy:#d29a1e; --mistake:#e0702a; --blunder:#d13b3b;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#141416; --surface:#1d1d20; --text:#ececef; --muted:#9a9aa2; --line:#2e2e33; --ep:#6c9cff; --lichess:#6a6a72; --hl:#2c2717;
}} }}
:root[data-theme="dark"] {{
  --bg:#141416; --surface:#1d1d20; --text:#ececef; --muted:#9a9aa2; --line:#2e2e33; --ep:#6c9cff; --lichess:#6a6a72; --hl:#2c2717;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }}
h2 {{ font-size:16px; margin:36px 0 10px; }}
.muted {{ color:var(--muted); }}
.meta {{ color:var(--muted); margin-bottom:24px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; }}
.side {{ text-transform:uppercase; font-size:11px; letter-spacing:0.08em; color:var(--muted); }}
.name {{ font-weight:600; margin:2px 0 10px; }}
.stat {{ font-size:22px; font-weight:600; margin-bottom:10px; }}
.stat .muted {{ font-size:13px; font-weight:400; }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.chip {{ display:inline-block; font-size:12px; padding:1px 8px; border-radius:999px; color:#fff; background:var(--good); white-space:nowrap; }}
.chip.ghost {{ background:transparent; color:var(--muted); border:1px solid var(--line); }}
{"".join(f".chip.{lab}:not(.ghost) {{ background:var(--{lab}); }}" for lab in LABEL_ORDER)}
.chart {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:12px; }}
svg {{ width:100%; height:auto; display:block; }}
.grid {{ stroke:var(--line); stroke-width:1; }} .grid.mid {{ stroke-dasharray:4 4; }}
.axis {{ fill:var(--muted); font-size:11px; }}
.line {{ fill:none; stroke-width:2; }} .line.ep {{ stroke:var(--ep); stroke-width:2.5; }} .line.lichess {{ stroke:var(--lichess); stroke-dasharray:5 4; }}
.legend {{ display:flex; gap:18px; font-size:13px; color:var(--muted); margin:8px 4px 0; flex-wrap:wrap; }}
.key {{ display:inline-block; width:18px; height:0; border-top:2.5px solid var(--ep); vertical-align:middle; margin-right:6px; }}
.key.lichess {{ border-top:2px dashed var(--lichess); }}
.table-wrap {{ overflow-x:auto; background:var(--surface); border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th, td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ font-size:12px; font-weight:600; color:var(--muted); position:sticky; top:0; background:var(--surface); }}
td.r, th.r {{ text-align:right; font-variant-numeric:tabular-nums; }}
td.num {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
td.san {{ font-weight:600; }}
tr.differs td {{ background:var(--hl); }}
tr:last-child td {{ border-bottom:none; }}
</style></head>
<body><main>
<h1>{title}</h1>
<div class="meta">{esc(hd.get("Result", "*"))} · {esc(r["time_class"])} {esc(hd.get("TimeControl", ""))} · rating band {esc(r["rating_band"])} · Stockfish depth {r["engine_depth"]}</div>
<div class="cards">{"".join(cards)}</div>
<h2>White's expected score</h2>
<div class="chart">{_chart_svg(r)}
<div class="legend"><span><span class="key"></span>EP model (rating, clock and time control aware)</span><span><span class="key lichess"></span>Eval-only (Lichess win% curve)</span></div></div>
<h2>Moves <span class="muted" style="font-weight:400">· {n_diff} highlighted where EP and eval-only labels disagree</span></h2>
<div class="table-wrap"><table>
<thead><tr><th>#</th><th>Move</th><th class="r">EP if best</th><th class="r">EP after</th><th class="r">EP loss</th><th>EP label</th><th>Eval-only</th><th>Engine best</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
</main></body></html>
"""
