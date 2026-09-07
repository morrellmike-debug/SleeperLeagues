"""Assembles all the data board.html needs: the dispersal pool, my roster
breakdown vs. position limits, and cut candidates. Pure data-shaping - no
HTML here (see html_render.py).
"""

from dataclasses import dataclass, field

import sleeper_api
from config import LeagueConfig, MY_USER_ID
from dynasty_values import fallback_tier_score, fetch_dynasty_values
from fantasypros import fetch_idp_rankings

# Position groups we roll IDP eligibility up into for limit-checking.
POSITION_GROUPS = ["QB", "RB", "WR", "TE", "K", "DL", "LB", "DB"]


@dataclass
class TeamInfo:
    roster_id: int
    owner_id: str | None
    team_name: str
    username: str | None


@dataclass
class BoardData:
    league: dict
    current_teams: dict[int, TeamInfo]  # roster_id -> TeamInfo
    departed_owner_ids: set[str]
    departed_orphan_roster_ids: set[int]  # prior-league rosters with owner_id None
    pool: list[dict]  # dispersal pool players, with dynasty_value + rank
    dynasty_values_are_real: bool
    idp_rankings_are_real: bool
    my_roster_id: int | None
    my_active_players: list[dict]
    my_taxi_players: list[dict]
    my_ir_players: list[dict]
    position_counts: dict[str, int]
    position_limits: dict[str, int]
    position_limits_source: str
    cut_candidates: list[dict]
    all_rosters_resolved: dict[int, list[dict]]  # roster_id -> resolved players, if time allowed


def _team_display_name(user: dict) -> str:
    metadata = user.get("metadata") or {}
    return metadata.get("team_name") or user.get("display_name") or user.get("username") or f"User {user.get('user_id')}"


def _build_team_map(rosters: list[dict], users: list[dict]) -> dict[int, TeamInfo]:
    users_by_id = {u["user_id"]: u for u in users}
    teams: dict[int, TeamInfo] = {}
    for r in rosters:
        owner_id = r.get("owner_id")
        user = users_by_id.get(owner_id) if owner_id else None
        teams[r["roster_id"]] = TeamInfo(
            roster_id=r["roster_id"],
            owner_id=owner_id,
            team_name=_team_display_name(user) if user else "Unowned/Orphaned Team",
            username=user.get("username") if user else None,
        )
    return teams


def _derive_position_limits(league: dict, cfg: LeagueConfig) -> tuple[dict[str, int], str]:
    """Best-effort derivation of position limits from live league settings.

    Sleeper doesn't have a standard "max players at position X" field in the
    public API - roster_positions describes *starting lineup* slots, not
    roster caps. We scan settings for anything that looks like an explicit
    position-limit field; if nothing is found, we fall back to the
    league-provided assumed limits and say so explicitly rather than
    presenting them as confirmed.
    """
    settings = league.get("settings") or {}
    derived = {}
    for key, value in settings.items():
        lower = key.lower()
        if "position" in lower and "limit" in lower and isinstance(value, (int, float)):
            for pos in POSITION_GROUPS:
                if pos.lower() in lower:
                    derived[pos] = int(value)

    if derived:
        return derived, "derived from league.settings (position_limit_* fields found)"

    if cfg.assumed_position_limits:
        return (
            dict(cfg.assumed_position_limits),
            "ASSUMED from spec, not confirmed via API - verify with commissioner rules before relying on this",
        )

    return {}, "no position limits available"


def _diff_departed_owners(current_users: list[dict], prior_rosters: list[dict], prior_users: list[dict]) -> tuple[set[str], set[int]]:
    current_owner_ids = {u["user_id"] for u in current_users}
    prior_owner_ids = {u["user_id"] for u in prior_users}

    departed_owner_ids = prior_owner_ids - current_owner_ids

    # Orphaned rosters in the prior league (owner_id null) also count as
    # departed - their players still need to go in the pool even though
    # there's no owner_id to diff.
    orphan_roster_ids = {r["roster_id"] for r in prior_rosters if not r.get("owner_id")}

    return departed_owner_ids, orphan_roster_ids


def _resolve_players(player_ids: list[str], players: dict) -> list[dict]:
    return [sleeper_api.player_lookup(pid, players) for pid in player_ids if pid]


def _apply_value_fields(p: dict, dynasty_values: dict[str, float], values_are_real: bool, idp_rankings: dict[str, dict]) -> None:
    """Sets dynasty_value / fp_idp_rank / fp_idp_tier / value_source / rank_score
    on a resolved player dict in place. Three-tier waterfall, each tier's
    score range kept strictly separated so sorting is consistent regardless
    of which source a given player landed in:

      1. Real DynastyProcess $ value (offense) - score = -value (lower/better
         for higher $).
      2. FantasyPros IDP consensus rank (DL/LB/DB DynastyProcess doesn't
         cover) - score = 100,000 + rank_ecr (lower/better for a lower,
         i.e. more elite, rank).
      3. Position + status tiering fallback, when neither source has the
         player (e.g. kickers) - score = 1,000,000 + tier.
    """
    pid = p["player_id"]

    if values_are_real and pid in dynasty_values:
        p["dynasty_value"] = dynasty_values[pid]
        p["fp_idp_rank"] = None
        p["fp_idp_tier"] = None
        p["value_source"] = "dynastyprocess"
        p["rank_score"] = -dynasty_values[pid]
        return

    if pid in idp_rankings:
        rank = idp_rankings[pid].get("rank_ecr")
        p["dynasty_value"] = None
        p["fp_idp_rank"] = rank
        p["fp_idp_tier"] = idp_rankings[pid].get("tier")
        p["value_source"] = "fantasypros_ecr"
        p["rank_score"] = 100_000 + (rank if rank is not None else 999)
        return

    p["dynasty_value"] = None
    p["fp_idp_rank"] = None
    p["fp_idp_tier"] = None
    p["value_source"] = "tiering"
    p["rank_score"] = 1_000_000 + fallback_tier_score(p.get("position"), p.get("status"))


def build_board_data(cfg: LeagueConfig, resolve_all_rosters: bool = True) -> BoardData:
    print(f"Fetching current league ({cfg.name})...")
    league = sleeper_api.get_league(cfg.league_id)
    current_rosters = sleeper_api.get_rosters(cfg.league_id)
    current_users = sleeper_api.get_users(cfg.league_id)
    current_teams = _build_team_map(current_rosters, current_users)

    departed_owner_ids: set[str] = set()
    orphan_roster_ids: set[int] = set()
    pool_player_ids: set[str] = set()
    pool_player_former_team: dict[str, str] = {}

    if cfg.prior_league_id:
        print(f"Fetching prior league ({cfg.prior_league_id}) to diff departed teams...")
        prior_rosters = sleeper_api.get_rosters(cfg.prior_league_id)
        prior_users = sleeper_api.get_users(cfg.prior_league_id)
        prior_users_by_id = {u["user_id"]: u for u in prior_users}
        departed_owner_ids, orphan_roster_ids = _diff_departed_owners(current_users, prior_rosters, prior_users)

        for r in prior_rosters:
            is_departed = (r.get("owner_id") in departed_owner_ids) or (r["roster_id"] in orphan_roster_ids)
            if is_departed:
                owner = prior_users_by_id.get(r.get("owner_id"))
                team_name = _team_display_name(owner) if owner else "Orphaned/Abandoned Team"
                for pid in r.get("players") or []:
                    pool_player_ids.add(pid)
                    pool_player_former_team[pid] = team_name

        print(
            f"Departed teams: {len(departed_owner_ids)} owners + {len(orphan_roster_ids)} orphaned "
            f"roster(s) -> dispersal pool of {len(pool_player_ids)} players."
        )

    players = sleeper_api.get_players()
    dynasty_values, values_are_real = fetch_dynasty_values()
    if not values_are_real:
        print("Dynasty value ranking is APPROXIMATE (position/status tiering fallback) - real source unreachable.")
    idp_rankings, idp_are_real = fetch_idp_rankings()

    pool_resolved = _resolve_players(list(pool_player_ids), players)
    for p in pool_resolved:
        _apply_value_fields(p, dynasty_values, values_are_real, idp_rankings)
        p["former_team"] = pool_player_former_team.get(p["player_id"], "Unknown")
    pool_resolved.sort(key=lambda p: p["rank_score"])

    # My roster
    my_roster = next((r for r in current_rosters if r.get("owner_id") == MY_USER_ID), None)
    my_roster_id = my_roster["roster_id"] if my_roster else None
    my_active_players: list[dict] = []
    my_taxi_players: list[dict] = []
    my_ir_players: list[dict] = []
    position_counts: dict[str, int] = {pos: 0 for pos in POSITION_GROUPS}
    cut_candidates: list[dict] = []

    if my_roster:
        taxi_ids = set(my_roster.get("taxi") or [])
        reserve_ids = set(my_roster.get("reserve") or [])
        all_ids = my_roster.get("players") or []
        active_ids = [pid for pid in all_ids if pid not in taxi_ids and pid not in reserve_ids]

        my_active_players = _resolve_players(active_ids, players)
        my_taxi_players = _resolve_players(list(taxi_ids), players)
        my_ir_players = _resolve_players(list(reserve_ids), players)

        for p in my_active_players:
            _apply_value_fields(p, dynasty_values, values_are_real, idp_rankings)
            for fp in p.get("fantasy_positions") or ([p["position"]] if p.get("position") else []):
                if fp in position_counts:
                    position_counts[fp] += 1

        cut_candidates = sorted(
            my_active_players,
            key=lambda p: p["rank_score"],
            reverse=True,  # worst value first = best cut candidate first
        )

    position_limits, position_limits_source = _derive_position_limits(league, cfg)

    all_rosters_resolved: dict[int, list[dict]] = {}
    if resolve_all_rosters:
        for r in current_rosters:
            all_rosters_resolved[r["roster_id"]] = _resolve_players(r.get("players") or [], players)

    return BoardData(
        league=league,
        current_teams=current_teams,
        departed_owner_ids=departed_owner_ids,
        departed_orphan_roster_ids=orphan_roster_ids,
        pool=pool_resolved,
        dynasty_values_are_real=values_are_real,
        idp_rankings_are_real=idp_are_real,
        my_roster_id=my_roster_id,
        my_active_players=my_active_players,
        my_taxi_players=my_taxi_players,
        my_ir_players=my_ir_players,
        position_counts=position_counts,
        position_limits=position_limits,
        position_limits_source=position_limits_source,
        cut_candidates=cut_candidates,
        all_rosters_resolved=all_rosters_resolved,
    )
