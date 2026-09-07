# SleeperLeagues

Dashboard + live tracker for Sleeper fantasy drafts, built directly against
the public Sleeper API. First use case: the West Coast Villians (WCV) 8-team
contraction dispersal auction.

## Why this runs locally

This repo was built in a sandboxed Claude Code environment whose network
egress policy blocks `api.sleeper.app`. The scripts are unaffected by that -
they're meant to be run on your own machine (or any environment with normal
internet access), where the Sleeper API is directly reachable with no auth.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

To enable real IDP rankings (DL/LB/DB - DynastyProcess only covers offense),
add your FantasyPros API key to a `.env` file in the repo root (gitignored,
never commit it):

```
FANTASYPROS_API_KEY=your-key-here
```

Requires a FantasyPros plan with API access (`api.fantasypros.com`). Without
a key, IDP/K players just fall back to the position/status tiering, flagged
as approximate in the UI - everything else still works.

## Phase 1 - build the pre-draft board

```bash
python build_board.py --league wcv
```

This:

1. Fetches the current 16-team league's rosters/users.
2. Fetches the prior 24-team league and diffs owner sets to find the 8
   departed teams (including any orphaned/abandoned rosters with
   `owner_id: null`).
3. Unions those rosters' players into the dispersal pool.
4. Fetches `players.json` (cached to disk under `cache/`, refreshed only if
   >24h old - it's a large payload and doesn't change intraday).
5. Fetches dynasty trade values from DynastyProcess's public CSV to rank
   offensive players (QB/RB/WR/TE) in the pool and your roster, and IDP
   (DL/LB/DB) consensus rankings from the FantasyPros API to cover the
   ~half of the dispersal pool DynastyProcess doesn't price. If either
   source is unreachable, that slice falls back to a simple position +
   status tiering and flags the ranking as approximate directly in the UI
   (Pool tab banner).
6. Computes your position counts vs. the league's position limits. Sleeper
   doesn't expose a "max players per position" field in its public API, so
   this uses the limits from the spec (`QB:3, RB:6, WR:7, TE:3, K:1, DL:4,
   LB:4, DB:4`) as a flagged assumption unless it finds explicit
   `position_limit_*` fields in `league.settings`. **Confirm these against
   your commissioner's actual rules before trusting the caps in the UI.**
7. Ranks your rostered players lowest-value-first as cut candidates (you
   have 0 open bench slots, 2 open taxi slots).
8. Writes `board.html` - open it directly in a browser, no server needed.

Useful flags:

```bash
python build_board.py --league wcv --refresh-players   # force players.json refetch
python build_board.py --league wcv --refresh-values    # force dynasty value refetch
python build_board.py --league wcv --out my_board.html
```

## Phase 2 - live tracker (draft day)

```bash
python live_tracker.py --league wcv --interval 15
```

Polls the draft's picks feed every `--interval` seconds, tracks each team's
remaining auction budget (`$329 - sum of winning bids`) and removes drafted
players from the pool, regenerates `board.html` in place each cycle, and
prints a scrolling log to the terminal (`Team X won Player Y for $Z (pick
N)`) as a second-screen glance even with the browser closed.

If Sleeper ever renames the auction price field
(`pick["metadata"]["amount"]`), inspect a real pick from a live draft and
update `extract_price()` in `live_tracker.py` - that's the only place it's
read from.

## Adding another league

Both scripts are parameterized by league key (`config.py`). Snake drafts
(no auction price, just `pick_no`/`roster_id`/`player_id`) are already
handled by `live_tracker.py` - it branches on `LeagueConfig.format`. To wire
up **Reg Cool Kids** or **Chopped Cool Kids**, fill in their `draft_id` in
`config.py` once Sleeper creates it, then run:

```bash
python build_board.py --league reg_cool_kids
python live_tracker.py --league reg_cool_kids
```

Note: the dispersal-pool diffing (departed-team logic, `prior_league_id`) is
WCV-specific to its one-time contraction event. It's skipped automatically
for leagues with no `prior_league_id` configured - `build_board.py` still
produces the My Roster tab, just with an empty Pool tab.

## Known gotchas (from the build)

- `settings.draft_rounds` on the league object is not meaningful for an
  auction - don't use it to estimate draft length.
- `players.json`'s `team` (current NFL team) field is sometimes stale; name
  and position are reliable, team less so.
- Some legacy/edge-case player IDs don't resolve in `players.json` at all -
  the UI shows `(unresolved id)` next to those rather than crashing.
- IDP players are often multi-eligible (`fantasy_positions: ["DL","LB"]`)
  even though `position` shows one primary value - roster-fit checks use
  `fantasy_positions`, not `position` alone.

## Files

| File | Purpose |
|---|---|
| `config.py` | League IDs, budget, format, position-limit fallbacks |
| `sleeper_api.py` | Sleeper API client + `players.json` disk cache |
| `player_ids.py` | Shared FantasyPros-id \<-\> sleeper-id crosswalk (DynastyProcess's `db_playerids.csv`) |
| `dynasty_values.py` | DynastyProcess CSV fetch/parse (offense values) + fallback tiering |
| `fantasypros.py` | FantasyPros API - IDP (DL/LB/DB) consensus rankings |
| `board_data.py` | Pool diffing, roster analysis, cut candidates, three-tier value ranking |
| `html_render.py` | Renders the self-contained `board.html` |
| `build_board.py` | Phase 1 CLI |
| `live_tracker.py` | Phase 2 CLI |
