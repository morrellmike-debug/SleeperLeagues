"""FantasyPros API integration - fills the IDP valuation gap DynastyProcess
leaves (it only covers offensive skill positions QB/RB/WR/TE).

Requires a FANTASYPROS_API_KEY, either in the environment or in a local
.env file (KEY=VALUE, gitignored - never commit this). Endpoint requires
premium API access: https://api.fantasypros.com/public/v2/json/nfl/{year}/
consensus-rankings?type=ROS&position=IDP&scoring=STD - note the required
"public" path segment, easy to miss (the same URL without it 403s).

FantasyPros' player_id uses the same numbering as DynastyProcess's fp_id,
so results are joined to sleeper_id through the same crosswalk file
(player_ids.py) rather than a second lookup table.
"""

import json
import os
import time

import requests

from config import (
    CACHE_DIR,
    FANTASYPROS_BASE_URL,
    FANTASYPROS_CACHE_MAX_AGE_HOURS,
    FANTASYPROS_IDP_CACHE_PATH,
    NFL_SEASON,
)
from player_ids import fetch_fp_id_to_sleeper_id


def _load_api_key() -> str | None:
    key = os.environ.get("FANTASYPROS_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("FANTASYPROS_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return None


def fetch_idp_rankings(force_refresh: bool = False) -> tuple[dict[str, dict], bool]:
    """Returns (sleeper_id -> {rank_ecr, tier, pos_rank}, is_real_data)."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_refresh and os.path.exists(FANTASYPROS_IDP_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(FANTASYPROS_IDP_CACHE_PATH)) / 3600
        if age_hours < FANTASYPROS_CACHE_MAX_AGE_HOURS:
            with open(FANTASYPROS_IDP_CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
                if cached:
                    return cached, True

    key = _load_api_key()
    if not key:
        print("NOTE: FANTASYPROS_API_KEY not set - IDP players will use position/status tiering instead.")
        return {}, False

    try:
        resp = requests.get(
            f"{FANTASYPROS_BASE_URL}/nfl/{NFL_SEASON}/consensus-rankings",
            params={"type": "ROS", "position": "IDP", "scoring": "STD"},
            headers={"x-api-key": key},
            timeout=30,
        )
        resp.raise_for_status()
        players = resp.json().get("players", [])

        fp_to_sleeper = fetch_fp_id_to_sleeper_id()
        if not fp_to_sleeper:
            print("WARNING: id crosswalk unavailable, can't map FantasyPros IDP rankings to sleeper_id.")
            return {}, False

        result: dict[str, dict] = {}
        for p in players:
            sid = fp_to_sleeper.get(str(p.get("player_id")))
            if not sid:
                continue
            result[sid] = {
                "rank_ecr": p.get("rank_ecr"),
                "tier": p.get("tier"),
                "pos_rank": p.get("pos_rank"),
            }

        if not result:
            print("WARNING: FantasyPros IDP rankings fetched but none matched a sleeper_id. Falling back to tiering.")
            return {}, False

        with open(FANTASYPROS_IDP_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f)
        print(f"FantasyPros IDP rankings: {len(result)} players matched to sleeper_id.")
        return result, True

    except Exception as exc:
        print(f"WARNING: FantasyPros IDP fetch failed ({exc}). Falling back to tiering.")
        return {}, False
