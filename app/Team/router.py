from fastapi import APIRouter
from .service import get_all_teams

router = APIRouter(
    prefix="/teams",
    tags=["Team"],
)


@router.get("/")
async def list_teams():
    """
    Return all NBA teams in Team entity format.
    Matches: id, nbaTeamId, name, city, abbreviation, conference, isActive.
    """
    teams_list = get_all_teams()
    return {"teams": teams_list, "count": len(teams_list)}
