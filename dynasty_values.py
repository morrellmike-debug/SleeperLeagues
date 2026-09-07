"""Dynasty trade-value data, used to rank the dispersal pool and my roster.

Primary source: DynastyProcess's public values-players.csv on GitHub, which
is keyed (among other columns) by sleeper_id and updated regularly. Column
names have shifted before, so we match by substring rather than an exact
header, and cache the parsed result to disk for a day.

If the fetch or parse fails for any reason (network, schema change, empty
response), we fall back to a simple tier-by-position+status ranking and
the caller is expected to flag that the ranking is approximate.
"""

import csv
import io
import json
import os
import time

import requests

from config import (
    CACHE_DIR,
    DYNASTY_PROCESS_VALUES_URL,
    DYNASTY_VALUES_CACHE_MAX_AGE_HOURS,
    DYNASTY_VALUES_CACHE_PATH,
)


def _find_column(fieldnames: list[str], *substrings: str) -> str | None:
    for name in fieldnames:
        lower = name.lower()
        if all(s in lower for s in substrings):
            return name
    return None


def fetch_dynasty_values(force_refresh: bool = False) -> tuple[dict[str, float], bool]:
    """Returns (sleeper_id -> value dict, is_real_data).

    is_real_data is False when we fell back to an empty dict, signaling the
    caller should use the approximate tiering fallback instead.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_refresh and os.path.exists(DYNASTY_VALUES_CACHE_PATH):
        age_hours = (time.time() - os.path.getmtime(DYNASTY_VALUES_CACHE_PATH)) / 3600
        if age_hours < DYNASTY_VALUES_CACHE_MAX_AGE_HOURS:
            with open(DYNASTY_VALUES_CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
                if cached:
                    return cached, True

    try:
        resp = requests.get(DYNASTY_PROCESS_VALUES_URL, timeout=30)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        fieldnames = reader.fieldnames or []

        id_col = _find_column(fieldnames, "sleeper", "id")
        # Prefer a 1QB superflex-agnostic overall value column; fall back to
        # whatever "value" column exists.
        value_col = (
            _find_column(fieldnames, "value_1qb")
            or _find_column(fieldnames, "value_2qb")
            or _find_column(fieldnames, "value")
        )

        if not id_col or not value_col:
            print(
                f"WARNING: could not find expected columns in DynastyProcess CSV "
                f"(saw: {fieldnames}). Falling back to tiering."
            )
            return {}, False

        values: dict[str, float] = {}
        for row in reader:
            sid = (row.get(id_col) or "").strip()
            raw_val = (row.get(value_col) or "").strip()
            if not sid or not raw_val:
                continue
            try:
                values[sid] = float(raw_val)
            except ValueError:
                continue

        if not values:
            print("WARNING: DynastyProcess CSV parsed but yielded no usable rows. Falling back to tiering.")
            return {}, False

        with open(DYNASTY_VALUES_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(values, f)
        return values, True

    except Exception as exc:  # network error, bad CSV, etc - never crash the board build
        print(f"WARNING: dynasty value fetch failed ({exc}). Falling back to tiering.")
        return {}, False


# --- Fallback tiering, used when real dynasty values aren't available ---

_STATUS_RANK = {
    "Active": 0,
    "Injured Reserve": 1,
    "PUP": 1,
    "Physically Unable to Perform": 1,
    "Sus": 2,
    "Suspended": 2,
    "NA": 3,
    "Inactive": 3,
    None: 4,
}

_POSITION_RANK = {
    "QB": 0, "RB": 1, "WR": 1, "TE": 2,
    "DL": 3, "LB": 3, "DB": 3,
    "K": 5,
}


def fallback_tier_score(position: str | None, status: str | None) -> float:
    """Lower is better - a rough, explicitly-approximate stand-in for a real
    dynasty value when no external source is reachable. Active > Inactive,
    then a coarse offense/IDP/kicker split.
    """
    pos_rank = _POSITION_RANK.get(position, 4)
    status_rank = _STATUS_RANK.get(status, 4)
    return pos_rank * 10 + status_rank
