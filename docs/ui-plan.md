# UI polish plan (web/)

Goal: make the ChessCoach web app look professional and be easy to understand for a first-time visitor,
without changing what the review computes. Keep the dark, Chess.com-like direction; polish it.

## Ground rules

- Only touch presentation: `web/src/App.tsx`, `web/src/components/*`, `web/src/index.css`, `web/src/lib/*`,
  `web/src/coach.ts` (wording only), `web/index.html`, `web/public/` (new assets).
- Do NOT change `web/src/review/*`, `web/src/engine/*`, `web/src/importers.ts`, model data in `web/public/data`,
  or anything outside `web/` (except `docs/` and `README.md` at the end).
- After each step: `cd web && npm run lint && npm test && npm run build` must pass.
- Match the existing code style (function components, plain CSS with tokens in `:root`, small files).
- Any third-party asset (pieces, sounds, fonts) needs a license that allows redistribution in a GPL project
  (the app ships Stockfish, GPLv3). Record source + license for each in `web/public/CREDITS.md`.
  If an asset can't be fetched or its license is unclear, skip it and use the fallback described below.
- Respect `prefers-reduced-motion` for every animation.

## Step 1: design foundation

- Define a complete token set in `index.css` `:root`: surfaces (bg, panel, raised, hover), text levels,
  accent, success/warn/danger, radii (6/10/14), spacing scale, shadows, motion durations/easing.
  Replace hard-coded colours in CSS/components with tokens.
- Font: Inter (via `@fontsource-variable/inter` or Google Fonts link) with `font-variant-numeric: tabular-nums`
  on clocks, accuracy, counts, eval text.
- Buttons: consistent primary / secondary / ghost / icon variants with hover, active, focus-visible, and a
  disabled state that looks clearly unavailable (today the disabled "Show best" looks broken).
- Pieces: add a piece-set setting (`lib/settings.ts`) with at least 2 sets from lichess `lila/public/piece`
  (e.g. cburnett, merida; both GPLv2+) as SVGs in `web/public/pieces/<set>/`, wired via react-chessboard
  `customPieces`. Default to cburnett. Keep the current default set as a fallback option.
- Coach avatar: replace the white blob with a clean SVG (e.g. a knight head) in `Coach.tsx`.
- Player avatars: coloured circle with initial (white/black piece colour), not grey boxes with "BO"/"AL".
- Motion: label badge pops in (scale 0.6 → 1, ~160ms), eval bar height/number animate (~250ms ease-out),
  move-list current cell transitions.

## Step 2: landing / import screen

- When no game is loaded, don't show an empty board with "Black/White/—". Show a hero in its place:
  title ("Free game review, right in your browser"), one-line pitch (Chess.com-style move labels, accuracy,
  game rating, retry your mistakes; nothing uploaded, runs locally), and 3 "how it works" steps
  (Pick a game → We analyze every move → Review and retry mistakes). On narrow screens stack it above the panel.
- Import panel: keep Chess.com / Lichess / Paste PGN tabs; add a **Try a sample game** button
  (bundle one short instructive PGN, e.g. the Alice vs Bob brilliant game from the docs screenshots) and
  a "Recently reviewed" list from localStorage (last 5: players, result, date; click to re-analyze).
  Wrap all localStorage in try/catch like the existing code.
- Game list items: show result as a W/L/D pill, time-control icon, opponent rating, colour played.
- Remove the stale "Can't reach the analysis server … python -m ep_model.phase_d.server" banner and the
  `serverDown` state if `health()` can no longer fail meaningfully (check `api.ts`).
- Analyzing state: progress bar with percentage, "Analyzing move X of Y", and an estimated time left
  (based on rate so far). Keep Cancel.

## Step 3: review screen layout

- Board must fit the viewport: top bar + both player bars + board fully visible at 1280×720 and up
  (today the bottom player bar is cut off). Size the board from available height and width.
- Eval bar: readable number near the side that is ahead, larger font, smooth animation.
- Graph: hover shows a tooltip (move number, SAN, label, chances %), a vertical hover line, and a
  slightly taller graph; markers stay clickable. Light axis label "50%".
- Coach bubble: clearer hierarchy (label icon + title, body, best line in mono), actions in one row.
- Panel header: replace the generic star icon; make the Chances / Engine toggle explain itself (see Step 5).
- Summary: keep "Start Review" visible at all times (sticky footer), accuracy cards side by side with
  player names, label table more compact (hide rows where both sides are 0 behind a "show all" toggle).

## Step 4: sounds

- Replace synthesized sounds in `lib/sound.ts` with recorded samples where a clearly licensed set is
  available (lichess `lila/public/sound/standard`: check its license in lila's COPYING.md; only use it if
  redistribution is allowed). Store as small .mp3/.ogg in `web/public/sounds/`, preload with Web Audio.
- Events: move, capture, check, castle, promote, game end (on reaching the final position), illegal move
  (rejected drop in retry), retry correct, retry wrong.
- Play the sound when jumping to a move by clicking (not only when stepping forward one move);
  no sound when going backward.
- Settings: volume slider (0–100) next to the on/off toggle, persisted.
- Fallback if no licensed samples: keep synthesis but make it nicer (wood-like click: short sine + filtered
  noise with a quick attack/decay; softer chimes) and add the new events.

## Step 5: make it easy to understand

- Move-label legend: a "?" button in the panel header opens a popover listing every label (icon, name,
  one plain sentence, e.g. "Mistake: loses a clear chunk of your winning chances").
- Inline info tips (click/tap, not just `title`) on: Accuracy, Game rating ("Played like a …"), Chances vs
  Engine, the phase grades. Plain-language text, one or two sentences each.
- Keyboard shortcuts popup (opened by `?` key and a small button): ← → Home End Space F.
- First-visit hint (dismissible, remembered): after the first review loads, a short 3-step tooltip tour
  (graph → move list → Retry button).
- Coach copy: review `coach.ts` strings for clarity and consistent tone; keep the numbers.

## Step 6: phone + finish

- Phone layout (≤ 640px): board full width on top, compact player bars, panel below, sticky prev/next
  controls; swipe left/right on the board to step moves (not in retry mode). No horizontal scroll at 360px.
- Light theme: `data-theme` on `<html>`, a System / Light / Dark setting, all tokens redefined.
- Accessibility: visible focus rings, aria labels on all icon buttons, colour contrast ≥ 4.5:1 for text.
- Update `index.html` meta (description, theme-color, Open Graph title/description).
- Take new screenshots (import, summary, review, retry, phone) into `docs/images/`, update README if
  it references them, and add an entry to `docs/engineering-log.md` describing the UI pass.
