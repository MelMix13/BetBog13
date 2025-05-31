import aiohttp
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import json
from config import Config
from logger import BetBogLogger

class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("API")
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'BetBog-Monitor/1.0',
                'Accept': 'application/json'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make API request with error handling"""
        if not self.session:
            raise RuntimeError("API client not initialized. Use async context manager.")
            
        url = f"{self.config.BASE_URL}{endpoint}"
        params['token'] = self.config.API_TOKEN
        params['locale'] = 'ru'
        
        try:
            self.logger.info(f"API Request: {endpoint}")
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success") == 1:
                        self.logger.success(f"API Success: {len(data.get('results', []))} items")
                        return data
                    else:
                        error_msg = data.get('error_detail', 'Unknown API error')
                        self.logger.error(f"API Error: {error_msg}")
                        return {"success": 0, "results": [], "error": error_msg}
                else:
                    self.logger.error(f"HTTP Error: {response.status}")
                    return {"success": 0, "results": [], "error": f"HTTP {response.status}"}
                    
        except asyncio.TimeoutError:
            self.logger.error("API Timeout")
            return {"success": 0, "results": [], "error": "Timeout"}
        except Exception as e:
            self.logger.error(f"API Exception: {str(e)}")
            return {"success": 0, "results": [], "error": str(e)}
    
    async def get_live_matches(self, sport_id: int = 1) -> List[Dict[str, Any]]:
        """Get live football matches"""
        params = {"sport_id": sport_id}
        self.logger.info(f"Requesting live matches with sport_id={sport_id}")
        data = await self._make_request(self.config.LIVE_ENDPOINT, params)
        results = data.get("results", [])
        self.logger.info(f"Received {len(results)} live matches")
        return results
    
    async def get_match_details(self, match_id: str) -> Dict[str, Any]:
        """Get detailed match information"""
        params = {"event_id": match_id}
        data = await self._make_request("/event/view", params)
        results = data.get("results", [])
        return results[0] if results else {}
    
    async def get_match_statistics(self, match_id: str) -> Dict[str, Any]:
        """Get match statistics"""
        params = {"event_id": match_id}
        data = await self._make_request("/event/stats", params)
        return data.get("results", {})
    
    async def get_finished_matches(self, 
                                 days_back: int = 1, 
                                 sport_id: int = 1) -> List[Dict[str, Any]]:
        """Get finished matches from recent days"""
        all_matches = []
        
        # Получаем данные за каждый день отдельно
        for day_offset in range(days_back):
            target_date = datetime.now() - timedelta(days=day_offset)
            
            params = {
                "sport_id": sport_id,
                "day": target_date.strftime("%Y%m%d"),
                "token": self.config.API_TOKEN
            }
            
            try:
                self.logger.info(f"Requesting historical matches for {target_date.strftime('%Y-%m-%d')}")
                data = await self._make_request(self.config.HISTORY_ENDPOINT, params)
                matches = data.get("results", [])
                self.logger.info(f"Received {len(matches)} matches for {target_date.strftime('%Y-%m-%d')}")
                all_matches.extend(matches)
            except Exception as e:
                self.logger.warning(f"Failed to get matches for {target_date.strftime('%Y-%m-%d')}: {e}")
                continue
        
        return all_matches
    
    async def get_team_matches(self, team_name: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get specific team's matches from recent period"""
        all_matches = await self.get_finished_matches(days_back)
        team_matches = []
        
        for match in all_matches:
            home_team = match.get("home", {}).get("name", "").lower()
            away_team = match.get("away", {}).get("name", "").lower()
            search_team = team_name.lower()
            
            if search_team in home_team or search_team in away_team:
                team_matches.append(self.parse_match_data(match))
        
        return team_matches
    
    def parse_match_data(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and normalize match data"""
        try:
            # Check if match_data is actually a dictionary
            if not isinstance(match_data, dict):
                self.logger.error(f"Expected dict, got {type(match_data)}: {str(match_data)[:100]}")
                return {}
                
            # Extract basic match info
            match_info = {
                "id": match_data.get("id"),
                "home_team": match_data.get("home", {}).get("name", "Unknown") if isinstance(match_data.get("home"), dict) else "Unknown",
                "away_team": match_data.get("away", {}).get("name", "Unknown") if isinstance(match_data.get("away"), dict) else "Unknown",
                "league": match_data.get("league", {}).get("name", "Unknown") if isinstance(match_data.get("league"), dict) else "Unknown",
                "start_time": self._parse_timestamp(match_data.get("time")),
                "minute": match_data.get("timer", {}).get("tm", 0) if isinstance(match_data.get("timer"), dict) else 0,
                "status": "live" if str(match_data.get("time_status")) == "1" else "finished",
                "home_score": self._parse_score(match_data.get("ss", "0-0"), "home"),
                "away_score": self._parse_score(match_data.get("ss", "0-0"), "away")
            }
            
            # Extract statistics if available
            stats = match_data.get("stats", {})
            if stats:
                match_info["stats"] = self._normalize_stats(stats)
            
            return match_info
            
        except Exception as e:
            self.logger.error(f"Error parsing match data: {str(e)}")
            return {}
    
    def _parse_timestamp(self, time_data) -> Optional[datetime]:
        """Parse timestamp from API response"""
        if not time_data:
            return None
            
        try:
            # Handle both string and dict formats
            if isinstance(time_data, str):
                timestamp = int(time_data)
            elif isinstance(time_data, dict):
                timestamp = int(time_data.get("timestamp", 0))
            else:
                timestamp = int(time_data)
                
            if timestamp:
                return datetime.fromtimestamp(timestamp)
        except (ValueError, TypeError):
            pass
            
        return None
    
    def _parse_score(self, score_string: str, team: str) -> int:
        """Parse score from string like '1-2'"""
        try:
            if not score_string or '-' not in score_string:
                return 0
            home_score, away_score = score_string.split('-')
            if team == "home":
                return int(home_score.strip())
            else:
                return int(away_score.strip())
        except (ValueError, AttributeError):
            return 0
    
    def _normalize_stats(self, stats_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize statistics data"""
        normalized = {
            "shots_home": 0,
            "shots_away": 0,
            "shots_on_target_home": 0,
            "shots_on_target_away": 0,
            "attacks_home": 0,
            "attacks_away": 0,
            "dangerous_attacks_home": 0,
            "dangerous_attacks_away": 0,
            "possession_home": 50.0,
            "possession_away": 50.0,
            "corners_home": 0,
            "corners_away": 0,
            "yellow_cards_home": 0,
            "yellow_cards_away": 0,
            "red_cards_home": 0,
            "red_cards_away": 0
        }
        
        # Map API stats to our format
        stat_mapping = {
            "1": "shots_home",
            "2": "shots_away", 
            "3": "shots_on_target_home",
            "4": "shots_on_target_away",
            "5": "attacks_home",
            "6": "attacks_away",
            "7": "dangerous_attacks_home",
            "8": "dangerous_attacks_away",
            "9": "possession_home",
            "10": "possession_away",
            "11": "corners_home",
            "12": "corners_away",
            "13": "yellow_cards_home",
            "14": "yellow_cards_away",
            "15": "red_cards_home",
            "16": "red_cards_away"
        }
        
        for api_key, our_key in stat_mapping.items():
            if api_key in stats_data:
                try:
                    value = float(stats_data[api_key])
                    normalized[our_key] = value
                except (ValueError, TypeError):
                    continue
        
        return normalized
