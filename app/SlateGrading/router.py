"""
HTTP layer for single-date slate grading (cron / props).
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .service import SUPPORTED_CATEGORIES, grade_slate_for_date

router = APIRouter()


class CategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    line: float | None = None


class PlayerBetRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    playerName: str = Field(
        description="Full name, must match nba_api static full_name (case-insensitive).",
    )
    betId: str | None = Field(
        default=None, description="Optional id for correlation with your bet rows."
    )
    categories: list[CategoryRequest] = Field(
        default_factory=lambda: [CategoryRequest(name="points")],
        description="Stat categories to grade; defaults to [points] for backward compat.",
    )


class SlateGradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gameDate: str = Field(
        description=(
            "Schedule date in YYYY-MM-DD (Eastern / NBA.com calendar day; same as "
            "ScoreboardV3 gameDate)."
        )
    )
    playerBets: list[PlayerBetRow] = Field(
        description="Points-prop rows; each must be non-empty at request level."
    )


@router.post(
    "/grade",
    summary="Grade one slate: final games + points per bet player for that date",
    response_description="camelCase envelope with games and playerResults",
)
async def grade_slate(request: SlateGradeRequest) -> dict:
    """
    **playerBets** must be a non-empty array; empty lists return 400 (do not return success with no work).

    **gameDate** must be a valid calendar YYYY-MM-DD; invalid parse returns 400.

    **playerResults** `resolveStatus`: `resolved` (points in box for a final on this date);
    `unresolved` (name not in static data or empty name); `ambiguous` (multiple static
    `full_name` matches); `notInSlate` (id resolved but not in any loaded box, e.g. DNP / no final).
    A real 0-pt line from the box is returned as `points: 0`, not as missing.
    """
    if not request.playerBets:
        raise HTTPException(
            status_code=400,
            detail="playerBets must be a non-empty array",
        )
    if any(not row.categories for row in request.playerBets):
        raise HTTPException(
            status_code=400,
            detail="categories must be non-empty for each bet row",
        )

    requested_categories = {
        category.name for row in request.playerBets for category in row.categories
    }
    unsupported_categories = sorted(
        category for category in requested_categories if category not in SUPPORTED_CATEGORIES
    )
    if unsupported_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported categories: {unsupported_categories}",
        )

    try:
        datetime.strptime(request.gameDate, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="gameDate must be a valid YYYY-MM-DD",
        ) from None

    rows = [r.model_dump(exclude_none=True) for r in request.playerBets]

    try:
        return await grade_slate_for_date(request.gameDate, rows)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load NBA data for slate: {str(exc)}",
        ) from exc
