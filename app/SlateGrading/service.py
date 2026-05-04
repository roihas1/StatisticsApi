"""
Business logic: grade a single schedule date using ScoreboardV3 + one box score per final game.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nba_api.stats.endpoints import scoreboardv3
from nba_api.stats.static import players

from app.TeamStat.service import get_boxscore_by_game_id

# Rate limit between BoxScoreTraditionalV3 calls (see TeamStat.get_all_boxscores_for_date)
SLEEP_BETWEEN_BOX_SCORES_SEC = 0.7

CATEGORY_MAP: dict[str, str] = {
    "points": "points",
    "assists": "assists",
    "rebounds": "reboundsTotal",
    "offensiveRebounds": "reboundsOffensive",
    "defensiveRebounds": "reboundsDefensive",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "threesMade": "threePointersMade",
    "threesAttempted": "threePointersAttempted",
    "freeThrowsMade": "freeThrowsMade",
    "freeThrowsAttempted": "freeThrowsAttempted",
    "fieldGoalsMade": "fieldGoalsMade",
    "fieldGoalsAttempted": "fieldGoalsAttempted",
}
SUPPORTED_CATEGORIES: frozenset[str] = frozenset(CATEGORY_MAP)


def _to_int_or_none(raw_value: Any) -> int | None:
    """Convert a box score stat field to int; preserve missing as None."""
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _extract_player_stats(player_row: dict[str, Any]) -> dict[str, Any] | None:
    """Extract personId + all supported stat categories from one box score player row."""
    pid = player_row.get("personId", player_row.get("person_id"))
    if pid is None:
        return None
    try:
        person_id = str(int(pid))
    except (TypeError, ValueError):
        return None

    statistics = player_row.get("statistics")
    stats_source = statistics if isinstance(statistics, dict) else {}
    parsed: dict[str, Any] = {"personId": person_id}
    for category, stats_key in CATEGORY_MAP.items():
        parsed[category] = _to_int_or_none(stats_source.get(stats_key))
    return parsed


def _fetch_scoreboard_sync(game_date: str) -> dict[str, Any]:
    sb = scoreboardv3.ScoreboardV3(game_date=game_date, timeout=15)
    return sb.get_dict()


def _team_display(t: dict[str, Any]) -> str:
    city = t.get("teamCity") or t.get("team_city") or ""
    name = t.get("teamName") or t.get("team_name") or ""
    if city and name:
        return f"{city} {name}"
    if name:
        return name
    tri = t.get("teamTricode") or t.get("team_tricode")
    if tri:
        return str(tri)
    return str(t.get("teamId") or "")


def _parse_final_games_for_response(sb_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build camelCase game rows for all games with gameStatus == 3 (final).
    Mirrors field fallbacks in get_last_night_game_winners.
    """
    games_list = sb_data.get("scoreboard", {}).get("games", [])
    results: list[dict[str, Any]] = []
    for g in games_list:
        status = g.get("gameStatus") or g.get("game_status")
        if int(status or 0) != 3:
            continue

        game_id = g.get("gameId") or g.get("game_id")
        home_t = g.get("homeTeam") or {}
        away_t = g.get("awayTeam") or {}
        home_score = home_t.get("score")
        away_score = away_t.get("score")
        home_id = home_t.get("teamId")
        away_id = away_t.get("teamId")

        if home_score is None and away_score is None:
            home_score = g.get("homeTeamScore") or g.get("home_score")
            away_score = g.get("awayTeamScore") or g.get("away_score")
            home_id = home_id or g.get("homeTeamId") or g.get("home_team_id")
            away_id = away_id or g.get("awayTeamId") or g.get("away_team_id")

        if game_id is None or home_score is None or away_score is None or home_id is None or away_id is None:
            continue

        h_s = int(home_score)
        a_s = int(away_score)
        if h_s == a_s:
            continue
        wid = str(home_id) if h_s > a_s else str(away_id)

        results.append(
            {
                "gameId": str(game_id),
                "boxScoreError": None,
                "home": {
                    "teamId": str(home_id),
                    "teamName": _team_display(home_t),
                    "score": h_s,
                },
                "away": {
                    "teamId": str(away_id),
                    "teamName": _team_display(away_t),
                    "score": a_s,
                },
                "winnerTeamId": wid,
            }
        )
    return results


def _static_matches_for_name(
    all_players: list[dict[str, Any]], player_name: str
) -> list[dict[str, Any]]:
    n = (player_name or "").strip().lower()
    if not n:
        return []
    return [p for p in all_players if (p.get("full_name") or "").lower() == n]


def _build_nightly_stats_map(
    final_games: list[dict[str, Any]], box_fetches: list[dict[str, Any] | None]
) -> dict[str, dict[str, Any]]:
    """
    person_id (str) -> per-game category stats for that slate.
    Last write wins (player should not appear in multiple final games on one date).
    """
    nightly_map: dict[str, dict[str, Any]] = {}
    for game, box in zip(final_games, box_fetches):
        if not box or box.get("error"):
            continue
        game_id = game["gameId"]
        for team_key in ("home_team", "away_team"):
            team = box.get(team_key) or {}
            for player_row in team.get("players") or []:
                parsed = _extract_player_stats(player_row)
                if not parsed:
                    continue
                person_id = parsed["personId"]
                nightly_map[person_id] = {
                    "gameId": str(game_id),
                    **{category: parsed.get(category) for category in CATEGORY_MAP},
                }
    return nightly_map


async def grade_slate_for_date(
    game_date: str,
    player_bets: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Grade one calendar date: finished games from scoreboard + player prop rows from static names + box scores.
    `player_bets` items: playerName, optional betId, optional categories[].
    """
    loop = asyncio.get_running_loop()

    sb_data = await loop.run_in_executor(None, _fetch_scoreboard_sync, game_date)
    final_games = _parse_final_games_for_response(sb_data)

    box_fetches: list[dict[str, Any] | None] = []
    for i, g in enumerate(final_games):
        gid = g["gameId"]
        box = await loop.run_in_executor(None, get_boxscore_by_game_id, gid)
        box_fetches.append(box)
        if box.get("error"):
            g["boxScoreError"] = str(box.get("error", "Unknown error"))
        if i < len(final_games) - 1:
            await asyncio.sleep(SLEEP_BETWEEN_BOX_SCORES_SEC)

    nightly = _build_nightly_stats_map(final_games, box_fetches)
    all_static: list[dict[str, Any]] = await loop.run_in_executor(
        None, players.get_players
    )

    player_results: list[dict[str, Any]] = []
    for row in player_bets:
        player_name = row.get("playerName") or row.get("player_name") or ""
        bet_id = row.get("betId") or row.get("bet_id")
        categories = row.get("categories") or [{"name": "points"}]

        base: dict[str, Any] = {
            "playerName": player_name,
            "playerId": None,
            "points": None,
            "gameId": None,
            "resolveStatus": "unresolved",
            "error": None,
            "categoryResults": {},
        }
        if bet_id is not None:
            base["betId"] = bet_id

        if not (player_name or "").strip():
            base["error"] = "Empty playerName"
            base["resolveStatus"] = "unresolved"
            player_results.append(base)
            continue

        matches = _static_matches_for_name(all_static, player_name)
        if len(matches) == 0:
            base["error"] = "No NBA player with this exact full name in static data"
            player_results.append(base)
            continue
        if len(matches) > 1:
            base["error"] = f"Multiple static players share full name ({len(matches)} matches); cannot resolve"
            base["resolveStatus"] = "ambiguous"
            player_results.append(base)
            continue

        pid = str(int(matches[0]["id"]))
        base["playerId"] = pid
        if pid in nightly:
            nightly_stats = nightly[pid]
            base["gameId"] = nightly_stats["gameId"]
            category_results: dict[str, dict[str, Any]] = {}
            for category in categories:
                category_name = category.get("name")
                if not category_name:
                    continue
                category_results[category_name] = {
                    "value": nightly_stats.get(category_name),
                    "line": category.get("line"),
                }
            base["categoryResults"] = category_results
            points_result = category_results.get("points")
            base["points"] = (
                points_result.get("value")
                if isinstance(points_result, dict)
                else None
            )
            base["resolveStatus"] = "resolved"
            base["error"] = None
        else:
            base["resolveStatus"] = "notInSlate"
            base["error"] = "Player not in any box score for a final game on this date (e.g. DNP or no game)"
            player_results.append(base)
            continue
        player_results.append(base)

    return {
        "status": "success",
        "gameDate": game_date,
        "gameCount": len(final_games),
        "games": final_games,
        "playerResultCount": len(player_results),
        "playerResults": player_results,
    }
