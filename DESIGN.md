---
name: elo101
description: Free in-browser chess game review, laid out on a green roll-up club mat and read off a buff scoresheet.
colors:
  vinyl-green: "#13221a"
  mat-green: "#1c3627"
  mat-ink: "#d2cbb0"
  buff-paper: "#ede6cf"
  buff-paper-2: "#e3dbc0"
  buff-paper-3: "#d6cdad"
  field-cream: "#f8f4e6"
  ink: "#1b1f1a"
  ink-2: "#3b4035"
  ink-muted: "#5c6152"
  text-2-on-green: "#c9c3ab"
  muted-on-green: "#9ba48f"
  line-on-green: "rgba(237, 230, 207, .12)"
  line-strong-on-green: "rgba(237, 230, 207, .24)"
  paper-line: "rgba(27, 31, 26, .14)"
  paper-line-strong: "rgba(27, 31, 26, .3)"
  club-green: "#2f5d3a"
  club-green-hover: "#386d45"
  on-green: "#f3eedd"
  brass: "#d9a441"
  brass-hover: "#e4b55a"
  on-brass: "#1b1f1a"
  success: "#2f6b33"
  danger: "#a3332b"
  error-bg: "#f4d8cc"
  error-line: "#d59a86"
  error-text: "#8a2a1c"
  square-dark-club: "#4a7a55"
  square-highlight-light: "#f1dc86"
  square-highlight-dark: "#bfb948"
  square-select: "rgba(217, 164, 65, .7)"
  move-dot: "rgba(19, 34, 26, .38)"
  best-arrow: "rgba(226, 150, 30, .85)"
  white-piece: "#f3eedd"
  black-piece: "#0e1912"
  graph-white: "#f8f4e6"
  graph-black: "#22362a"
  graph-axis: "#7d8471"
  label-brilliant: "#1fb5a0"
  label-great: "#5d8fc4"
  label-best: "#81b64c"
  label-excellent: "#96bc4b"
  label-good: "#8fa98a"
  label-book: "#a88865"
  label-inaccuracy: "#f0b429"
  label-mistake: "#ff9550"
  label-miss: "#ec6a86"
  label-blunder: "#ff7970"
  label-ink: "#10161e"
  page-light: "#e6dfc8"
  mat-green-light: "#2a5434"
  mat-ink-light: "#dcd5bc"
  paper-light: "#fbf8ef"
  paper-2-light: "#f1ecdd"
  paper-3-light: "#e5dec8"
  field-light: "#ffffff"
  graph-black-light: "#2a3d30"
typography:
  display:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "46px"
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: "-0.035em"
  display-numeral:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "46px"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.035em"
    fontFeature: "tnum"
  headline:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  stat:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
    fontFeature: "tnum"
  coordinate:
    fontFamily: "Bricolage Grotesque, Figtree, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 800
    lineHeight: 1
  body:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.3
  label-sm:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.3
  section-label:
    fontFamily: "Figtree, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "11.5px"
    fontWeight: 800
    lineHeight: 1.5
    letterSpacing: "0.08em"
rounded:
  board: "2px"
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  pill: "99px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.brass}"
    textColor: "{colors.on-brass}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.brass-hover}"
    textColor: "{colors.on-brass}"
  button-primary-lg:
    backgroundColor: "{colors.brass}"
    textColor: "{colors.on-brass}"
    rounded: "{rounded.md}"
    padding: "13px 16px"
  button-secondary:
    backgroundColor: "{colors.buff-paper-2}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.buff-paper-3}"
    textColor: "{colors.ink}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "9px 16px"
  button-sm:
    typography: "{typography.label-sm}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  segmented-option:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.sm}"
    padding: "6px 10px"
  segmented-option-on:
    backgroundColor: "{colors.club-green}"
    textColor: "{colors.on-green}"
    rounded: "{rounded.sm}"
  segmented-track:
    backgroundColor: "{colors.buff-paper-2}"
    rounded: "{rounded.md}"
    padding: "3px"
  move-cell:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "3px 9px 3px 6px"
    height: "30px"
  move-cell-current:
    backgroundColor: "{colors.club-green}"
    textColor: "{colors.on-green}"
    rounded: "{rounded.sm}"
  field:
    backgroundColor: "{colors.field-cream}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  nav-control:
    backgroundColor: "{colors.buff-paper-2}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    height: "42px"
  nav-control-play:
    backgroundColor: "{colors.club-green}"
    textColor: "{colors.on-green}"
    rounded: "{rounded.md}"
    height: "42px"
  panel:
    backgroundColor: "{colors.buff-paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    width: "400px"
  mat:
    backgroundColor: "{colors.mat-green}"
    textColor: "{colors.mat-ink}"
    typography: "{typography.coordinate}"
    rounded: "{rounded.lg}"
    padding: "8px"
  topbar:
    backgroundColor: "{colors.vinyl-green}"
    textColor: "{colors.buff-paper}"
    height: "56px"
    padding: "0 24px"
  clock-white:
    backgroundColor: "{colors.white-piece}"
    textColor: "{colors.ink}"
    typography: "{typography.stat}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
  clock-black:
    backgroundColor: "{colors.black-piece}"
    textColor: "{colors.white-piece}"
    typography: "{typography.stat}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
  ai-tag:
    backgroundColor: "{colors.club-green}"
    textColor: "{colors.on-green}"
    rounded: "{rounded.xs}"
    padding: "1px 6px"
  error-banner:
    backgroundColor: "{colors.error-bg}"
    textColor: "{colors.error-text}"
    rounded: "{rounded.md}"
    padding: "9px 12px"
---

# Design System: elo101

## Overview

**Creative North Star: "Club Night"**

The board every club player learned on, grown into the whole app. The page is the deep vinyl green of a roll-up tournament mat; the chessboard sits on a slightly lighter green mat with bold printed a–h / 1–8 coordinates in its margin and the eval strip tucked beside the ranks. Everything you read sits on buff scoresheet paper in dark ink, ruled with hairlines like a score pad. The review is a quiet, tactile evening at the club, not a dashboard.

Density is moderate and tool-like: the board takes the left of the viewport, a single 400px paper panel holds the coach, graph, move list and controls on the right. Colour is spent sparingly and by meaning. Green marks where you are (current move, active tab, play, toggles, progress); brass marks what you can do (the one primary action in view). The Chess.com move-label colours and glyphs are inherited unchanged because players read them by habit.

The world explicitly refuses the category default of grey-dark panels with a blue accent and letter avatars. There are no decorative gradients, no glows, and no avatars; a small filled disc in the piece colour stands in for each player.

**Key Characteristics:**
- Vinyl-green ground, darker-green board mat, buff paper panels with ink text.
- Two accent roles only: green for position/state, brass for action.
- Bricolage Grotesque for headings, numerals, coordinates and clocks; Figtree for everything read or clicked.
- Hairline rules (1px, low-alpha ink or cream) separate content; no cards inside cards.
- Flat at rest: shadows only on things that float or lift (popovers, the board, square badges).
- Light and dark appearances share the same green mat and paper; only the ground and paper tint shift.

## Colors

A two-material palette (green vinyl and buff paper) with two narrow accents and a fixed, inherited set of move-label colours.

### Primary
- **Club Green** (`club-green`): "where you are." The current move pill, the active segmented option or tab, the play control, checked toggles, the progress fill, the field focus border, the AI-note tag, and focus rings on paper. Hover deepens to `club-green-hover`. Text on it is `on-green`.

### Secondary
- **Brass** (`brass`): "what you can do." Only on `btn-primary`: Retry, Continue, Find games, Review this PGN, Start Review, and Show best when the arrow is hidden. Also the page focus ring on the green ground, the tour target outline, the selected-square tint (`square-select`) and text selection. Hover lifts to `brass-hover`; text on it is `on-brass` ink.

### Tertiary
- **Move-label set** (`label-brilliant` … `label-blunder`, glyphs in `label-ink`): Brilliant teal, Great blue, Best green, Excellent, Good, Book brown, Inaccuracy amber, Mistake orange, Miss pink, Blunder red. Used for label icons in the coach title, the square badge, move list, summary table and graph markers. Identical in every appearance and board theme.

### Neutral
- **Vinyl Green** (`vinyl-green`): the page ground and top bar in the dark appearance; also the `theme-color` meta. Light appearance swaps to **Buff Ground** (`page-light`).
- **Mat Green** (`mat-green`): the margin around the board (light appearance: `mat-green-light`). Coordinates print on it in **Mat Ink** (`mat-ink` / `mat-ink-light`).
- **Buff Paper** (`buff-paper`): the panel and every popover. Two tonal steps, `buff-paper-2` (resting button, segmented track, nav controls, hover row) and `buff-paper-3` (button hover, toggle track off, spinner track). Light appearance uses the whiter `paper-light` / `paper-2-light` / `paper-3-light`.
- **Field Cream** (`field-cream`, light: `field-light`): text inputs, `kbd` keys, the toggle knob.
- **Ink** (`ink`, `ink-2`, `ink-muted`): text on paper, from heading to secondary to muted.
- **Cream text on green** (`text-2-on-green`, `muted-on-green`): pitch copy, figcaptions and player ratings on the green ground.
- **Hairlines**: `paper-line` / `paper-line-strong` on paper; `line-on-green` / `line-strong-on-green` on the ground.
- **Board and pieces**: the default Club board uses `buff-paper` light squares and `square-dark-club` dark squares; last move is tinted `square-highlight-light` / `square-highlight-dark` per square colour; the best-move arrow is `best-arrow`. `white-piece` and `black-piece` colour the side discs, clocks, eval bar and captured pieces.
- **Graph**: `graph-white` area over a `graph-black` field (light: `graph-black-light`), dashed `graph-axis` midline.
- **Status**: `success` / `danger` for win and loss pills; `error-bg`, `error-line`, `error-text` for error banners.

### Named Rules
**The Green-Is-Here, Brass-Is-Do Rule.** Green only ever marks the current position or an active state; brass only ever marks the primary action. If a control is neither, it is paper (`buff-paper-2`) or ghost.

**The One Brass Rule.** At most one brass button per view region (coach actions, import form, summary footer). Secondary actions are ghost or paper.

**The Fixed Labels Rule.** Move-label colours and glyphs are the Chess.com convention and are never re-themed, re-ordered or recoloured by appearance or board theme.

**The Paper Remap Rule.** Anything placed on a paper surface (panel, settings, info, help, tour card) inherits ink text, paper hairlines, paper hover and a green focus ring by remapping `--text`, `--muted`, `--line`, `--hover` and `--focus` on the surface. Never hand-set ink colours inside paper; join the remap list instead.

## Typography

**Display Font:** Bricolage Grotesque (opsz 12–96, weights 500–800), falling back to Figtree, system-ui
**Body Font:** Figtree (weights 400–800), falling back to -apple-system, BlinkMacSystemFont, Segoe UI

**Character:** Bricolage is the printed matter of the club: the headline, the coordinates on the mat, the clocks and the big accuracy numbers, set heavy and tight. Figtree is the handwriting on the scoresheet: friendly, legible, bold where it is a control.

### Hierarchy
- **Display** (800, 46px, 1.04, -0.035em): the start-screen headline only. Steps to 34px under 960px and 32px under 640px.
- **Display numeral** (800, 46px, 1.05, -0.035em, tabular): per-player accuracy in the summary; 38px on phones.
- **Headline** (700, 20px, 1.2): the analyzing title. The brand wordmark uses Bricolage 800 at 20px (17px on phones), -0.02em.
- **Title** (700, 19px, 1.2–1.25, -0.015em): panel title and coach heading (17px on phones); popover headings at 18px.
- **Stat** (700, 16px, 1.3, tabular): clocks, label-table counts; the game-rating values use the same face at 22px.
- **Coordinate** (Bricolage 800, 13px, 1): printed a–h / 1–8 on the mat; 10px on phones.
- **Body** (400, 15px, 1.5): base text. The start-screen pitch runs at 16px with a 48ch measure; coach body and move list at 14px.
- **Label** (700, 14px; small 13px): buttons, segmented options, settings labels, move SAN (600).
- **Section label** (800, 11.5px, 0.08em, uppercase): the heading of a data group inside the panel (Accuracy, Phase grades, Key moments, Recently reviewed). The AI-note tag uses the same idiom at 10.5px / 0.05em on green.

### Named Rules
**The Tabular Figures Rule.** Every number that changes as you step through a game (clocks, eval text, accuracy, ratings, label counts, move numbers, dates, progress) is set with tabular figures so columns never jitter.

**The Two Voices Rule.** Bricolage for things that are printed on the club equipment (headings, coordinates, clocks, big numerals); Figtree for everything you read in sentences or press. Don't set body copy or buttons in Bricolage.

**The Section Label Rule.** The uppercase tracked label is the only heading of a data group. It never sits above a display headline or a title as an eyebrow.

## Layout

A two-column operating layout: board left, paper panel right. The grid is `minmax(0, 1fr) 400px` with a 24px gap, max width 1300px, centred, 16px / 24px page padding. The board area is capped at `min(820px, 100dvh - 160px)` so the whole board always fits the viewport height. The panel is sticky at 16px and fills `100dvh - 88px`; its middle (coach, graph, move list) scrolls internally while the head and nav controls stay fixed.

Player bars sit above and below the mat, 48px tall, indented by a 52px board gutter so the name aligns with the a-file. The start screen uses a centred `560px + 400px` grid with a 72px column gap, top-aligned at `max(16px, 6dvh)`: headline, pitch and the sample's final position on the mat at left, import panel at right.

Spacing rhythm is 4 / 8 / 12 / 16 / 24px. Panel sections pad 16px and are separated by a single hairline; button groups gap 8px; nav controls gap 6px.

Responsive:
- **≤960px:** single column; the panel becomes static and grows with content; the move list caps at 260px; the start screen stacks.
- **≤640px:** board gutter 38px; the mat tightens to 4px padding, 14px coordinate tracks and an 8px radius; nav controls (and the summary's Start Review footer) pin to the bottom edge with safe-area padding; on the start screen the import panel comes first and the mat follows it at up to 300px; move cells grow to 36px targets.

## Elevation & Depth

Flat by default. Depth comes from material, not shadow: green ground, a lighter green mat, and paper panels sitting on top as a different material. The panel carries no shadow; in the light appearance it gets a 1px inset ink outline instead (`paper-line-strong`) so cream on buff still separates. Shadows appear only on things that physically lift or float.

### Shadow Vocabulary
- **Board lift** (`box-shadow: 0 2px 8px rgba(0, 0, 0, .35)`; light: `rgba(20, 35, 25, .3)`): the chessboard resting on the mat.
- **Popover** (`box-shadow: 0 14px 36px -14px rgba(0, 0, 0, .5), 0 2px 6px rgba(0, 0, 0, .16)`; light uses green-black at .35 / .1): settings, info, help and tour cards.
- **Square badge** (`filter: drop-shadow(0 1px 2px rgba(0, 0, 0, .45))`): the move-label badge on the destination square.
- **Pinned controls** (`box-shadow: 0 -6px 18px -10px rgba(0, 0, 0, .4)`): the phone's bottom nav bar only.

### Named Rules
**The Mat Is Flat Rule.** The mat and the panel never take a drop shadow. Only the board, floating popovers, the square badge and the phone's pinned controls cast one.

## Shapes

Gently rounded, three steps: 6px for small controls (segmented options, move pills, clocks, list rows), 8px for buttons, fields and nav controls, 12px for large surfaces (panel, popovers, the mat). The board itself is nearly square at 2px, and the eval bar at 3px, because they are printed objects inside the mat. Pills (99px) are reserved for the progress bar, toggles and the recent-game result chip; circles for side discs, label icons and the info trigger.

Separation is done with 1px hairlines: between panel sections, between move-list rows, between label-table rows and around the game rating. Ghost buttons and icon buttons use a 1px `line-strong` outline; `kbd` keys add a 2px bottom border.

## Components

### Buttons
Tactile and plain: solid fills, no gradients, a 1px press-down on `:active`.
- **Shape:** gently curved (8px).
- **Primary (brass):** `brass` fill, `on-brass` ink, 700 14px, 9px × 16px. Sizes: small 6px × 12px at 13px; large 13px × 16px at 16px (summary Start Review); block fills its row.
- **Secondary (paper):** `buff-paper-2` fill, ink text; hover to `buff-paper-3`.
- **Ghost:** transparent with a 1px `line-strong` outline; hover fills `hover`. Used for New game, Next mistake, Summary, Skip tour, Show all labels.
- **Hover / Focus:** 160ms background transition; focus is a 3px solid ring offset 2px (brass on the green ground, green on paper and in the light appearance). Disabled drops to 45% opacity.
- **Icon button:** 36px square, 8px radius, 1px `line-strong` outline, transparent; hover or expanded fills `hover`.

### Segmented control / tabs
- **Style:** a `buff-paper-2` track (8px radius, 3px inset) holding equal-width options in `ink-muted` 700 13px.
- **State:** the selected option fills `club-green` with `on-green` text (Chances / Engine; Chess.com / Lichess / Paste PGN). Hover on an unselected option darkens text only.

### Cards / Containers (the paper panel)
- **Corner Style:** 12px.
- **Background:** `buff-paper` (light: `paper-light`).
- **Shadow Strategy:** none (see Elevation); light appearance adds a 1px inset ink outline.
- **Border:** none; sections divide with hairlines.
- **Internal Padding:** 16px; head 14px / 16px / 12px.
- Popovers (settings, info, help, tour) are the same paper with 12px radius, 16–18px padding and the popover shadow.

### Inputs / Fields
- **Style:** `field-cream` fill, 1px `line-strong` stroke, 8px radius, 10px × 12px, body type; PGN textarea in the system monospace at 12.5px.
- **Focus:** border turns `club-green` with a 3px green ring at 22% (`color-mix`).
- **Error:** a banner, not a field state: `error-bg` fill, `error-line` border, `error-text` copy, 8px radius.

### Navigation
- **Top bar:** 56px, ground colour, hairline below; brand mark (knight favicon + Bricolage wordmark) at left, ghost New game and icon buttons at right.
- **Nav controls:** a row of six `buff-paper-2` buttons, 42px tall, 8px radius, 20px SVG icons in `ink-2`; hover `buff-paper-3`; the play button is `club-green`; flip is narrower (0.6 share). Pinned to the bottom on phones.

### Move list
- **Rows:** grid of number (40px, muted tabular) + two move cells, divided by hairlines.
- **Cell:** 30px tall, 6px radius, label icon + SAN at 600; hover `buff-paper-2`; the current move is a `club-green` pill with `on-green` text.

### The Mat (signature)
The board's frame and the system's signature. A `mat-green` grid, 8px padding and 12px radius, with 20px tracks on all four sides printing a–h and 1–8 in Bricolage 800 13px `mat-ink`; files and ranks reverse when the board flips. In review, a 24px track to the left of the ranks holds the eval bar (`black-piece` field, `white-piece` fill rising from the bottom, 3px radius, 800 10px tabular score at the winning end). The board inside sits at 2px radius with the board-lift shadow. The same mat frames the start screen's sample position.

### Player bar and clocks
48px row: a 12px side disc in the piece colour, bold name with muted tabular rating, captured pieces beneath with a muted `+N` material lead, and a clock at the far right. The clock is a 6px-radius chip in the player's piece colour (`white-piece` with ink, or `black-piece` with cream), Bricolage 700 16px tabular.

### Label icon and square badge
A filled circle in the label colour with the label glyph in `label-ink` at ~55% of the diameter, 900 weight. On the board it sits at the destination square's top-right corner at 26px with a 2px `on-green` cream ring and the badge drop shadow, popping in with a 260ms scale. Glyphs (!!, !, ★, +, ✓, B, ?!, ?, ✕, ??) are part of the binding Chess.com convention.

### Coach block
Title row (label icon 22px + Bricolage 19px heading), 14px body in `ink-2`, optional muted eval and best-line rows separated by a hairline, an optional AI note marked with the green uppercase tag, then the action row (one brass Retry + ghost Next mistake).

### Advantage graph
104px tall, 6px radius: `graph-white` area for White over a `graph-black` field, dashed midline, label-coloured markers (4.5px) for Brilliant, Great and the four bad labels, a dashed green hover cursor and an ink tooltip with paper text.

### Motion
Short and functional: 160ms for hover/background/colour, 260ms with `cubic-bezier(.22, 1, .36, 1)` for the eval fill, progress, toggle knob and badge pop. A 0.9s linear spinner and a 1.3s skeleton shimmer cover loading. `prefers-reduced-motion` turns every animation and transition off.

## Do's and Don'ts

### Do:
- **Do** keep the board on the mat at the left and the single 400px paper panel at the right; on phones the board comes first in review and the import panel comes first on the start screen.
- **Do** use `club-green` for the current move, the active option, play and checked toggles, and nothing else.
- **Do** spend brass on one primary action per region (Retry, Find games, Start Review).
- **Do** separate panel content with 1px hairlines (`paper-line`) instead of nested cards.
- **Do** set every changing number with tabular figures.
- **Do** put new floating paper surfaces on the paper remap list so they inherit ink text and the green focus ring.
- **Do** keep move-label colours and glyphs exactly as the Chess.com convention defines them.
- **Do** offer the other board themes (Green, Walnut, Slate, Ice) and both appearances as user choices; Club is the default board.

### Don't:
- **Don't** fall back to grey-dark panels with a blue accent, or letter avatars; a side disc in the piece colour identifies each player.
- **Don't** add decorative gradients or glows. The only gradients in the system are functional: the skeleton shimmer and the radial legal-move dots on the board.
- **Don't** give the mat or the panel a drop shadow; shadows belong to the board, popovers, the square badge and the phone's pinned controls.
- **Don't** use brass for selection or "current" state, or green for a call to action.
- **Don't** set buttons or body copy in Bricolage Grotesque.
- **Don't** stack an uppercase section label above a headline as an eyebrow.
