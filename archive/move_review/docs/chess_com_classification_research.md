# Chess.com Classification — Research Notes

## Core Model

Win Probability Loss (WPL), not raw centipawn loss.

```
win_prob(cp, elo) = 1 / (1 + exp(-k * cp))
k = 0.00368208 * (1 + (elo - 1500) / 10000)
WPL = win_prob(before) - win_prob(after)  (from player's perspective)
```

Classification is **position-dependent** — same eval swing is weighted differently depending on whether position is equal vs already decided.

---

## Category Definitions (Chess.com Official)

**Book** — move matches opening theory database.

**Brilliant (!!)** — best move + material sacrifice + eval improves ~1.5+ pawns + NOT already winning. Post-2021 definition is sacrifice-based.

**Great (!)** — "the only good move; everything else significantly worsens position." Requires multipv: gap between 1st and 2nd best must be large. Also triggers when: equalizes losing position, or punishes opponent's mistake to gain winning advantage.

**Miss (Ø)** — opponent made a bad move on previous turn, you failed to exploit it. NOT just "was winning, played suboptimal." Introduced Nov 2022.

**Best** — engine's top move, BUT only when it meaningfully outperforms alternatives (multipv gap >= ~30cp). When alternatives are nearly equal, top move → Excellent instead.

**Excellent** — near-best, very low WPL. Also: engine top move when multipv gap is small.

**Good** — acceptable WPL, doesn't worsen position significantly.

**Inaccuracy** — ~1 pawn eval swing.

**Mistake** — ~3 pawn eval swing, immediately worsens position.

**Blunder** — TWO criteria required (Nov 2022 update): (1) large eval drop AND (2) loses material or allows forced mate. Positional-only eval drops → Mistake, not Blunder.

---

## CAPS2 Accuracy

```
avg_wpl = mean(max(0, wpl * 100)) per player's moves
accuracy = 103.1668 * exp(-0.04354 * avg_wpl) - 3.1669
clamped [0, 100]
```
Rating-aware (Elo affects sigmoid). Most scores 50-95.

## Game Rating

Maps accuracy → fictional Elo. Proprietary formula, likely polynomial/lookup:
- ~1000 Elo → ~55 accuracy
- ~1500 Elo → ~68 accuracy
- ~2000 Elo → ~80 accuracy
- ~2500 Elo → ~88 accuracy

---

## Code Bugs

1. **Multipv discarded** — engine calls `multipv=3` but only stores `info[0]`. Great/Best detection has no data.
2. **Great gap calc wrong** — compares consecutive position evals instead of alternative moves in same position.
3. **Best over-counted** — every engine-match → Best. Needs multipv gap filter.
4. **Blunder missing material check** — only uses WPL > 0.20, no concrete-consequences check.
5. **Miss wrong definition** — checks "was winning + suboptimal" instead of "opponent blundered, you didn't punish."
6. **Book only checks top entry** — `find()` returns highest-weight only. Need `find_all()`.
7. **Mate scores too coarse** — mate-in-1 and mate-in-20 both ±10000.
8. **Game rating formula broken** — linear mapping is off by 300+ points.

## Fix Order

1. Engine: store multipv data
2. Book: use `find_all()`
3. Great: use real multipv gap
4. Best: add multipv gap filter
5. Blunder: add material-loss / forced-mate check
6. Miss: check opponent's previous move was an error
7. Accuracy / game rating calibration
