import asyncio
import time
from datetime import datetime, timedelta
from nba_api.stats.endpoints import boxscoretraditionalv3, scoreboardv3
from nba_api.stats.endpoints import teamplayerdashboard
from app.database import getDb

async def testMongoConnection():
    """Check if the database is reachable."""
    try:
        db = getDb()
        # The ping command is the standard way to check connectivity
        await db.command("ping")
        print("✅ MongoDB connection test successful!")
        return True
    except Exception as exc:
        print(f"❌ MongoDB connection failed: {exc}")
        return False
def get_boxscore_by_game_id(game_id: str) -> dict:
    """Fetch final box score for a single NBA game."""
    try:
        boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id,
            timeout=45
        )
        data = boxscore.get_dict()
        game = data.get("boxScoreTraditional")
        
        if not game:
            return {"game_id": game_id, "error": "No data found"}

        home_team = game["homeTeam"]
        away_team = game["awayTeam"]

        return {
            "game_id": game_id,
            "home_team": {
                "team_id": home_team["teamId"],
                "team_name": home_team["teamName"],
                "statistics": home_team.get("statistics", {}),
                "players": home_team.get("players", []),
            },
            "away_team": {
                "team_id": away_team["teamId"],
                "team_name": away_team["teamName"],
                "statistics": away_team.get("statistics", {}),
                "players": away_team.get("players", []),
            },
        }
    except Exception as exc:
        print(f"Error fetching game {game_id}: {exc}")
        return {"game_id": game_id, "error": str(exc)}


def get_last_night_game_winners(game_date: str | None = None) -> list[dict]:
    """
    Return list of {gameId, winnerTeamId} for finished games on the given date.
    Uses ScoreboardV3 (single API call). Only includes games with gameStatus == 3 (final).
    """
    if game_date is None:
        game_date = (datetime.now() - timedelta(1)).strftime("%Y-%m-%d")

    try:
        sb = scoreboardv3.ScoreboardV3(game_date=game_date, timeout=45)
        sb_data = sb.get_dict()
        games_list = sb_data.get("scoreboard", {}).get("games", [])
    except Exception as exc:
        print(f"Error fetching scoreboard for {game_date}: {exc}")
        return []
    results = []
    for g in games_list:
        status = g.get("gameStatus") or g.get("game_status")
        if int(status or 0) != 3:
            continue

        game_id = g.get("gameId") or g.get("game_id")
        home_team = g.get("homeTeam") or {}
        away_team = g.get("awayTeam") or {}
        home_score = home_team.get("score")
        away_score = away_team.get("score")
        home_id = home_team.get("teamId")
        away_id = away_team.get("teamId")

        if home_score is None and away_score is None:
            home_score = g.get("homeTeamScore") or g.get("home_score")
            away_score = g.get("awayTeamScore") or g.get("away_score")
            home_id = home_id or g.get("homeTeamId") or g.get("home_team_id")
            away_id = away_id or g.get("awayTeamId") or g.get("away_team_id")

        if game_id is None or home_score is None or away_score is None or home_id is None or away_id is None:
            continue

        winner_id = str(home_id) if home_score > away_score else str(away_id)
        results.append({"gameId": str(game_id), "winnerTeamId": winner_id})

    return results


async def get_all_boxscores_for_date(game_date: str) -> list[dict]:
    """
    Fetch all box scores for a specific date and store them in MongoDB.
    """
    # 1. Get the scoreboard for the date
    # Note: scoreboardv3 is a synchronous call in nba_api
    sb = scoreboardv3.ScoreboardV3(game_date=game_date, timeout=45)
    sb_data = sb.get_dict()
    
    games_list = sb_data.get("scoreboard", {}).get("games", [])
    game_ids = [g["gameId"] for g in games_list]
    
    # Get the database instance from your database.py helper
    db = getDb()
    collection = db["boxscores"]
    results = []

    # Limit to [:1] for your testing as requested
    for g_id in game_ids[:1]:
        print(f"🔍 Fetching boxscore for: {g_id}")
        
        # This is a sync call, we run it normally
        result = get_boxscore_by_game_id(g_id)
        
        if result and "error" not in result:
            # 2. Save/Update in MongoDB
            # Using update_one with upsert=True prevents duplicates
            try:
                await collection.update_one(
                    {"game_id": g_id}, 
                    {
                        "$set": {
                            "fetched_at": datetime.now(),
                            **result
                        }
                    }, 
                    upsert=True
                )
                print(f"✅ Saved game {g_id} to MongoDB")
            except Exception as e:
                print(f"❌ Mongo Save Error: {e}")
        
        results.append(result)
        
        # NBA API is strict; even in async functions, use time.sleep 
        # or await asyncio.sleep(1.5) to respect rate limits
        await asyncio.sleep(1.5) 
        
    return results
GSW_TEAM_ID = "1610612744"
CURRENT_SEASON = "2024-25"
async def getTeamPlayerStats(
    teamId: str = GSW_TEAM_ID,
    season: str = CURRENT_SEASON
) -> dict:
    """
    Fetch per-game average team stats and per-game average player stats
    directly from NBA API (TeamPlayerDashboard).
    """

    loop = asyncio.get_event_loop()
    dashboard = await loop.run_in_executor(
        None,
        lambda: teamplayerdashboard.TeamPlayerDashboard(
            team_id=teamId,
            season=season,
            timeout=30
        )
    )

    data_dict = dashboard.get_dict()

    # ======================================================
    # TEAM AVERAGES (NBA already aggregates per game here)
    # ======================================================
    team_data = data_dict["resultSets"][0]
    t_headers = team_data["headers"]
    t_row = team_data["rowSet"][0]
    t_map = dict(zip(t_headers, t_row))

    t_fg2m = t_map["FGM"] - t_map["FG3M"]
    t_fg2a = t_map["FGA"] - t_map["FG3A"]
    team_fg2_pct = round(t_fg2m / t_fg2a, 3) if t_fg2a > 0 else 0

    team_gp = t_map["GP"]

# 2PT%
    t_fg2m = t_map["FGM"] - t_map["FG3M"]
    t_fg2a = t_map["FGA"] - t_map["FG3A"]
    team_2pt_pct = round(t_fg2m / t_fg2a, 3) if t_fg2a > 0 else 0

    team_averages = {
        "pts": round(t_map["PTS"] / team_gp, 2),
        "reb": round(t_map["REB"] / team_gp, 2),
        "ast": round(t_map["AST"] / team_gp, 2),
        "stl": round(t_map["STL"] / team_gp, 2),
        "blk": round(t_map["BLK"] / team_gp, 2),
        "tov": round(t_map["TOV"] / team_gp, 2),
        "ftPct": round(t_map["FT_PCT"], 3),
        "fg2Pct": team_2pt_pct,
        "fg3Pct": round(t_map["FG3_PCT"], 3),
    }
    # ======================================================
    # PLAYER PER-GAME AVERAGES (MANUAL DIVISION)
    # ======================================================
    players_data = data_dict["resultSets"][1]
    p_headers = players_data["headers"]
    p_rows = players_data["rowSet"]

    players = []

    for row in p_rows:
        p = dict(zip(p_headers, row))
        gp = p["GP"]

        if gp == 0:
            continue

        fg2m = p["FGM"] - p["FG3M"]
        fg2a = p["FGA"] - p["FG3A"]
        fg2_pct = round(fg2m / fg2a, 3) if fg2a > 0 else 0

        players.append({
            "playerId": p["PLAYER_ID"],
            "playerName": p["PLAYER_NAME"],
            "gp": gp,
            "pts": round(p["PTS"] / gp, 2),
            "reb": round(p["REB"] / gp, 2),
            "ast": round(p["AST"] / gp, 2),
            "stl": round(p["STL"] / gp, 2),
            "blk": round(p["BLK"] / gp, 2),
            "tov": round(p["TOV"] / gp, 2),
            "ftPct": round(p["FT_PCT"], 3),
            "fg2Pct": fg2_pct,
            "fg3Pct": round(p["FG3_PCT"], 3),
        })

    return {
        "teamId": teamId,
        "teamName": t_map["TEAM_NAME"],
        "season": season,
        "averages": team_averages,
        "players": players,
        "updatedAt": datetime.now()
    }
