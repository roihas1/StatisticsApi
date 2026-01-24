from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Dict, Any
from .service import PlayerService, getPlayerService 

# 1. Initialize the Router
router = APIRouter(
    tags=["Player Management"], # Descriptive tag for the documentation
)
@router.get(
    "/averages-vs-opponent",
    summary="Get player's averages vs a specific opponent",
    description="Retrieve a player's per-game averages (points, assists, rebounds, etc.) against a specific opponent for a given season."
)
async def get_player_averages_vs_opponent(
    player_name: str = Query(..., description="Full name of the player"),
    opponent_team_name: str = Query(..., description="Full name of the opponent team"),
    season: str = Query('2024-25', description="Season in 'YYYY-YY' format, e.g., '2024-25'"),
    playerService: PlayerService = Depends(getPlayerService)
) -> List[Dict[str, Any]]:
    """
    Returns a player's per-game averages against a specific opponent for a given season.
    """
    try:
        df = playerService.get_player_averages_vs_opponent(
            player_name=player_name,
            opponent_team_name=opponent_team_name,
            season=season
        )
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch player averages vs opponent: {e}")

# 2. Define the Endpoints
@router.get(
    "/historical-averages",
    summary="Get historical per-game averages for players",
    description="Retrieve per-game averages (points, assists, rebounds, etc.) for a list of players across multiple seasons."
)
async def get_historical_player_averages(
    start_year: str = Query('2025-26', description="Starting season, e.g., '2025-26'"),
    end_year: str = Query('2022-23', description="Ending season, e.g., '2022-23'"),
    player_names: List[str] = Query(
        default=[],
        description="List of full player names. If empty, defaults to first 10 active players."
    ),
    playerService: PlayerService = Depends(getPlayerService)
) -> List[Dict[str, Any]]:
    """
    Returns historical player averages for the given player names and seasons.
    """
    try:
        player_ids = playerService.get_player_ids_by_names(player_names) if player_names else None
        df = playerService.get_historical_player_averages(
            start_year=start_year,
            end_year=end_year,
            player_ids=list(player_ids.values()) if player_ids else None
        )
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch historical player averages: {e}")
@router.get("/getTopScoringPlayers", summary="Get top scoring players")
async def getTopScoringPlayers(
    topN: int = Query(default=10, gt=0, le=50, description="The number of players to return"),
    
    # Inject the PlayerService dependency
    playerService: PlayerService = Depends(getPlayerService)
) -> List[Dict[str, Any]]: 
    """
    Retrieves a list of the top players ranked by points scored by delegating 
    the external API call to the Player Service.
    """
    try:
        # 1. Delegate logic completely to the Service layer
        playerLeaders = await playerService.fetchTopLeadersByPoints(topN=topN)
        
        # 2. Return the HTTP Response
        return playerLeaders
        
    except Exception:
        # Catch exceptions raised by the service and return a clean HTTP error
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable or failed to retrieve external data."
        )


@router.get("/{player_id}/averages")
def get_player_averages(player_id: str ,
                        season: str = Query("2024-25", description="Format: YYYY-YY (e.g., 2024-25)"),
                        playerService: PlayerService = Depends(getPlayerService)):
    data =playerService.get_player_last_season_averages(player_id, season)

    if not data["regularSeason"] and not data["playoffs"]:
        raise HTTPException(status_code=404, detail="Player not found for last season")

    return data
