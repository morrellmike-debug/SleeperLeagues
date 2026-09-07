"""Real auction-dollar valuation, computed from Sleeper's own season point
projections scored under the LEAGUE'S ACTUAL scoring_settings - not generic
PPR. This matters most for IDP: Sleeper's in-app PROJ/PTS columns use a
generic scoring profile (confirmed by cross-checking a real screenshot
against this same projections payload), which can diverge a lot from a
custom IDP league's real scoring.

Two things worth knowing about the projections payload
(api.sleeper.app/projections/nfl/{season}) before trusting numbers from it:

1. It's ~9MB across ~9400 entries (every rostered-or-relevant NFL player,
   not just this league's pool) - cached to disk like players.json.
2. IDP tackle scoring has a redundancy trap: a league's scoring_settings
   can carry BOTH "idp_tkl" (total tackles) AND "idp_tkl_solo" /
   "idp_tkl_ast" (the same tackles split out). Applying all three would
   double-count. This module skips "idp_tkl" and scores off solo+assist
   only - the standard convention - and flags this choice explicitly
   rather than silently guessing.
"""

import json
import os
import time

import requests

from config import CACHE_DIR

PROJECTIONS_CACHE_PATH = f"{CACHE_DIR}/sleeper_projections.json"
PROJECTIONS_CACHE_MAX_AGE_HOURS = 24

# Scoring keys that exist in league scoring_settings but apply only to a
# team DEF/ST roster slot, not individual IDP players - safe to include in
# the dot product (an IDP player's stat dict never has these keys) but
# listed here for clarity on what's deliberately NOT being interpreted as
# individual-player scoring.
TEAM_DEF_ST_KEYS = {
    "sack", "safe", "blk_kick", "ff", "fum_rec", "def_td",
    "def_st_ff", "def_st_fum_rec", "def_st_td", "st_ff", "st_fum_rec", "st_td",
}

# Skip this key when dotting stats against scoring_settings: it's the sum
# of idp_tkl_solo + idp_tkl_ast, so scoring it too would double-count.
SKIP_SCORING_KEYS = {"idp_tkl"}


def fetch_projections(season: int, force_refresh: bool = False) -> dict[str, dict]:
    """Returns sleeper_id -> stats dict (raw per-category season projection)."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_refresh and os.path.exists(PROJECTIONS_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(PROJECTIONS_CACHE_PATH)) / 3600
        if age_hours < PROJECTIONS_CACHE_MAX_AGE_HOURS:
            with open(PROJECTIONS_CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
                if cached:
                    return cached

    print("Fetching Sleeper season projections (~9MB, one-time/daily cost)...")
    resp = requests.get(
        f"https://api.sleeper.app/projections/nfl/{season}",
        params={"season_type": "regular"},
        timeout=60,
    )
    resp.raise_for_status()
    entries = resp.json()

    by_sleeper_id: dict[str, dict] = {}
    for entry in entries:
        player = entry.get("player") or {}
        sid = player.get("player_id") or entry.get("player_id")
        stats = entry.get("stats") or {}
        if sid and stats:
            by_sleeper_id[str(sid)] = stats

    with open(PROJECTIONS_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(by_sleeper_id, f)
    return by_sleeper_id


def score_projection(stats: dict, scoring_settings: dict) -> float:
    """Dot product of a player's projected stat categories against the
    league's actual scoring_settings, skipping the double-counting trap
    (see module docstring).
    """
    total = 0.0
    for stat_key, stat_value in stats.items():
        if stat_key in SKIP_SCORING_KEYS:
            continue
        weight = scoring_settings.get(stat_key)
        if weight:
            total += stat_value * weight
    return round(total, 1)


def compute_pool_projections(pool_player_ids: list[str], scoring_settings: dict, season: int) -> dict[str, float]:
    """Returns sleeper_id -> projected season points under this league's
    real scoring, for whichever of the given player_ids have a projection.
    IDs with no projection entry (deep bench / practice squad types) are
    simply absent from the result - callers should treat missing as
    unknown, not zero.
    """
    projections = fetch_projections(season)
    result = {}
    for pid in pool_player_ids:
        stats = projections.get(pid)
        if stats:
            result[pid] = score_projection(stats, scoring_settings)
    return result
