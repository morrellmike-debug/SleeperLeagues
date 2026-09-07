"""Shared FantasyPros-id -> sleeper-id crosswalk, sourced from
DynastyProcess's db_playerids.csv. Used by both dynasty_values.py (to key
values-players.csv by sleeper_id) and fantasypros.py (to key the live
FantasyPros API's IDP rankings by sleeper_id), so it's fetched/cached once
here instead of twice.
"""

import csv
import io
import json
import os
import time

import requests

from config import (
    CACHE_DIR,
    DYNASTY_PROCESS_PLAYERIDS_URL,
    PLAYERIDS_CACHE_MAX_AGE_HOURS,
    PLAYERIDS_CACHE_PATH,
)


def fetch_fp_id_to_sleeper_id(force_refresh: bool = False) -> dict[str, str]:
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_refresh and os.path.exists(PLAYERIDS_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(PLAYERIDS_CACHE_PATH)) / 3600
        if age_hours < PLAYERIDS_CACHE_MAX_AGE_HOURS:
            with open(PLAYERIDS_CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
                if cached:
                    return cached

    try:
        resp = requests.get(DYNASTY_PROCESS_PLAYERIDS_URL, timeout=30)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        mapping: dict[str, str] = {}
        for row in reader:
            fpid = (row.get("fantasypros_id") or "").strip()
            sid = (row.get("sleeper_id") or "").strip()
            if fpid and sid and fpid.upper() != "NA" and sid.upper() != "NA":
                mapping[fpid] = sid

        if not mapping:
            print("WARNING: db_playerids.csv parsed but yielded no fantasypros_id -> sleeper_id rows.")
            return {}

        with open(PLAYERIDS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(mapping, f)
        return mapping

    except Exception as exc:
        print(f"WARNING: player id crosswalk fetch failed ({exc}).")
        return {}
