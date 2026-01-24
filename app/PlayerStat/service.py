from nba_api.stats.endpoints import leagueleaders
from typing import List, Dict, Any
import pandas as pd
import time
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import players
from typing import List, Optional, Dict
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import leaguedashplayerstats


# ----------------------------------------------------------------------
# 1. The Player Service Class (Handles business logic for the Player domain)
# ----------------------------------------------------------------------

LAST_SEASON = "2024-25"


class PlayerService:
    def __init__(self, sleep_between_calls: float = 0.6):
        self.sleep_between_calls = sleep_between_calls

    def get_player_last_season_averages(self, player_id: str,season: str) -> dict:
        """
        Retrieves both Regular Season and Playoff averages for a specific season 
        using the PlayerCareerStats endpoint.
        """
        # 1. Fetch data for the specific player (one call for all career history)
        career = playercareerstats.PlayerCareerStats(player_id=player_id)
        player_info = players.find_player_by_id(player_id)
        player_name = player_info['full_name'] if player_info else "Unknown Player"
        # 2. Convert to DataFrames
        # [0] is Regular Season, [2] is Post Season (Playoffs)
        df_regular = career.get_data_frames()[0]
        df_playoffs = career.get_data_frames()[2]

        # 3. Filter for the specific season (e.g., '2023-24')
        reg_row = df_regular[df_regular['SEASON_ID'] == season]
        ply_row = df_playoffs[df_playoffs['SEASON_ID'] == season]

        return {
            "playerId": player_id,
            "player name":player_name,
            "season": season,
            "regularSeason": self._parse_row(reg_row) if not reg_row.empty else None,
            "playoffs": self._parse_row(ply_row) if not ply_row.empty else None
        }

    def _parse_row(self, row_df: pd.DataFrame) -> dict:
        """Helper to extract and format per-game averages from a season total row."""
        # PlayerCareerStats returns TOTALS. We divide by GP (Games Played) for averages.
        gp = int(row_df['GP'].iloc[0])
        if gp == 0: return None
        
        data = row_df.iloc[0]
        return {
            "pts": round(data["PTS"] / gp, 2),
            "reb": round(data["REB"] / gp, 2),
            "ast": round(data["AST"] / gp, 2),
            "stl": round(data["STL"] / gp, 2),
            "blk": round(data["BLK"] / gp, 2),
            "tov": round(data["TOV"] / gp, 2),
            "ftPct": round(data["FT_PCT"], 3),
            "fgPct": round(data["FG_PCT"], 3),
            "fg3Pct": round(data["FG3_PCT"], 3),
            "gp": gp
        }
    def get_entity_id(self, name: str, entity_type: str = 'player') -> Optional[int]:
        """Retrieve Player ID or Team ID by full name."""
        if entity_type == 'player':
            entity_list = players.get_players()
        elif entity_type == 'team':
            entity_list = teams.get_teams()
        else:
            raise ValueError("entity_type must be 'player' or 'team'")

        found_entity = next((e for e in entity_list if e['full_name'].lower() == name.lower()), None)
        return found_entity['id'] if found_entity else None

    def get_player_averages_vs_opponent(
        self,
        player_name: str,
        opponent_team_name: str,
        season: str = '2024-25'
    ) -> pd.DataFrame:
        """
        Calculates a player's per-game averages against a specific opponent for a season.
        """
        player_id = self.get_entity_id(player_name, 'player')
        opponent_id = self.get_entity_id(opponent_team_name, 'team')

        if not player_id or not opponent_id:
            return pd.DataFrame()

        STATS_COLS = ['PTS', 'AST', 'OREB', 'DREB', 'TOV', 'FG3M', 'STL', 'BLK']

        try:
            time.sleep(self.sleep_between_calls)
            log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
            df = log.get_data_frames()[0]
        except Exception:
            return pd.DataFrame()

        if df.empty:
            return pd.DataFrame()

        opponent_abbrev = teams.find_team_name_by_id(opponent_id)['abbreviation']
        filtered_df = df[df['MATCHUP'].str.contains(opponent_abbrev, case=False, na=False)].copy()

        games_played = len(filtered_df)
        if games_played == 0:
            return pd.DataFrame()

        averages = (filtered_df[STATS_COLS].sum() / games_played).round(2)

        result = {
            'PlayerID': player_id,
            'PlayerName': player_name,
            'OpponentID': opponent_id,
            'OpponentName': opponent_team_name,
            'Season': season,
            'GamesPlayedVsOpp': games_played,
            'PointsAvg': averages['PTS'],
            'AssistsAvg': averages['AST'],
            'OffRebAvg': averages['OREB'],
            'DefRebAvg': averages['DREB'],
            'TOT_Rebounds': averages['OREB']+averages['DREB'],
            'TurnoversAvg': averages['TOV'],
            '3PM_Avg': averages['FG3M'],
            'StealsAvg': averages['STL'],
            'BlocksAvg': averages['BLK']
        }

        return pd.DataFrame([result])
    def get_player_ids_by_names(self, names: List[str]) -> Dict[str, int]:
        """Retrieve Player IDs for a list of full player names."""
        all_players = players.get_players()
        id_map = {}
        for name in names:
            found_player = next(
                (p for p in all_players if p['full_name'].lower() == name.lower()), None
            )
            if found_player:
                id_map[name] = found_player['id']
        return id_map

    def get_historical_player_averages(
        self,
        start_year: str = '2024-25',
        end_year: str = '2022-23',
        player_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Retrieve historical season averages for specified players.
        If player_ids is None, defaults to first 10 active players.
        """
        # Determine players to query
        if player_ids:
            nba_players_data = players.get_players()
            player_id_to_name = {
                p['id']: p['full_name']
                for p in nba_players_data
                if p['id'] in player_ids
            }
        else:
            nba_players = players.get_active_players()
            player_id_to_name = {p['id']: p['full_name'] for p in nba_players}
            player_id_to_name = dict(list(player_id_to_name.items())[:10])

        # Build seasons list
        season_start_int = int(start_year[:4])
        season_end_int = int(end_year[:4])
        seasons_to_query = [f"{y}-{str(y+1)[2:]}" for y in range(season_start_int, season_end_int-1, -1)]

        all_player_seasons = []

        for player_id, player_name in player_id_to_name.items():
            time.sleep(self.sleep_between_calls)
            try:
                career = playercareerstats.PlayerCareerStats(player_id=player_id)
                career_df = career.season_totals_regular_season.get_data_frame()
                if career_df.empty:
                    continue
                filtered_df = career_df[career_df['SEASON_ID'].isin(seasons_to_query)].copy()
                if not filtered_df.empty:
                    filtered_df['PlayerName'] = player_name
                    all_player_seasons.append(filtered_df)
            except Exception:
                continue

        if not all_player_seasons:
            return pd.DataFrame()

        # Combine all player data
        master_df = pd.concat(all_player_seasons, ignore_index=True)
        STATS_COLS = ['PTS', 'AST', 'OREB', 'DREB', 'TOV', 'FG3M', 'STL', 'BLK', 'GP']
        df_totals = master_df[['PLAYER_ID', 'PlayerName', 'SEASON_ID'] + STATS_COLS].copy()

        cols_to_average = [c for c in STATS_COLS if c != 'GP']
        df_totals['GP_SAFE'] = df_totals['GP'].apply(lambda x: x if x > 0 else 1)

        for col in cols_to_average:
            df_totals[col] = df_totals[col] / df_totals['GP_SAFE']
            df_totals.loc[df_totals['GP'] == 0, col] = 0
            df_totals[col] = df_totals[col].round(2)

        final_column_map = {
            'PLAYER_ID': 'PlayerID',
            'SEASON_ID': 'Year',
            'GP': 'GamesPlayed',
            'PTS': 'PointsAvg',
            'AST': 'AssistsAvg',
            'OREB': 'OffRebAvg',
            'DREB': 'DefRebAvg',
            'TOV': 'TurnoversAvg',
            'FG3M': '3PM_Avg',
            'STL': 'StealsAvg',
            'BLK': 'BlocksAvg'
        }

        final_df = df_totals[['PLAYER_ID', 'PlayerName', 'SEASON_ID', 'GP'] + cols_to_average].rename(columns=final_column_map)
        return final_df[['PlayerID', 'PlayerName', 'Year', 'GamesPlayed', 'PointsAvg', 'AssistsAvg',
                         'OffRebAvg', 'DefRebAvg', 'TurnoversAvg', '3PM_Avg', 'StealsAvg', 'BlocksAvg']]
    async def fetchTopLeadersByPoints(self, topN: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches the top N point leaders from the NBA API (external dependency),
        returning per-game averages.
        """
        try:
            leaders = leagueleaders.LeagueLeaders(
                stat_category_abbreviation="PTS",
                per_mode48="PerGame"   
            )

            leaders_data = leaders.get_data_frames()[0].to_dict("records")

            top_leaders = [
                {
                    "rank": player.get("RANK"),
                    "playerName": player.get("PLAYER"),
                    "teamID": player.get("TEAM_ID"),
                    'PlayerId' : player.get("PLAYER_ID"),
                    "pointsPerGame": player.get("PTS"),
                    "reboundsPerGame": player.get("REB"),
                    "assistsPerGame": player.get("AST"),
                    "gamesPlayed": player.get("GP"),
                }
                for player in leaders_data[:topN]
            ]

            return top_leaders

        except Exception as e:
            print(f"Error fetching NBA leaders in PlayerService: {e}")
            raise Exception("Failed to retrieve data from external source.")

# ----------------------------------------------------------------------
# 2. Dependency Function for Service Injection
# ----------------------------------------------------------------------

def getPlayerService() -> PlayerService:
    # No complex dependencies needed yet, so it just returns the initialized class
    return PlayerService()
