from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from .service import get_all_boxscores_for_date, getTeamPlayerStats, testMongoConnection

router = APIRouter(
    prefix="/team-stat",
    tags=["TeamStat"]
)
@router.get("/check-db")
async def checkDbStatus():
    """Connectivity test endpoint."""
    is_alive = await testMongoConnection()
    return {"databaseConnected": is_alive}
@router.get("/boxscore/daily")
async def get_daily_boxscores(
    game_date: str = Query(
        None, 
        description="Date in YYYY-MM-DD format. Defaults to yesterday."
    )
):
    """
    Get all box scores for a specific date.
    """
    # Default to yesterday if no date is provided
    if not game_date:
        game_date = (datetime.now() - timedelta(1)).strftime('%Y-%m-%d')

    try:
        games = await get_all_boxscores_for_date(game_date)
        
        return {
            "status": "success",
            "date": game_date,
            "game_count": len(games),
            "games": games,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch daily scores: {str(exc)}"
        )
GSW_TEAM_ID = "1610612744"
CURRENT_SEASON = "2024-25"
@router.get("/player-stats")
async def get_team_stats(
    teamId: str = Query(GSW_TEAM_ID, description="The 10-digit NBA Team ID"),
    season: str = Query(CURRENT_SEASON, description="Format: YYYY-YY (e.g., 2024-25)")
):
    """
    Fetch player statistics for a specific team and season.
    Defaults to Golden State Warriors 2024-25.
    """
    try:
        stats = await getTeamPlayerStats(teamId=teamId, season=season)
        
        if not stats:
            raise HTTPException(status_code=404, detail="No data found for the given team/season.")
            
        return {
            "requestedTeamId": teamId,
            "requestedSeason": season,
            "count": len(stats),
            "players": stats
        }
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in get_team_stats: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error from NBA API")