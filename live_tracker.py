#!/usr/bin/env python3
"""Phase 2: live draft tracker.

Usage:
    python live_tracker.py [--league wcv] [--out board.html] [--interval 15]

Polls the draft's picks feed, tracks running budget/pool state, regenerates
board.html every cycle, and logs new picks to the terminal as a second-
screen glance even without the browser open.

Handles two pick formats, branched on config.py's LeagueConfig.format:
  - "auction" (e.g. WCV): price comes from pick["metadata"]["amount"].
    If Sleeper ever renames this field, extract_price() below is the only
    place that needs updating - inspect a real pick's metadata dict to find
    the new key.
  - "snake" (e.g. Reg Cool Kids, Chopped Cool Kids): no price, just
    pick_no/roster_id/player_id/round.
"""

import argparse
import sys
import time
from datetime import datetime

import sleeper_api
from board_data import build_board_data
from config import LEAGUES, LeagueConfig
from html_render import to_json_payload, write_board_html


def extract_price(pick: dict, cfg: LeagueConfig) -> int | None:
    if cfg.format != "auction":
        return None
    metadata = pick.get("metadata") or {}
    amount = metadata.get("amount")
    if amount is None:
        return None
    try:
        return int(amount)
    except (TypeError, ValueError):
        return None


def build_live_state(cfg: LeagueConfig, picks: list[dict], teams: dict, player_name_fn) -> dict:
    budget = cfg.budget
    spent: dict[int, int] = {}
    players_won: dict[int, list[dict]] = {}
    drafted_player_ids: set[str] = set()
    log_entries: list[dict] = []

    for pick in sorted(picks, key=lambda p: p.get("pick_no", 0)):
        pid = pick.get("player_id")
        roster_id = pick.get("roster_id")
        pick_no = pick.get("pick_no")
        if pid is None or roster_id is None:
            continue

        drafted_player_ids.add(pid)
        price = extract_price(pick, cfg)
        player_name = player_name_fn(pid)
        team_name = teams[roster_id].team_name if roster_id in teams else f"Roster {roster_id}"

        if price is not None:
            spent[roster_id] = spent.get(roster_id, 0) + price
            players_won.setdefault(roster_id, []).append({"name": player_name, "price": price})
            line = f"Team {team_name} won {player_name} for ${price} (pick {pick_no})"
        else:
            players_won.setdefault(roster_id, []).append({"name": player_name, "price": 0})
            line = f"Team {team_name} selected {player_name} (pick {pick_no})"

        log_entries.append({"pick_no": pick_no, "line": line})

    team_rows = []
    for rid, info in teams.items():
        s = spent.get(rid, 0)
        team_rows.append({
            "team_name": info.team_name,
            "spent": s,
            "remaining": (budget - s) if budget else None,
            "players_won": players_won.get(rid, []),
        })
    team_rows.sort(key=lambda r: r["team_name"])

    return {
        "teams": team_rows,
        "picks_log": [e["line"] for e in log_entries],
        "log_entries": log_entries,  # structured, for terminal dedup only
        "drafted_player_ids": drafted_player_ids,
        "last_updated": datetime.now().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="wcv", choices=list(LEAGUES.keys()))
    parser.add_argument("--out", default="board.html")
    parser.add_argument("--interval", type=int, default=15, help="poll interval in seconds (15-20 recommended)")
    args = parser.parse_args()

    cfg = LEAGUES[args.league]
    if not cfg.draft_id:
        print(f"League '{cfg.key}' has no draft_id configured yet.", file=sys.stderr)
        return 1

    print(f"Building initial board for {cfg.name}...")
    data = build_board_data(cfg)
    players_raw = sleeper_api.get_players()  # cache already warm from build_board_data

    def player_name(pid: str) -> str:
        return sleeper_api.player_lookup(pid, players_raw)["name"]

    printed_pick_nos: set[int] = set()
    full_pool = list(data.pool)  # keep the original pool; Pool tab shows what's left each cycle
    print(f"Polling picks every {args.interval}s. Ctrl+C to stop.\n")

    try:
        while True:
            try:
                picks = sleeper_api.get_picks(cfg.draft_id)
            except Exception as exc:
                print(f"[warn] poll failed: {exc}")
                time.sleep(args.interval)
                continue

            live = build_live_state(cfg, picks, data.current_teams, player_name)

            for entry in live["log_entries"]:
                if entry["pick_no"] not in printed_pick_nos:
                    print(entry["line"])
                    printed_pick_nos.add(entry["pick_no"])

            data.pool = [p for p in full_pool if p["player_id"] not in live["drafted_player_ids"]]

            payload = to_json_payload(data, cfg, live_state=live)
            write_board_html(payload, args.out)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
