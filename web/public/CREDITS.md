# UI assets

- **Inter** — Copyright © 2016 The Inter Project Authors, SIL Open Font License 1.1.
  Source: https://github.com/rsms/inter; license: https://github.com/rsms/inter/blob/master/LICENSE.txt.
  Loaded through Google Fonts with `display=swap`; system fonts are used if offline or blocked.
  No font binary is redistributed in this repository. OFL permits bundling with GPL software.
- **Coach knight icon** — original SVG created for elo101, distributed under the project's license.
- **Chess pieces** — the existing react-chessboard built-in pieces remain in use.
  No new third-party piece asset is included. Cburnett (Colin M. L. Burnett) and Merida
  (Armando Hernandez Marroquin) were checked as GPLv2-or-later in
  https://github.com/lichess-org/lila/blob/master/COPYING.md, but downloads failed
  because `raw.githubusercontent.com` could not be resolved in the build environment.
  The plan's built-in-piece fallback is used; unavailable sets are not offered as broken choices.

- **Sounds** — original Web Audio synthesis in `src/lib/sound.ts`, distributed under the project's license.
  No recorded sound is included. The standard Lichess sounds were not used: Lila's COPYING.md
  lists “the other sounds in public/sound” under non-free exceptions, with no clear standard-set
  redistribution grant. The plan's synthesis fallback supplies all nine UI events.
- **Sample game** — original PGN headers for Alice/Bob over the public-domain Legál mating pattern.
  No third-party annotations, prose, or database extract is included.
