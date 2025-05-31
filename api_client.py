import aiohttp
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import json
import time
from config import Config
from logger import BetBogLogger

class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("API")
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_request_time = 0
        self.rate_limit_delay = 5.0  # 5 seconds between requests to avoid 429 errors
        
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
        """Make API request with error handling and automatic reconnection"""
        url = f"{self.config.BASE_URL}{endpoint}"
        params['token'] = self.config.API_TOKEN
        params['locale'] = 'ru'
        
        # Проверяем и переподключаемся если нужно
        if not self.session or self.session.closed:
            await self._reconnect()
        
        try:
            # Rate limiting to avoid 429 errors
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - time_since_last
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = time.time()
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
            error_str = str(e)
            if "closed" in error_str.lower() or "session" in error_str.lower():
                self.logger.warning(f"Session closed, attempting reconnection: {error_str}")
                try:
                    await self._reconnect()
                    # Retry request after reconnection
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("success") == 1:
                                self.logger.success(f"API Success after reconnect: {len(data.get('results', []))} items")
                                return data
                except Exception as retry_e:
                    self.logger.error(f"Retry failed: {str(retry_e)}")
            
            self.logger.error(f"API Exception: {error_str}")
            return {"success": 0, "results": [], "error": error_str}
    
    async def _reconnect(self):
        """Переподключение к API"""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
        except:
            pass
        
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'BetBog-Monitor/1.0',
                'Accept': 'application/json'
            }
        )
        self.logger.info("API client reconnected")
    
    async def get_live_matches(self, sport_id: int = 1, skip_esports: bool = True) -> List[Dict[str, Any]]:
        """Get live football matches"""
        params = {"sport_id": sport_id}
        self.logger.info(f"Requesting live matches with sport_id={sport_id}")
        data = await self._make_request(self.config.LIVE_ENDPOINT, params)
        results = data.get("results", [])
        
        # Фильтруем виртуальные/киберспортивные матчи если нужно
        if skip_esports:
            real_matches = []
            for match in results:
                league = match.get("league", {}).get("name", "").lower()
                home_team = match.get("home", {}).get("name", "").lower() 
                away_team = match.get("away", {}).get("name", "").lower()
                
                # Исключаем виртуальные матчи по ключевым словам
                virtual_keywords = ["virtual", "esports", "fifa", "pes", "cyber", "sim", "simulation", "esoccer", "gt leagues"]
                is_virtual = any(keyword in league or keyword in home_team or keyword in away_team 
                               for keyword in virtual_keywords)
                
                if not is_virtual:
                    real_matches.append(match)
            
            self.logger.info(f"Filtered {len(results)} -> {len(real_matches)} real matches")
            return real_matches
        
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
        # Используем правильный endpoint согласно документации API
        data = await self._make_request("/event/view", params)
        results = data.get("results", [])
        if results and isinstance(results, list) and len(results) > 0:
            return results[0].get("stats", {})
        return {}
    
    async def get_finished_matches(self, 
                                 days_back: int = 1, 
                                 sport_id: int = 1,
                                 league_id: str = None,
                                 team_id: str = None) -> List[Dict[str, Any]]:
        """Get finished matches with real results from recent days"""
        all_matches = []
        
        # Получаем данные за каждый день отдельно
        for day_offset in range(days_back):
            target_date = datetime.now() - timedelta(days=day_offset + 1)  # Вчерашние и более ранние матчи
            
            params = {
                "sport_id": sport_id,
                "day": target_date.strftime("%Y%m%d"),
                "token": self.config.API_TOKEN,
                "page": 1
            }
            
            # Добавляем дополнительные фильтры если указаны
            if league_id:
                params["league_id"] = league_id
            if team_id:
                params["team_id"] = team_id
            
            try:
                self.logger.info(f"Requesting ended matches for {target_date.strftime('%Y-%m-%d')}")
                data = await self._make_request(self.config.HISTORY_ENDPOINT, params)
                matches = data.get("results", [])
                
                # Фильтруем только матчи с реальными результатами
                real_matches = []
                for match in matches:
                    parsed = self.parse_match_data(match)
                    home_score = parsed.get('home_score')
                    away_score = parsed.get('away_score')
                    
                    # Проверяем что это завершенный матч с реальным счетом
                    if (home_score is not None and away_score is not None and 
                        isinstance(home_score, int) and isinstance(away_score, int) and
                        parsed.get('status') == 'finished'):
                        real_matches.append(match)
                
                self.logger.info(f"Found {len(real_matches)} finished matches with scores for {target_date.strftime('%Y-%m-%d')}")
                all_matches.extend(real_matches)
                
            except Exception as e:
                self.logger.warning(f"Failed to get matches for {target_date.strftime('%Y-%m-%d')}: {e}")
                continue
        
        return all_matches
    
    async def get_team_matches(self, team_name: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get specific team's matches from recent period"""
        try:
            # Получаем завершенные матчи за указанный период
            matches = await self.get_finished_matches(days_back=days_back)
            
            # Фильтруем матчи для конкретной команды
            team_matches = []
            for match in matches:
                parsed = self.parse_match_data(match)
                home_team = parsed.get('home_team', '').lower()
                away_team = parsed.get('away_team', '').lower()
                search_name = team_name.lower()
                
                # Проверяем вхождение названия команды
                if search_name in home_team or search_name in away_team or home_team in search_name or away_team in search_name:
                    team_matches.append(parsed)
            
            self.logger.info(f"Found {len(team_matches)} matches for team '{team_name}' in last {days_back} days")
            return team_matches
            
        except Exception as e:
            self.logger.error(f"Error getting team matches for {team_name}: {str(e)}")
            return []
    
    async def get_upcoming_matches(self, 
                                 days_ahead: int = 1, 
                                 sport_id: int = 1,
                                 skip_esports: bool = True) -> List[Dict[str, Any]]:
        """Get upcoming matches for pre-match analysis"""
        all_matches = []
        
        # Получаем данные на ближайшие дни
        for day_offset in range(days_ahead):
            target_date = datetime.now() + timedelta(days=day_offset)
            
            params = {
                "sport_id": sport_id,
                "day": target_date.strftime("%Y%m%d"),
                "token": self.config.API_TOKEN,
                "page": 1
            }
            
            try:
                self.logger.info(f"Requesting upcoming matches for {target_date.strftime('%Y-%m-%d')}")
                data = await self._make_request("/events/upcoming", params)
                matches = data.get("results", [])
                
                # Фильтруем виртуальные матчи если нужно
                if skip_esports:
                    real_matches = []
                    for match in matches:
                        league = match.get("league", {}).get("name", "").lower()
                        home_team = match.get("home", {}).get("name", "").lower() 
                        away_team = match.get("away", {}).get("name", "").lower()
                        
                        # Исключаем виртуальные матчи
                        virtual_keywords = ["virtual", "esports", "fifa", "pes", "cyber", "sim", "simulation"]
                        is_virtual = any(keyword in league or keyword in home_team or keyword in away_team 
                                       for keyword in virtual_keywords)
                        
                        if not is_virtual:
                            real_matches.append(match)
                    
                    matches = real_matches
                
                self.logger.info(f"Found {len(matches)} upcoming matches for {target_date.strftime('%Y-%m-%d')}")
                all_matches.extend(matches)
                
            except Exception as e:
                self.logger.warning(f"Failed to get upcoming matches for {target_date.strftime('%Y-%m-%d')}: {e}")
                continue
        
        return all_matches
    
    async def get_team_matches_by_id(self, team_id: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get specific team's matches by team ID from recent period"""
        try:
            # Получаем завершенные матчи для конкретной команды по ID
            matches = await self.get_finished_matches(days_back=days_back, team_id=team_id)
            
            # Парсим данные матчей
            team_matches = []
            for match in matches:
                parsed = self.parse_match_data(match)
                if parsed:  # Добавляем только успешно распарсенные матчи
                    team_matches.append(parsed)
            
            self.logger.info(f"Found {len(team_matches)} matches for team ID '{team_id}' in last {days_back} days")
            return team_matches
            
        except Exception as e:
            self.logger.error(f"Error getting matches for team ID {team_id}: {str(e)}")
            return []

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
    
    async def get_match_by_id(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Get specific match by ID from API"""
        try:
            params = {
                "event_id": match_id,
                "token": self.config.API_TOKEN
            }
            
            self.logger.info(f"Searching for match by ID: {match_id}")
            data = await self._make_request("/event/view", params)
            
            if data and data.get("results"):
                match_data = data["results"][0] if isinstance(data["results"], list) else data["results"]
                parsed_match = self.parse_match_data(match_data)
                self.logger.success(f"Found match {match_id}: {parsed_match.get('home_team')} vs {parsed_match.get('away_team')}")
                return parsed_match
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Match {match_id} not found via direct ID search: {str(e)}")
            return None
    
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
                "home_team_id": match_data.get("home", {}).get("id") if isinstance(match_data.get("home"), dict) else None,
                "away_team_id": match_data.get("away", {}).get("id") if isinstance(match_data.get("away"), dict) else None,
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
