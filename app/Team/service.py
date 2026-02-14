from nba_api.stats.static import teams

# Conference mapping: current 30 NBA teams by abbreviation
# East: ATL, BOS, BKN, CHA, CHI, CLE, DET, IND, MIA, MIL, NYK, ORL, PHI, TOR, WAS
# West: DAL, DEN, GSW, HOU, LAC, LAL, MEM, MIN, NOP, OKC, PHX, POR, SAC, SAS, UTA
NBA_CONFERENCE_MAP: dict[str, str] = {
    "ATL": "East",
    "BOS": "East",
    "BKN": "East",
    "CHA": "East",
    "CHI": "East",
    "CLE": "East",
    "DET": "East",
    "IND": "East",
    "MIA": "East",
    "MIL": "East",
    "NYK": "East",
    "ORL": "East",
    "PHI": "East",
    "TOR": "East",
    "WAS": "East",
    "DAL": "West",
    "DEN": "West",
    "GSW": "West",
    "HOU": "West",
    "LAC": "West",
    "LAL": "West",
    "MEM": "West",
    "MIN": "West",
    "NOP": "West",
    "OKC": "West",
    "PHX": "West",
    "POR": "West",
    "SAC": "West",
    "SAS": "West",
    "UTA": "West",
}


def get_all_teams() -> list[dict]:
    """
    Fetch all NBA teams from nba_api and map to Team entity format.
    Returns list of dicts: id, nbaTeamId, name, city, abbreviation, conference, isActive.
    """
    raw_teams = teams.get_teams()

    result = []
    for t in raw_teams:
        abbrev = t.get("abbreviation", "") or ""
        conference = NBA_CONFERENCE_MAP.get(abbrev.upper(), "East")
        nba_id = t.get("id")
        is_active = abbrev.upper() in NBA_CONFERENCE_MAP

        result.append({
            "id": str(nba_id) if nba_id is not None else "",
            "name": t.get("full_name", "") or "",
            "city": t.get("city", "") or "",
            "abbreviation": abbrev,
            "conference": conference,
            "isActive": is_active,
        })

    return result
