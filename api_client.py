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
        data = await self._make_request(self.config.LIVE_ENDPOINT, params)
        return data.get("results", [])
    
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
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            "sport_id": sport_id,
            "day": start_date.strftime("%Y%m%d")
        }
        
        data = await self._make_request(self.config.HISTORY_ENDPOINT, params)
        return data.get("results", [])
    
    def parse_match_data(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and normalize match data"""
        try:
            # Extract basic match info
            match_info = {
                "id": match_data.get("id"),
                "home_team": match_data.get("home", {}).get("name", "Unknown"),
                "away_team": match_data.get("away", {}).get("name", "Unknown"),
                "league": match_data.get("league", {}).get("name", "Unknown"),
                "start_time": self._parse_timestamp(match_data.get("time")),
                "minute": match_data.get("time", {}).get("minute", 0),
                "status": match_data.get("time", {}).get("status", "unknown"),
                "home_score": int(match_data.get("scores", {}).get("home", 0)),
                "away_score": int(match_data.get("scores", {}).get("away", 0))
            }
            
            # Extract statistics if available
            stats = match_data.get("stats", {})
            if stats:
                match_info["stats"] = self._normalize_stats(stats)
            
            return match_info
            
        except Exception as e:
            self.logger.error(f"Error parsing match data: {str(e)}")
            return {}
    
    def _parse_timestamp(self, time_data: Dict[str, Any]) -> Optional[datetime]:
        """Parse timestamp from API response"""
        if not time_data:
            return None
            
        try:
            timestamp = time_data.get("timestamp")
            if timestamp:
                return datetime.fromtimestamp(int(timestamp))
        except (ValueError, TypeError):
            pass
            
        return None
    
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
