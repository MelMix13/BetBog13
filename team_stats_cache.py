"""
Система кэширования статистики команд для оптимизации API запросов
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from config import Config
from api_client import APIClient
from logger import BetBogLogger

@dataclass
class TeamStats:
    """Статистика команды"""
    team_name: str
    home_avg_goals: float = 0.0
    away_avg_goals: float = 0.0
    home_avg_attacks: float = 0.0
    away_avg_attacks: float = 0.0
    home_avg_shots: float = 0.0
    away_avg_shots: float = 0.0
    home_avg_dangerous: float = 0.0
    away_avg_dangerous: float = 0.0
    home_avg_corners: float = 0.0
    away_avg_corners: float = 0.0
    total_games: int = 0
    home_games: int = 0
    away_games: int = 0
    last_updated: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TeamStats':
        """Создание из словаря"""
        return cls(**data)

class TeamStatsCache:
    """Система кэширования статистики команд"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("TEAM_CACHE")
        self.cache_file = "team_stats_cache.json"
        self.teams_stats: Dict[str, TeamStats] = {}
        self.api_client: Optional[APIClient] = None
        
    async def initialize(self, api_client: APIClient):
        """Инициализация системы кэширования"""
        self.api_client = api_client
        await self.load_cache()
        
    async def load_cache(self):
        """Загрузка кэша из файла"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                for team_name, stats_data in cache_data.items():
                    self.teams_stats[team_name] = TeamStats.from_dict(stats_data)
                    
                self.logger.success(f"Загружен кэш для {len(self.teams_stats)} команд")
            else:
                self.logger.info("Файл кэша не найден, будет создан новый")
                
        except Exception as e:
            self.logger.error(f"Ошибка загрузки кэша: {str(e)}")
            self.teams_stats = {}
    
    async def save_cache(self):
        """Сохранение кэша в файл"""
        try:
            cache_data = {}
            for team_name, stats in self.teams_stats.items():
                cache_data[team_name] = stats.to_dict()
                
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
            self.logger.success(f"Кэш сохранен для {len(self.teams_stats)} команд")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения кэша: {str(e)}")
    
    async def update_teams_from_live_matches(self):
        """Обновление статистики команд из текущих live матчей через анализ завершенных матчей"""
        if not self.api_client:
            self.logger.error("API клиент не инициализирован")
            return
            
        try:
            self.logger.header("Получение команд из live матчей для анализа завершенных игр")
            
            # Получаем все live матчи только для извлечения списка команд
            async with self.api_client:
                live_matches = await self.api_client.get_live_matches()
            
            if not live_matches:
                self.logger.warning("Live матчи не найдены")
                return
                
            unique_teams = set()
            for match in live_matches:
                if isinstance(match, dict):
                    home_team = match.get('home', {}).get('name', '')
                    away_team = match.get('away', {}).get('name', '')
                    if home_team:
                        unique_teams.add(home_team)
                    if away_team:
                        unique_teams.add(away_team)
            
            self.logger.info(f"Найдено {len(unique_teams)} уникальных команд для анализа")
            
            # Анализируем завершенные матчи для каждой команды
            updated_count = 0
            for team_name in unique_teams:
                try:
                    await self.update_team_stats_from_finished_matches(team_name)
                    updated_count += 1
                    
                    # Пауза между запросами чтобы не перегружать API
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    self.logger.error(f"Ошибка обновления статистики для {team_name}: {str(e)}")
                    
            self.logger.success(f"Обновлена статистика для {updated_count} команд на основе завершенных матчей")
            await self.save_cache()
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления команд: {str(e)}")
    
    async def update_team_stats_from_finished_matches(self, team_name: str, days_back: int = 14):
        """Обновление статистики команды на основе завершенных матчей"""
        try:
            # Проверяем, нужно ли обновлять (если данные свежие)
            if team_name in self.teams_stats:
                last_updated = datetime.fromisoformat(self.teams_stats[team_name].last_updated)
                if datetime.now() - last_updated < timedelta(hours=6):
                    return  # Данные свежие, не обновляем
            
            self.logger.info(f"Анализ завершенных матчей для команды: {team_name}")
            
            # Получаем завершенные матчи за последние дни
            async with self.api_client:
                finished_matches = await self.api_client.get_finished_matches(days_back=days_back)
            
            if not finished_matches:
                self.logger.warning(f"Завершенные матчи не найдены")
                return
                
            # Фильтруем матчи этой команды
            team_matches = []
            for match in finished_matches:
                if isinstance(match, dict):
                    home_team = match.get('home', {}).get('name', '')
                    away_team = match.get('away', {}).get('name', '')
                    if team_name == home_team or team_name == away_team:
                        team_matches.append(match)
            
            if not team_matches:
                self.logger.warning(f"Завершенные матчи команды {team_name} не найдены")
                return
                
            # Анализируем статистику
            stats = await self.analyze_finished_team_matches(team_name, team_matches)
            
            # Сохраняем в кэш
            self.teams_stats[team_name] = stats
            self.logger.success(f"Статистика обновлена для {team_name}: {stats.total_games} завершенных матчей")
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления статистики команды {team_name}: {str(e)}")

    async def update_team_stats(self, team_name: str, days_back: int = 30):
        """Обновление статистики конкретной команды (устаревший метод)"""
        # Перенаправляем на новый метод анализа завершенных матчей
        await self.update_team_stats_from_finished_matches(team_name, days_back)
    
    async def analyze_finished_team_matches(self, team_name: str, matches: List[Dict[str, Any]]) -> TeamStats:
        """Анализ завершенных матчей команды для расчета средних показателей"""
        stats = TeamStats(team_name=team_name, last_updated=datetime.now().isoformat())
        
        home_stats = {'goals': [], 'attacks': [], 'shots': [], 'dangerous': [], 'corners': []}
        away_stats = {'goals': [], 'attacks': [], 'shots': [], 'dangerous': [], 'corners': []}
        
        for match in matches:
            try:
                # Определяем, играла ли команда дома или в гостях
                home_team = match.get('home', {}).get('name', '')
                away_team = match.get('away', {}).get('name', '')
                
                # Проверяем, что матч завершен и есть итоговый счет
                if match.get('time_status') != '3':  # 3 = Finished
                    continue
                
                # Получаем финальный счет
                ss = match.get('ss', '')
                if not ss:
                    continue
                    
                try:
                    home_goals, away_goals = map(int, ss.split('-'))
                except:
                    continue
                
                # Получаем статистику матча (если доступна)
                match_stats = match.get('stats', {})
                
                if team_name == home_team:
                    # Команда играла дома
                    stats.home_games += 1
                    home_stats['goals'].append(home_goals)
                    
                    # Добавляем статистику, если доступна
                    if match_stats:
                        home_stats['attacks'].append(match_stats.get('attacks_home', 0))
                        home_stats['shots'].append(match_stats.get('shots_home', 0))
                        home_stats['dangerous'].append(match_stats.get('dangerous_home', 0))
                        home_stats['corners'].append(match_stats.get('corners_home', 0))
                    
                elif team_name == away_team:
                    # Команда играла в гостях
                    stats.away_games += 1
                    away_stats['goals'].append(away_goals)
                    
                    # Добавляем статистику, если доступна
                    if match_stats:
                        away_stats['attacks'].append(match_stats.get('attacks_away', 0))
                        away_stats['shots'].append(match_stats.get('shots_away', 0))
                        away_stats['dangerous'].append(match_stats.get('dangerous_away', 0))
                        away_stats['corners'].append(match_stats.get('corners_away', 0))
                    
            except Exception as e:
                self.logger.debug(f"Ошибка анализа матча: {str(e)}")
                continue
        
        # Рассчитываем средние значения
        if stats.home_games > 0:
            stats.home_avg_goals = sum(home_stats['goals']) / stats.home_games
            if home_stats['attacks']:
                stats.home_avg_attacks = sum(home_stats['attacks']) / len(home_stats['attacks'])
            if home_stats['shots']:
                stats.home_avg_shots = sum(home_stats['shots']) / len(home_stats['shots'])
            if home_stats['dangerous']:
                stats.home_avg_dangerous = sum(home_stats['dangerous']) / len(home_stats['dangerous'])
            if home_stats['corners']:
                stats.home_avg_corners = sum(home_stats['corners']) / len(home_stats['corners'])
            
        if stats.away_games > 0:
            stats.away_avg_goals = sum(away_stats['goals']) / stats.away_games
            if away_stats['attacks']:
                stats.away_avg_attacks = sum(away_stats['attacks']) / len(away_stats['attacks'])
            if away_stats['shots']:
                stats.away_avg_shots = sum(away_stats['shots']) / len(away_stats['shots'])
            if away_stats['dangerous']:
                stats.away_avg_dangerous = sum(away_stats['dangerous']) / len(away_stats['dangerous'])
            if away_stats['corners']:
                stats.away_avg_corners = sum(away_stats['corners']) / len(away_stats['corners'])
        
        stats.total_games = stats.home_games + stats.away_games
        
        return stats

    async def analyze_team_matches(self, team_name: str, matches: List[Dict[str, Any]]) -> TeamStats:
        """Анализ матчей команды для расчета средних показателей"""
        stats = TeamStats(team_name=team_name, last_updated=datetime.now().isoformat())
        
        home_stats = {'goals': [], 'attacks': [], 'shots': [], 'dangerous': [], 'corners': []}
        away_stats = {'goals': [], 'attacks': [], 'shots': [], 'dangerous': [], 'corners': []}
        
        for match in matches:
            try:
                # Определяем, играла ли команда дома или в гостях
                home_team = match.get('home', {}).get('name', '')
                away_team = match.get('away', {}).get('name', '')
                
                # Получаем статистику матча
                match_stats = match.get('stats', {})
                if not match_stats:
                    continue
                
                if team_name == home_team:
                    # Команда играла дома
                    stats.home_games += 1
                    home_stats['goals'].append(match_stats.get('goals_home', 0))
                    home_stats['attacks'].append(match_stats.get('attacks_home', 0))
                    home_stats['shots'].append(match_stats.get('shots_home', 0))
                    home_stats['dangerous'].append(match_stats.get('dangerous_home', 0))
                    home_stats['corners'].append(match_stats.get('corners_home', 0))
                    
                elif team_name == away_team:
                    # Команда играла в гостях
                    stats.away_games += 1
                    away_stats['goals'].append(match_stats.get('goals_away', 0))
                    away_stats['attacks'].append(match_stats.get('attacks_away', 0))
                    away_stats['shots'].append(match_stats.get('shots_away', 0))
                    away_stats['dangerous'].append(match_stats.get('dangerous_away', 0))
                    away_stats['corners'].append(match_stats.get('corners_away', 0))
                    
            except Exception as e:
                self.logger.debug(f"Ошибка анализа матча: {str(e)}")
                continue
        
        # Рассчитываем средние значения
        if stats.home_games > 0:
            stats.home_avg_goals = sum(home_stats['goals']) / stats.home_games
            stats.home_avg_attacks = sum(home_stats['attacks']) / stats.home_games
            stats.home_avg_shots = sum(home_stats['shots']) / stats.home_games
            stats.home_avg_dangerous = sum(home_stats['dangerous']) / stats.home_games
            stats.home_avg_corners = sum(home_stats['corners']) / stats.home_games
            
        if stats.away_games > 0:
            stats.away_avg_goals = sum(away_stats['goals']) / stats.away_games
            stats.away_avg_attacks = sum(away_stats['attacks']) / stats.away_games
            stats.away_avg_shots = sum(away_stats['shots']) / stats.away_games
            stats.away_avg_dangerous = sum(away_stats['dangerous']) / stats.away_games
            stats.away_avg_corners = sum(away_stats['corners']) / stats.away_games
        
        stats.total_games = stats.home_games + stats.away_games
        
        return stats
    
    def get_team_stats(self, team_name: str) -> Optional[TeamStats]:
        """Получение статистики команды из кэша"""
        return self.teams_stats.get(team_name)
    
    def get_match_prediction_data(self, home_team: str, away_team: str) -> Dict[str, Any]:
        """Получение данных для предсказания результата матча"""
        home_stats = self.get_team_stats(home_team)
        away_stats = self.get_team_stats(away_team)
        
        prediction_data = {
            'home_team': home_team,
            'away_team': away_team,
            'data_available': False
        }
        
        if home_stats and away_stats:
            prediction_data.update({
                'data_available': True,
                'predicted_home_goals': home_stats.home_avg_goals,
                'predicted_away_goals': away_stats.away_avg_goals,
                'predicted_total_goals': home_stats.home_avg_goals + away_stats.away_avg_goals,
                'home_attack_strength': home_stats.home_avg_attacks,
                'away_attack_strength': away_stats.away_avg_attacks,
                'home_shot_efficiency': home_stats.home_avg_goals / max(home_stats.home_avg_shots, 1),
                'away_shot_efficiency': away_stats.away_avg_goals / max(away_stats.away_avg_shots, 1),
                'home_games_analyzed': home_stats.home_games,
                'away_games_analyzed': away_stats.away_games
            })
        
        return prediction_data
    
    async def is_cache_outdated(self) -> bool:
        """Проверка актуальности кэша"""
        if not os.path.exists(self.cache_file):
            return True
            
        try:
            file_modified = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
            return datetime.now() - file_modified > timedelta(hours=6)
        except:
            return True
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        total_teams = len(self.teams_stats)
        teams_with_home_data = sum(1 for stats in self.teams_stats.values() if stats.home_games > 0)
        teams_with_away_data = sum(1 for stats in self.teams_stats.values() if stats.away_games > 0)
        
        return {
            'total_teams': total_teams,
            'teams_with_home_data': teams_with_home_data,
            'teams_with_away_data': teams_with_away_data,
            'cache_file_exists': os.path.exists(self.cache_file),
            'last_modified': datetime.fromtimestamp(os.path.getmtime(self.cache_file)).isoformat() if os.path.exists(self.cache_file) else None
        }