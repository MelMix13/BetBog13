"""
Анализ истории команд для стратегий тоталов голов
"""
import asyncio
import asyncpg
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from config import Config
from logger import BetBogLogger

class HistoricalAnalyzer:
    """Анализатор исторических данных команд"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("HISTORICAL_ANALYZER")
    
    async def get_db_connection(self):
        """Получение подключения к базе данных"""
        try:
            return await asyncpg.connect(self.config.DATABASE_URL)
        except Exception as e:
            self.logger.error(f"Ошибка подключения к БД: {e}")
            return None
    
    async def analyze_team_totals_history(self, team_name: str, days_back: int = 30) -> Dict[str, Any]:
        """Анализ истории тоталов конкретной команды"""
        conn = await self.get_db_connection()
        if not conn:
            return {}
        
        try:
            # Получаем историю матчей команды
            query = """
            SELECT 
                home_team, away_team, home_score, away_score,
                match_date, league
            FROM matches 
            WHERE (home_team ILIKE $1 OR away_team ILIKE $1)
            AND match_date >= $2
            AND home_score IS NOT NULL 
            AND away_score IS NOT NULL
            ORDER BY match_date DESC
            LIMIT 20
            """
            
            since_date = datetime.now() - timedelta(days=days_back)
            matches = await conn.fetch(query, f"%{team_name}%", since_date)
            
            if not matches:
                return {"status": "no_data", "team": team_name}
            
            # Анализируем тоталы с детальной разбивкой дома/в гостях
            totals_stats = self._analyze_totals_pattern(matches, team_name)
            recent_form = self._analyze_recent_form(matches, team_name)
            home_away_analysis = self._analyze_home_away_pattern(matches, team_name)
            
            return {
                "status": "success",
                "team": team_name,
                "matches_analyzed": len(matches),
                "totals_stats": totals_stats,
                "recent_form": recent_form,
                "home_away_analysis": home_away_analysis,
                "last_updated": datetime.now()
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа истории команды {team_name}: {e}")
            return {"status": "error", "team": team_name}
        finally:
            await conn.close()
    
    def _analyze_totals_pattern(self, matches: List[Dict], team_name: str) -> Dict[str, Any]:
        """Анализ паттернов тоталов"""
        totals = []
        over_15 = 0
        over_25 = 0  
        over_35 = 0
        under_25 = 0
        
        for match in matches:
            total_goals = match['home_score'] + match['away_score']
            totals.append(total_goals)
            
            if total_goals > 1.5:
                over_15 += 1
            if total_goals > 2.5:
                over_25 += 1
            if total_goals > 3.5:
                over_35 += 1
            if total_goals < 2.5:
                under_25 += 1
        
        total_matches = len(matches)
        avg_total = sum(totals) / total_matches if total_matches > 0 else 0
        
        return {
            "average_total": round(avg_total, 2),
            "over_15_percentage": round((over_15 / total_matches) * 100, 1) if total_matches > 0 else 0,
            "over_25_percentage": round((over_25 / total_matches) * 100, 1) if total_matches > 0 else 0,
            "over_35_percentage": round((over_35 / total_matches) * 100, 1) if total_matches > 0 else 0,
            "under_25_percentage": round((under_25 / total_matches) * 100, 1) if total_matches > 0 else 0,
            "total_trend": self._calculate_trend(totals[-5:] if len(totals) >= 5 else totals),
            "consistency": self._calculate_consistency(totals)
        }
    
    def _analyze_recent_form(self, matches: List[Dict], team_name: str) -> Dict[str, Any]:
        """Анализ недавней формы команды"""
        recent_matches = matches[:5]  # Последние 5 матчей
        
        goals_scored = []
        goals_conceded = []
        
        for match in recent_matches:
            if match['home_team'].lower() in team_name.lower():
                # Команда играла дома
                goals_scored.append(match['home_score'])
                goals_conceded.append(match['away_score'])
            else:
                # Команда играла в гостях
                goals_scored.append(match['away_score'])
                goals_conceded.append(match['home_score'])
        
        avg_scored = sum(goals_scored) / len(goals_scored) if goals_scored else 0
        avg_conceded = sum(goals_conceded) / len(goals_conceded) if goals_conceded else 0
        
        return {
            "recent_matches": len(recent_matches),
            "avg_goals_scored": round(avg_scored, 2),
            "avg_goals_conceded": round(avg_conceded, 2),
            "avg_total_involved": round(avg_scored + avg_conceded, 2),
            "scoring_trend": self._calculate_trend(goals_scored),
            "defensive_trend": self._calculate_trend(goals_conceded)
        }
    
    def _analyze_home_away_pattern(self, matches: List[Dict], team_name: str) -> Dict[str, Any]:
        """Анализ паттернов дома и в гостях"""
        home_totals = []
        away_totals = []
        
        for match in matches:
            total_goals = match['home_score'] + match['away_score']
            
            if match['home_team'].lower() in team_name.lower():
                home_totals.append(total_goals)
            else:
                away_totals.append(total_goals)
        
        home_avg = sum(home_totals) / len(home_totals) if home_totals else 0
        away_avg = sum(away_totals) / len(away_totals) if away_totals else 0
        
        return {
            "home_matches": len(home_totals),
            "away_matches": len(away_totals),
            "home_avg_total": round(home_avg, 2),
            "away_avg_total": round(away_avg, 2),
            "home_over_25": sum(1 for t in home_totals if t > 2.5) / len(home_totals) * 100 if home_totals else 0,
            "away_over_25": sum(1 for t in away_totals if t > 2.5) / len(away_totals) * 100 if away_totals else 0
        }
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Расчет тренда значений"""
        if len(values) < 2:
            return "insufficient_data"
        
        # Простой линейный тренд
        n = len(values)
        sum_x = sum(range(n))
        sum_y = sum(values)
        sum_xy = sum(i * values[i] for i in range(n))
        sum_x2 = sum(i * i for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing" 
        else:
            return "stable"
    
    def _calculate_consistency(self, values: List[float]) -> float:
        """Расчет консистентности (обратная дисперсия)"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        
        # Чем меньше дисперсия, тем выше консистентность
        consistency = 1.0 / (1.0 + variance)
        return round(consistency, 3)
    
    async def analyze_match_totals_prediction(self, home_team: str, away_team: str) -> Dict[str, Any]:
        """Комплексный анализ предстоящего матча для тоталов"""
        
        # Анализируем обе команды
        home_analysis = await self.analyze_team_totals_history(home_team)
        away_analysis = await self.analyze_team_totals_history(away_team)
        
        if (home_analysis.get("status") != "success" or 
            away_analysis.get("status") != "success"):
            return {"status": "insufficient_data"}
        
        # Анализируем историю личных встреч
        h2h_analysis = await self.analyze_head_to_head(home_team, away_team)
        
        # Делаем прогноз
        prediction = self._calculate_totals_prediction(home_analysis, away_analysis, h2h_analysis)
        
        return {
            "status": "success",
            "home_team": home_team,
            "away_team": away_team,
            "home_analysis": home_analysis,
            "away_analysis": away_analysis,
            "h2h_analysis": h2h_analysis,
            "prediction": prediction,
            "confidence_factors": self._get_confidence_factors(home_analysis, away_analysis, h2h_analysis)
        }
    
    async def analyze_head_to_head(self, home_team: str, away_team: str, limit: int = 5) -> Dict[str, Any]:
        """Анализ личных встреч команд"""
        conn = await self.get_db_connection()
        if not conn:
            return {"status": "no_connection"}
        
        try:
            query = """
            SELECT home_team, away_team, home_score, away_score, match_date
            FROM matches 
            WHERE (
                (home_team ILIKE $1 AND away_team ILIKE $2) OR
                (home_team ILIKE $2 AND away_team ILIKE $1)
            )
            AND home_score IS NOT NULL 
            AND away_score IS NOT NULL
            ORDER BY match_date DESC
            LIMIT $3
            """
            
            matches = await conn.fetch(query, f"%{home_team}%", f"%{away_team}%", limit)
            
            if not matches:
                return {"status": "no_h2h_data"}
            
            totals = [match['home_score'] + match['away_score'] for match in matches]
            avg_total = sum(totals) / len(totals)
            over_25_count = sum(1 for t in totals if t > 2.5)
            
            return {
                "status": "success",
                "matches_found": len(matches),
                "average_total": round(avg_total, 2),
                "over_25_percentage": round((over_25_count / len(matches)) * 100, 1),
                "recent_totals": totals,
                "trend": self._calculate_trend(totals)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа H2H {home_team} vs {away_team}: {e}")
            return {"status": "error"}
        finally:
            await conn.close()
    
    def _calculate_totals_prediction(self, home_analysis: Dict, away_analysis: Dict, h2h_analysis: Dict) -> Dict[str, Any]:
        """Расчет прогноза для тоталов"""
        
        # Базовые показатели команд
        home_avg = home_analysis.get("total_analysis", {}).get("average_total", 2.5)
        away_avg = away_analysis.get("total_analysis", {}).get("average_total", 2.5)
        
        # Учитываем домашний фактор
        home_home_avg = home_analysis.get("home_away_analysis", {}).get("home_avg_total", home_avg)
        away_away_avg = away_analysis.get("home_away_analysis", {}).get("away_avg_total", away_avg)
        
        # Прогнозируемый тотал
        predicted_total = (home_home_avg + away_away_avg) / 2
        
        # Корректировка по H2H
        if h2h_analysis.get("status") == "success":
            h2h_avg = h2h_analysis.get("average_total", predicted_total)
            predicted_total = (predicted_total * 0.7 + h2h_avg * 0.3)  # 70% общая форма, 30% H2H
        
        # Расчет вероятностей
        over_25_prob = self._calculate_over_probability(predicted_total, 2.5)
        under_25_prob = 1.0 - over_25_prob
        
        return {
            "predicted_total": round(predicted_total, 2),
            "over_25_probability": round(over_25_prob, 3),
            "under_25_probability": round(under_25_prob, 3),
            "recommendation": "over_2.5" if over_25_prob > 0.6 else "under_2.5" if under_25_prob > 0.6 else "no_bet",
            "confidence": max(over_25_prob, under_25_prob)
        }
    
    def _calculate_over_probability(self, predicted_total: float, line: float) -> float:
        """Расчет вероятности прохождения тотала"""
        # Используем логистическую функцию
        import math
        
        # Чем больше разница между прогнозом и линией, тем выше/ниже вероятность
        diff = predicted_total - line
        
        # Логистическая функция: P = 1 / (1 + e^(-k*diff))
        k = 2.0  # Коэффициент крутизны
        probability = 1.0 / (1.0 + math.exp(-k * diff))
        
        return max(0.05, min(0.95, probability))  # Ограничиваем от 5% до 95%
    
    def _get_confidence_factors(self, home_analysis: Dict, away_analysis: Dict, h2h_analysis: Dict) -> List[str]:
        """Получение факторов уверенности в прогнозе"""
        factors = []
        
        # Проверяем количество данных
        home_matches = home_analysis.get("matches_analyzed", 0)
        away_matches = away_analysis.get("matches_analyzed", 0)
        
        if home_matches >= 10 and away_matches >= 10:
            factors.append("Достаточно статистики обеих команд")
        
        # Проверяем консистентность
        home_consistency = home_analysis.get("total_analysis", {}).get("consistency", 0)
        away_consistency = away_analysis.get("total_analysis", {}).get("consistency", 0)
        
        if home_consistency > 0.7 and away_consistency > 0.7:
            factors.append("Высокая консистентность команд")
        
        # Проверяем наличие H2H данных
        if h2h_analysis.get("status") == "success":
            h2h_matches = h2h_analysis.get("matches_found", 0)
            if h2h_matches >= 3:
                factors.append("Достаточно личных встреч")
        
        # Проверяем тренды
        home_trend = home_analysis.get("form_analysis", {}).get("scoring_trend", "stable")
        away_trend = away_analysis.get("form_analysis", {}).get("scoring_trend", "stable")
        
        if home_trend == "increasing" or away_trend == "increasing":
            factors.append("Команды в атакующей форме")
        
        return factors if factors else ["Недостаточно факторов уверенности"]

async def main():
    """Тестирование анализатора"""
    config = Config()
    analyzer = HistoricalAnalyzer(config)
    
    # Тестируем анализ команды
    print("=== Анализ команды ===")
    team_analysis = await analyzer.analyze_team_totals_history("Manchester United")
    print(f"Результат: {team_analysis}")
    
    # Тестируем анализ матча
    print("\n=== Анализ матча ===")
    match_analysis = await analyzer.analyze_match_totals_prediction("Manchester United", "Liverpool")
    print(f"Результат: {match_analysis}")

if __name__ == "__main__":
    asyncio.run(main())