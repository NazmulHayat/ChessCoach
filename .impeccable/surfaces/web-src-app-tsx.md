---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: ["web/src/index.css"]
---

# Surface: elo101 app (import, analyzing, summary, review)

Mode: Operate. Primary user: club/online player (800–1800) reviewing their own game on a laptop right after playing; task is find the turning points and retry mistakes. Constraints: Chess.com move-label colours/icons and board-left/panel-right layout are binding; light/dark appearance and board themes stay user-switchable (Club Night is the default).

## Direction contract

THESIS: The board every club player learned on, grown into the whole app: the review happens on a green roll-up mat, read off a buff scoresheet. Refuses the category default of grey-dark panels with a blue accent and letter avatars.

OWN-WORLD: Deep vinyl-green ground (#13221A), a darker green mat (#1B3325) framing the board with bold printed a–h / 1–8 coordinates and the eval bar in its margin, buff paper panels (#EDE6CF) with ink text, brass (#D9A441) only on primary actions, green (#2F5D3A) for "where you are" (current move, active tab/toggle). Bricolage Grotesque for display, Figtree for UI, tabular figures. Ruled lines, no glow, no gradients, no avatars.

STORY: The player sees their game on the familiar board, reads the coach line, sees where the chances swung, and retries a mistake.

FIRST VIEWPORT: Slim green top bar (brand, New game, shortcuts, settings). Left: player bar, board on the mat with coordinates and eval strip, player bar. Right (~400px): buff panel — title + Chances/Engine toggle, coach block (label + heading + body + Retry/Next mistake), graph, move list with green current pill, nav controls, Summary / Show best. Start screen: headline and the sample game's final position (Légal's mate, 7.Nd5#) on the mat at left, import panel right, top-aligned; on phones the mat follows the import panel.

FORM: Club Night (green-and-buff vinyl club board), grounded candidate 1 of 7 (pick card); seed:cf040af4a3d34d53

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
