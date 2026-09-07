#!/usr/bin/env python3
"""Phase 1: build the pre-draft board.

Usage:
    python build_board.py [--league wcv] [--out board.html] [--refresh-players] [--refresh-values]

Requires real network access to api.sleeper.app (and github.com for the
dynasty value CSV) - run this locally, not from a sandboxed environment
with restricted egress.
"""

import argparse
import sys

from board_data import build_board_data
from config import LEAGUES
from html_render import to_json_payload, write_board_html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="wcv", choices=list(LEAGUES.keys()))
    parser.add_argument("--out", default="board.html")
    parser.add_argument("--refresh-players", action="store_true", help="force-refetch players.json even if cache is fresh")
    parser.add_argument("--refresh-values", action="store_true", help="force-refetch dynasty values even if cache is fresh")
    args = parser.parse_args()

    cfg = LEAGUES[args.league]
    if not cfg.league_id:
        print(f"League '{cfg.key}' has no league_id configured yet.", file=sys.stderr)
        return 1

    if args.refresh_players:
        import sleeper_api
        sleeper_api.get_players(force_refresh=True)
    if args.refresh_values:
        import dynasty_values
        dynasty_values.fetch_dynasty_values(force_refresh=True)

    data = build_board_data(cfg)
    payload = to_json_payload(data, cfg)
    write_board_html(payload, args.out)

    print("\n--- Summary ---")
    print(f"League: {data.league.get('name')}")
    print(f"Dispersal pool: {len(data.pool)} players")
    print(f"My team: {payload['my_team_name']}")
    print(f"Position counts vs limits ({data.position_limits_source}):")
    for pos in sorted(set(list(data.position_counts) + list(data.position_limits))):
        count = data.position_counts.get(pos, 0)
        limit = data.position_limits.get(pos)
        flag = " <- AT/OVER CAP" if limit is not None and count >= limit else ""
        print(f"  {pos:>3}: {count}{'/' + str(limit) if limit is not None else ''}{flag}")
    if data.cut_candidates:
        print("Top 5 cut candidates:")
        for p in data.cut_candidates[:5]:
            if p.get("dynasty_value") is not None:
                value_str = f"${round(p['dynasty_value']):,}"
            elif p.get("fp_idp_rank") is not None:
                value_str = f"IDP ECR #{p['fp_idp_rank']} (Tier {p.get('fp_idp_tier')})"
            else:
                value_str = "no ranking data (tiering fallback)"
            print(f"  {p['name']} ({p.get('position')}) - {value_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
