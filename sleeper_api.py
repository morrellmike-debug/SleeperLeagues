"""Thin wrapper around the public Sleeper API, plus the on-disk players.json
cache. No auth needed for any of this - all public endpoints.
"""

import json
import os
import time
from typing import Any

import requests

from config import (
    CACHE_DIR,
    PLAYERS_CACHE_MAX_AGE_HOURS,
    PLAYERS_CACHE_PATH,
)

BASE_URL = "https://api.sleeper.app/v1"
_session = requests.Session()


def _get(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    resp = _session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_league(league_id: str) -> dict:
    return _get(f"/league/{league_id}")


def get_rosters(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/rosters") or []


def get_users(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/users") or []


def get_drafts(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/drafts") or []


def get_picks(draft_id: str) -> list[dict]:
    return _get(f"/draft/{draft_id}/picks") or []


def get_traded_picks(draft_id: str) -> list[dict]:
    return _get(f"/draft/{draft_id}/traded_picks") or []


def get_players(force_refresh: bool = False) -> dict[str, dict]:
    """Fetch the full NFL player dict, cached to disk for up to 24h.

    This payload is ~5-10MB, and doesn't change intraday, so we only hit
    the network when the cache is missing or stale.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_refresh and os.path.exists(PLAYERS_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(PLAYERS_CACHE_PATH)) / 3600
        if age_hours < PLAYERS_CACHE_MAX_AGE_HOURS:
            with open(PLAYERS_CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)

    print("Fetching players.json from Sleeper (large payload, one-time/daily cost)...")
    players = _get("/players/nfl")
    with open(PLAYERS_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f)
    return players


def player_lookup(player_id: str, players: dict[str, dict]) -> dict:
    """Resolve a player_id to a display-friendly dict, tolerating IDs that
    don't exist in players.json (some legacy/edge-case IDs don't resolve).
    """
    p = players.get(player_id)
    if p is None:
        return {
            "player_id": player_id,
            "name": f"Unknown Player ({player_id})",
            "position": None,
            "fantasy_positions": [],
            "team": None,
            "status": None,
            "age": None,
            "unresolved": True,
        }
    full_name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    return {
        "player_id": player_id,
        "name": full_name or f"Unknown Player ({player_id})",
        "position": p.get("position"),
        "fantasy_positions": p.get("fantasy_positions") or ([p["position"]] if p.get("position") else []),
        "team": p.get("team"),
        "status": p.get("status"),
        "age": p.get("age"),
        "unresolved": False,
    }
