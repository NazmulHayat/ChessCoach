"""Per-move rows for analysed rapid games from the Lichess dump (skips the analysed games the shipped model was fit on)."""
import math, re, sys, zlib
from multiprocessing import Pool
import numpy as np, zstandard

DUMP = "/Users/nazmulhayat/Desktop/Programming/ChessCoach/lichess_db_standard_rated_2026-02.pgn.zst"
HEADER_RE = re.compile(r'^\[(\w+) "([^"]*)"\]', re.M)
CMT_RE = re.compile(r"(\d+)(\.\.\.|\.)\s+\S+\s+\{([^}]*)\}")
EVAL_RE = re.compile(r"\[%eval\s+(#?)(-?[\d.]+)\]")
CLK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+)\]")
SEP = b"\n\n[Event "
SKIP_ANALYSED = 250_000
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 60_000

def wp(cp):
    cp = max(-1000.0, min(1000.0, cp)); return 1 / (1 + math.exp(-0.00368208 * cp))

def game(raw):
    t = raw.decode("utf-8", "replace"); s = t.find("\n\n")
    if s < 0: return None
    h = dict(HEADER_RE.findall(t[:s]))
    if h.get("Variant", "Standard") != "Standard": return None
    tc = h.get("TimeControl", "-")
    if "+" not in tc: return None
    init, inc = (int(x) for x in tc.split("+"))
    if not (480 <= init < 1500): return "other"
    try: elo = {0: int(h["WhiteElo"]), 1: int(h["BlackElo"])}
    except Exception: return None
    res = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}.get(h.get("Result"))
    ev, clk = {}, {}
    for m in CMT_RE.finditer(t[s + 2:]):
        ply = (int(m.group(1)) - 1) * 2 + (0 if m.group(2) == "." else 1)
        e = EVAL_RE.search(m.group(3)); c = CLK_RE.search(m.group(3))
        if e: ev[ply] = (1000.0 if not e.group(2).startswith("-") else -1000.0) if e.group(1) == "#" else float(e.group(2)) * 100
        if c: clk[ply] = int(c.group(1)) * 3600 + int(c.group(2)) * 60 + int(c.group(3))
    if not ev: return None
    rows = []
    for i in range(1, max(ev) + 1):
        if i - 1 not in ev or i not in ev: continue
        side = i % 2; sign = 1.0 if side == 0 else -1.0
        cpb = sign * ev[i - 1]
        loss = max(0.0, wp(cpb) - wp(sign * ev[i]))
        clock = clk.get(i - 2, init)  # mover's clock before this move
        rows.append((side, i, loss, cpb, clock / init, init, inc))
    if len(rows) < 20: return None
    return {"w": h.get("White", ""), "b": h.get("Black", ""), "elo": elo, "res": res, "rows": rows}

def chunk(blob):
    out, n_an = [], 0
    for raw in blob.split(SEP):
        if b"[%eval" not in raw: continue
        n_an += 1
        g = game(raw)
        if isinstance(g, dict): out.append(g)
    return n_an, out

def blobs():
    with open(DUMP, "rb") as f:
        r = zstandard.ZstdDecompressor().stream_reader(f, read_size=4 << 20); carry = b""
        while True:
            d = r.read(16 << 20)
            if not d: break
            buf = carry + d; cut = buf.rfind(SEP)
            carry = buf[cut + 2:]; yield buf[:cut]

if __name__ == "__main__":
    seen, games = 0, []
    with Pool(9) as p:
        for n_an, gs in p.imap(chunk, blobs()):
            if seen >= SKIP_ANALYSED: games.extend(gs)
            seen += n_an
            if len(games) >= TARGET: break
            print(seen, len(games), flush=True, file=sys.stderr) if seen % 50 == 0 else None
    # flatten to player-games
    pg, mv = [], []
    for gi, g in enumerate(games[:TARGET]):
        for side in (0, 1):
            rs = [r for r in g["rows"] if r[0] == side]
            if len(rs) < 10: continue
            name = g["w"] if side == 0 else g["b"]
            sc = None if g["res"] is None else (g["res"] if side == 0 else 1 - g["res"])
            pid = len(pg)
            pg.append((gi, zlib.crc32(name.encode()), g["elo"][side], g["elo"][1 - side], -1 if sc is None else sc, len(rs)))
            mv.extend((pid,) + r[1:] for r in rs)
    np.savez("/private/tmp/claude-501/-Users-nazmulhayat-Desktop-Programming-ChessCoach/ad350f4a-12a7-43e3-b193-25949b70ac2c/scratchpad/gr/rapid.npz", pg=np.array(pg, dtype=np.int64), mv=np.array(mv, dtype=np.float64))
    print("games", len(games[:TARGET]), "player-games", len(pg), "moves", len(mv), "analysed seen", seen)
