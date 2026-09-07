"""League configuration for all Sleeper dashboards in this repo.

Parameterized so the same tooling (sleeper_api.py, build_board.py,
live_tracker.py) works across leagues/formats instead of hardcoding one
league's IDs. Add new leagues here as they come up.
"""

from dataclasses import dataclass, field


@dataclass
class LeagueConfig:
    key: str
    name: str
    league_id: str
    draft_id: str
    format: str  # "auction" or "snake"
    budget: int | None = None  # only meaningful for auction format
    # WCV-specific: the league_id of the league this one contracted from,
    # used to diff owner sets and find departed teams' rosters (the
    # dispersal pool). Leave None for leagues with no such event.
    prior_league_id: str | None = None
    # Fallback position limits, used only if they can't be derived from the
    # live league settings. Confirm against league.roster_positions /
    # league.settings at runtime rather than trusting these blindly.
    assumed_position_limits: dict[str, int] = field(default_factory=dict)


MY_USER_ID = "468165901481406464"
MY_USERNAME = "normalmo"

LEAGUES: dict[str, LeagueConfig] = {
    "wcv": LeagueConfig(
        key="wcv",
        name="West Coast Villians",
        league_id="1380768690147983360",
        draft_id="1380768690160545792",
        format="auction",
        budget=329,
        prior_league_id="1255022229289185280",
        assumed_position_limits={
            "QB": 3, "RB": 6, "WR": 7, "TE": 3, "K": 1,
            "DL": 4, "LB": 4, "DB": 4,
        },
    ),
    "reg_cool_kids": LeagueConfig(
        key="reg_cool_kids",
        name="Reg Cool Kids",
        league_id="1394438913442979840",
        draft_id="",  # fill in once the draft is created
        format="snake",
    ),
    "chopped_cool_kids": LeagueConfig(
        key="chopped_cool_kids",
        name="Chopped Cool Kids",
        league_id="1394363458304098304",
        draft_id="",  # fill in once the draft is created
        format="snake",
    ),
}

CACHE_DIR = "cache"
PLAYERS_CACHE_PATH = f"{CACHE_DIR}/players.json"
PLAYERS_CACHE_MAX_AGE_HOURS = 24
DYNASTY_VALUES_CACHE_PATH = f"{CACHE_DIR}/dynasty_values.json"
DYNASTY_VALUES_CACHE_MAX_AGE_HOURS = 24

# DynastyProcess publishes a free, regularly-updated CSV of dynasty trade
# values keyed by sleeper_id. If this ever 404s (repo path changed), the
# code falls back to a simple position/status tiering and flags the ranking
# as approximate rather than crashing.
DYNASTY_PROCESS_VALUES_URL = (
    "https://github.com/dynastyprocess/data/raw/master/files/values-players.csv"
)
