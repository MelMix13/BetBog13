"""
Продвинутые стратегии для всех типов ставок с использованием производных метрик
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import math
from metrics_calculator import MatchMetrics
from logger import BetBogLogger
from historical_analyzer import HistoricalAnalyzer

@dataclass
class SignalResult:
    """Результат анализа стратегии"""
    strategy_name: str
    signal_type: str
    confidence: float
    prediction: str
    threshold_used: float
    reasoning: str
    trigger_metrics: Dict[str, float]
    recommended_odds: float = 0.0
    stake_multiplier: float = 1.0
    team_stats: Optional[Dict[str, Any]] = None

class AdvancedFootballStrategies:
    """Продвинутые футбольные стратегии с производными метриками"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = BetBogLogger("ADVANCED_STRATEGIES")
        from config import Config
        self.historical_analyzer = HistoricalAnalyzer(Config())
        
        # Коэффициенты для каждого типа ставки
        self.default_odds = {
            "over_2_5_goals": 1.85,
            "under_2_5_goals": 2.10,
            "btts_yes": 1.75,
            "btts_no": 2.20,
            "home_win": 1.95,
            "away_win": 3.20,
            "draw": 3.40,
            "next_goal_home": 1.65,
            "next_goal_away": 2.10,
            "over_1_5_goals": 1.25,
            "under_1_5_goals": 4.50,
            "over_3_5_goals": 3.20,
            "under_3_5_goals": 1.40
        }
    
    def analyze_all_strategies(self, 
                             current_metrics: MatchMetrics,
                             match_data: Dict[str, Any],
                             minute: int) -> List[SignalResult]:
        """Анализ всех стратегий и возврат сигналов"""
        signals = []
        
        # Рассчитываем производные метрики
        current_metrics = self._calculate_derived_metrics(current_metrics, match_data, minute)
        
        strategies = {
            "over_2_5_goals": self.analyze_over_2_5_goals,
            "under_2_5_goals": self.analyze_under_2_5_goals,
            "btts_yes": self.analyze_btts_yes,
            "btts_no": self.analyze_btts_no,
            "home_win": self.analyze_home_win,
            "away_win": self.analyze_away_win,
            "draw": self.analyze_draw,
            "next_goal_home": self.analyze_next_goal_home,
            "next_goal_away": self.analyze_next_goal_away,
            "over_1_5_goals": self.analyze_over_1_5_goals,
            "under_1_5_goals": self.analyze_under_1_5_goals,
            "over_3_5_goals": self.analyze_over_3_5_goals,
            "under_3_5_goals": self.analyze_under_3_5_goals
        }
        
        for strategy_name, strategy_func in strategies.items():
            try:
                result = strategy_func(current_metrics, match_data, minute)
                if result and result.confidence > 0.58:  # Минимальный порог confidence
                    signals.append(result)
                    self.logger.info(f"Сигнал {strategy_name}: {result.prediction} (confidence: {result.confidence:.2f})")
            except Exception as e:
                self.logger.error(f"Ошибка в стратегии {strategy_name}: {str(e)}")
        
        return signals

    def _calculate_derived_metrics(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> MatchMetrics:
        """Рассчитать производные метрики"""
        # Используем калькулятор метрик для расчета производных метрик
        from metrics_calculator import MetricsCalculator
        calculator = MetricsCalculator()
        return calculator.calculate_derived_metrics(metrics, match_data, minute)

    async def analyze_over_2_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал больше 2.5 голов - активная атакующая игра"""
        # Проверяем ограничение по времени - анализируем только до 25 минуты
        if minute > 25:
            return None
            
        # Основные показатели для тотала больше 2.5
        goal_expectancy_high = metrics.goal_expectancy >= 2.8
        high_tempo = metrics.match_tempo >= 2.2
        attacking_intensity_high = metrics.attacking_intensity >= 1.8
        both_teams_attacking = metrics.dominance_home >= 0.35 and metrics.dominance_away >= 0.35
        
        # Дополнительные факторы
        defensive_vulnerability = (metrics.defensive_stability_home <= 0.6 or 
                                 metrics.defensive_stability_away <= 0.6)
        high_pressure = metrics.defensive_pressure >= 15
        conversion_potential = (metrics.conversion_rate_home + metrics.conversion_rate_away) >= 0.3
        
        # Анализ текущих голов
        current_goals = metrics.goals_home + metrics.goals_away
        goals_needed = max(0, 3 - current_goals)
        time_factor = max(0.7, 1.0 - (minute / 90))
        
        conditions = [
            goal_expectancy_high,
            high_tempo,
            attacking_intensity_high,
            both_teams_attacking,
            defensive_vulnerability,
            high_pressure,
            conversion_potential,
            metrics.dxg_home + metrics.dxg_away >= 2.5,
            metrics.attacking_balance <= 0.4,  # Не слишком односторонняя игра
            minute <= 25  # Раннее прогнозирование
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 7:
            base_confidence = (conditions_met / 10) * 0.82
            
            # Бонусы
            if metrics.goal_expectancy >= 3.2:
                base_confidence += 0.06
            if current_goals >= 1 and minute <= 20:
                base_confidence += 0.04
            if metrics.pressure_zones >= 0.7:
                base_confidence += 0.03
                
            final_confidence = min(0.88, base_confidence * time_factor)
            
            reasoning_parts = [
                f"Ожидание голов: {metrics.goal_expectancy:.2f}",
                f"Темп: {metrics.match_tempo:.2f}",
                f"Интенсивность: {metrics.attacking_intensity:.2f}"
            ]
            
            return SignalResult(
                strategy_name="over_2_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Over 2.5 Goals",
                threshold_used=2.8,
                reasoning="Over 2.5: " + ", ".join(reasoning_parts),
                trigger_metrics={
                    "goal_expectancy": metrics.goal_expectancy,
                    "match_tempo": metrics.match_tempo,
                    "attacking_intensity": metrics.attacking_intensity,
                    "defensive_pressure": metrics.defensive_pressure
                },
                recommended_odds=self.default_odds["over_2_5_goals"]
            )
        return None

    async def analyze_under_2_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал меньше 2.5 голов - анализ разности между 0-м и 30-м тиком"""
        match_id = match_data.get('match_id')
        if not match_id:
            return None
        
        # Получаем данные о тиках для анализа
        try:
            from main import db_session
            if db_session is None:
                return None
            
            total_ticks = db_session.query(MatchMetrics).filter(MatchMetrics.match_id == match_id).count()
            
            # Ждем накопления минимум 30 тиков
            if total_ticks < 30:
                return None
                
            zero_tick = db_session.query(MatchMetrics)\
                .filter(MatchMetrics.match_id == match_id)\
                .order_by(MatchMetrics.created_at.asc())\
                .first()
            
            thirtieth_tick = db_session.query(MatchMetrics)\
                .filter(MatchMetrics.match_id == match_id)\
                .order_by(MatchMetrics.created_at.asc())\
                .offset(29)\
                .first()
            
            if not zero_tick or not thirtieth_tick:
                return None
                
        except Exception as e:
            return None
        
        # Анализ разностей между тиками
        delta_goal_expectancy = thirtieth_tick.goal_expectancy - zero_tick.goal_expectancy
        delta_tempo = thirtieth_tick.match_tempo - zero_tick.match_tempo
        delta_pressure = thirtieth_tick.defensive_pressure - zero_tick.defensive_pressure
        delta_intensity = thirtieth_tick.attacking_intensity - zero_tick.attacking_intensity
        
        # Условия для Under 2.5
        low_expectancy_growth = delta_goal_expectancy <= 1.2
        stable_tempo = delta_tempo <= 1.0
        defensive_improvement = (thirtieth_tick.defensive_stability_home >= zero_tick.defensive_stability_home or
                               thirtieth_tick.defensive_stability_away >= zero_tick.defensive_stability_away)
        low_pressure_growth = delta_pressure <= 8
        controlled_intensity = delta_intensity <= 1.0
        
        # Текущее состояние игры
        current_goals = metrics.goals_home + metrics.goals_away
        low_current_expectancy = metrics.goal_expectancy <= 2.3
        defensive_stability = min(metrics.defensive_stability_home, metrics.defensive_stability_away) >= 0.6
        
        conditions = [
            low_expectancy_growth,
            stable_tempo,
            defensive_improvement,
            low_pressure_growth,
            controlled_intensity,
            low_current_expectancy,
            defensive_stability,
            metrics.attacking_balance >= 0.3,  # Неравномерная игра
            metrics.conversion_rate_home + metrics.conversion_rate_away <= 0.4,
            current_goals <= 1  # Мало голов уже забито
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 7:
            base_confidence = (conditions_met / 10) * 0.79
            
            # Бонусы за стабильность
            if delta_goal_expectancy <= 0.8:
                base_confidence += 0.05
            if current_goals == 0 and minute >= 35:
                base_confidence += 0.04
            if defensive_stability:
                base_confidence += 0.03
                
            final_confidence = min(0.85, base_confidence)
            
            reasoning_parts = [
                f"Δ Ожидание: {delta_goal_expectancy:.2f}",
                f"Стабильность: {min(metrics.defensive_stability_home, metrics.defensive_stability_away):.2f}",
                f"Реализация: {metrics.conversion_rate_home + metrics.conversion_rate_away:.2f}"
            ]
            
            return SignalResult(
                strategy_name="under_2_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Under 2.5 Goals",
                threshold_used=2.3,
                reasoning="Under 2.5 (30 тиков): " + ", ".join(reasoning_parts),
                trigger_metrics={
                    "delta_goal_expectancy": delta_goal_expectancy,
                    "defensive_stability": min(metrics.defensive_stability_home, metrics.defensive_stability_away),
                    "conversion_total": metrics.conversion_rate_home + metrics.conversion_rate_away
                },
                recommended_odds=self.default_odds["under_2_5_goals"]
            )
        return None

    def analyze_btts_yes(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Обе забьют ДА - сбалансированная атака"""
        balanced_attack = metrics.attacking_balance <= 0.25
        both_teams_threat = metrics.dominance_home >= 0.3 and metrics.dominance_away >= 0.3
        vulnerability = (metrics.defensive_stability_home <= 0.7 and 
                        metrics.defensive_stability_away <= 0.7)
        
        conversion_both = (metrics.conversion_rate_home >= 0.08 and 
                          metrics.conversion_rate_away >= 0.08)
        counter_attacks = (metrics.counter_attack_potential_home >= 0.3 or 
                          metrics.counter_attack_potential_away >= 0.3)
        
        active_game = metrics.match_tempo >= 1.8 and metrics.attacking_intensity >= 1.5
        goal_expectancy_distributed = metrics.goal_expectancy >= 2.0
        
        conditions = [
            balanced_attack,
            both_teams_threat,
            vulnerability,
            conversion_both,
            counter_attacks,
            active_game,
            goal_expectancy_distributed,
            metrics.dxg_home >= 0.7 and metrics.dxg_away >= 0.7,
            metrics.pressure_zones >= 0.4
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 6:
            base_confidence = (conditions_met / 9) * 0.76
            
            if metrics.attacking_balance <= 0.15:
                base_confidence += 0.06
            if minute >= 60 and both_teams_threat:
                base_confidence += 0.04
                
            final_confidence = min(0.83, base_confidence)
            
            return SignalResult(
                strategy_name="btts_yes",
                signal_type="btts",
                confidence=final_confidence,
                prediction="Both Teams to Score - Yes",
                threshold_used=0.25,
                reasoning=f"BTTS: Баланс {metrics.attacking_balance:.2f}, Угроза обеих {both_teams_threat}",
                trigger_metrics={
                    "attacking_balance": metrics.attacking_balance,
                    "dominance_home": metrics.dominance_home,
                    "dominance_away": metrics.dominance_away
                },
                recommended_odds=self.default_odds["btts_yes"]
            )
        return None

    def analyze_btts_no(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Обе забьют НЕТ - слабая атака одной команды"""
        unbalanced_attack = metrics.attacking_balance >= 0.4
        weak_team = min(metrics.dominance_home, metrics.dominance_away) <= 0.2
        strong_defense = max(metrics.defensive_stability_home, metrics.defensive_stability_away) >= 0.8
        
        poor_conversion = min(metrics.conversion_rate_home, metrics.conversion_rate_away) <= 0.05
        low_counter_potential = (metrics.counter_attack_potential_home <= 0.2 and 
                                metrics.counter_attack_potential_away <= 0.2)
        
        defensive_game = metrics.match_tempo <= 1.5 or metrics.attacking_intensity <= 1.0
        
        conditions = [
            unbalanced_attack,
            weak_team,
            strong_defense,
            poor_conversion,
            low_counter_potential,
            defensive_game,
            metrics.goal_expectancy <= 1.8,
            min(metrics.dxg_home, metrics.dxg_away) <= 0.5
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            base_confidence = (conditions_met / 8) * 0.73
            
            if strong_defense and weak_team:
                base_confidence += 0.05
            if minute >= 45 and metrics.goals_home + metrics.goals_away <= 1:
                base_confidence += 0.04
                
            final_confidence = min(0.81, base_confidence)
            
            return SignalResult(
                strategy_name="btts_no",
                signal_type="btts",
                confidence=final_confidence,
                prediction="Both Teams to Score - No",
                threshold_used=0.4,
                reasoning=f"BTTS No: Дисбаланс {metrics.attacking_balance:.2f}, Слабая команда",
                trigger_metrics={
                    "attacking_balance": metrics.attacking_balance,
                    "weak_dominance": min(metrics.dominance_home, metrics.dominance_away),
                    "strong_defense": max(metrics.defensive_stability_home, metrics.defensive_stability_away)
                },
                recommended_odds=self.default_odds["btts_no"]
            )
        return None

    def analyze_home_win(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Победа хозяев - доминирование дома"""
        home_dominance = metrics.dominance_home >= 0.65
        home_pressure = metrics.pressure_zones >= 0.6 and metrics.possession_home >= 55
        home_conversion = metrics.conversion_rate_home >= metrics.conversion_rate_away * 1.5
        
        away_weakness = metrics.defensive_stability_away <= 0.5
        home_momentum = metrics.momentum_home >= 0.7
        home_attacking = metrics.dxg_home >= metrics.dxg_away * 1.8
        
        current_advantage = metrics.goals_home >= metrics.goals_away
        
        conditions = [
            home_dominance,
            home_pressure,
            home_conversion,
            away_weakness,
            home_momentum,
            home_attacking,
            current_advantage,
            metrics.counter_attack_potential_home >= 0.4
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            base_confidence = (conditions_met / 8) * 0.71
            
            if home_dominance and home_pressure:
                base_confidence += 0.06
            if metrics.goals_home > metrics.goals_away:
                base_confidence += 0.04
                
            final_confidence = min(0.82, base_confidence)
            
            return SignalResult(
                strategy_name="home_win",
                signal_type="match_result",
                confidence=final_confidence,
                prediction="Home Win",
                threshold_used=0.65,
                reasoning=f"Дом: Доминирование {metrics.dominance_home:.2f}, Давление {metrics.pressure_zones:.2f}",
                trigger_metrics={
                    "dominance_home": metrics.dominance_home,
                    "pressure_zones": metrics.pressure_zones,
                    "conversion_rate_home": metrics.conversion_rate_home
                },
                recommended_odds=self.default_odds["home_win"]
            )
        return None

    def analyze_away_win(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Победа гостей - эффективная игра в гостях"""
        away_efficiency = metrics.dominance_away >= 0.55
        away_counter_attacks = metrics.counter_attack_potential_away >= 0.5
        away_conversion = metrics.conversion_rate_away >= metrics.conversion_rate_home * 1.3
        
        home_weakness = metrics.defensive_stability_home <= 0.6
        away_momentum = metrics.momentum_away >= 0.6
        away_attacking = metrics.dxg_away >= metrics.dxg_home * 1.2
        
        current_advantage = metrics.goals_away >= metrics.goals_home
        
        conditions = [
            away_efficiency,
            away_counter_attacks,
            away_conversion,
            home_weakness,
            away_momentum,
            away_attacking,
            current_advantage,
            metrics.attacking_balance <= 0.3  # Сбалансированная игра или преимущество гостей
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            base_confidence = (conditions_met / 8) * 0.69
            
            if away_counter_attacks and away_conversion:
                base_confidence += 0.05
            if metrics.goals_away > metrics.goals_home:
                base_confidence += 0.04
                
            final_confidence = min(0.79, base_confidence)
            
            return SignalResult(
                strategy_name="away_win",
                signal_type="match_result",
                confidence=final_confidence,
                prediction="Away Win",
                threshold_used=0.55,
                reasoning=f"Гости: Эффективность {metrics.dominance_away:.2f}, Контратаки {metrics.counter_attack_potential_away:.2f}",
                trigger_metrics={
                    "dominance_away": metrics.dominance_away,
                    "counter_attack_potential_away": metrics.counter_attack_potential_away,
                    "conversion_rate_away": metrics.conversion_rate_away
                },
                recommended_odds=self.default_odds["away_win"]
            )
        return None

    def analyze_draw(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Ничья - равновесие команд"""
        perfect_balance = metrics.attacking_balance <= 0.15
        equal_dominance = abs(metrics.dominance_home - metrics.dominance_away) <= 0.1
        equal_conversion = abs(metrics.conversion_rate_home - metrics.conversion_rate_away) <= 0.1
        
        defensive_stability = (metrics.defensive_stability_home >= 0.7 and 
                              metrics.defensive_stability_away >= 0.7)
        equal_scores = metrics.goals_home == metrics.goals_away
        moderate_tempo = 1.2 <= metrics.match_tempo <= 2.0
        
        equal_pressure = abs(metrics.pressure_zones) <= 0.3
        late_game = minute >= 70
        
        conditions = [
            perfect_balance,
            equal_dominance,
            equal_conversion,
            defensive_stability,
            equal_scores,
            moderate_tempo,
            equal_pressure,
            abs(metrics.dxg_home - metrics.dxg_away) <= 0.5
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 6:
            base_confidence = (conditions_met / 8) * 0.67
            
            if perfect_balance and equal_dominance:
                base_confidence += 0.05
            if late_game and equal_scores:
                base_confidence += 0.04
                
            final_confidence = min(0.77, base_confidence)
            
            return SignalResult(
                strategy_name="draw",
                signal_type="match_result",
                confidence=final_confidence,
                prediction="Draw",
                threshold_used=0.15,
                reasoning=f"Ничья: Баланс {metrics.attacking_balance:.2f}, Равенство {equal_dominance}",
                trigger_metrics={
                    "attacking_balance": metrics.attacking_balance,
                    "dominance_difference": abs(metrics.dominance_home - metrics.dominance_away),
                    "goals_difference": abs(metrics.goals_home - metrics.goals_away)
                },
                recommended_odds=self.default_odds["draw"]
            )
        return None

    def analyze_next_goal_home(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Следующий гол забьют хозяева"""
        home_pressure = metrics.dominance_home >= 0.6
        home_momentum_advantage = metrics.momentum_home >= metrics.momentum_away + 0.2
        home_attacking_advantage = metrics.dxg_home >= metrics.dxg_away + 0.3
        
        recent_home_activity = metrics.pressure_zones >= 0.5 and metrics.possession_home >= 55
        away_defense_tired = metrics.defensive_stability_away <= 0.6
        
        conditions = [
            home_pressure,
            home_momentum_advantage,
            home_attacking_advantage,
            recent_home_activity,
            away_defense_tired,
            metrics.conversion_rate_home >= 0.1
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 4:
            base_confidence = (conditions_met / 6) * 0.68
            
            if minute >= 60 and home_pressure:
                base_confidence += 0.04
                
            final_confidence = min(0.76, base_confidence)
            
            return SignalResult(
                strategy_name="next_goal_home",
                signal_type="next_goal",
                confidence=final_confidence,
                prediction="Next Goal - Home",
                threshold_used=0.6,
                reasoning=f"След.гол дом: Давление {metrics.dominance_home:.2f}, Моментум +{metrics.momentum_home - metrics.momentum_away:.2f}",
                trigger_metrics={
                    "dominance_home": metrics.dominance_home,
                    "momentum_advantage": metrics.momentum_home - metrics.momentum_away,
                    "pressure_zones": metrics.pressure_zones
                },
                recommended_odds=self.default_odds["next_goal_home"]
            )
        return None

    def analyze_next_goal_away(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Следующий гол забьют гости"""
        away_counter_efficiency = metrics.counter_attack_potential_away >= 0.4
        away_momentum_advantage = metrics.momentum_away >= metrics.momentum_home + 0.15
        away_attacking_advantage = metrics.dxg_away >= metrics.dxg_home + 0.2
        
        home_pressure_fatigue = metrics.pressure_zones >= 0.6 and metrics.possession_home >= 60
        home_defense_vulnerable = metrics.defensive_stability_home <= 0.6
        
        conditions = [
            away_counter_efficiency,
            away_momentum_advantage,
            away_attacking_advantage,
            home_pressure_fatigue,
            home_defense_vulnerable,
            metrics.conversion_rate_away >= 0.08
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 4:
            base_confidence = (conditions_met / 6) * 0.66
            
            if away_counter_efficiency and home_pressure_fatigue:
                base_confidence += 0.04
                
            final_confidence = min(0.74, base_confidence)
            
            return SignalResult(
                strategy_name="next_goal_away",
                signal_type="next_goal",
                confidence=final_confidence,
                prediction="Next Goal - Away",
                threshold_used=0.4,
                reasoning=f"След.гол гости: Контратаки {metrics.counter_attack_potential_away:.2f}, Усталость дома",
                trigger_metrics={
                    "counter_attack_potential_away": metrics.counter_attack_potential_away,
                    "momentum_advantage": metrics.momentum_away - metrics.momentum_home,
                    "home_pressure_fatigue": home_pressure_fatigue
                },
                recommended_odds=self.default_odds["next_goal_away"]
            )
        return None

    # Дополнительные стратегии для других тоталов

    def analyze_over_1_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал больше 1.5 голов"""
        if minute > 35:
            return None
            
        current_goals = metrics.goals_home + metrics.goals_away
        if current_goals >= 2:
            return None
            
        moderate_expectancy = metrics.goal_expectancy >= 1.8
        decent_tempo = metrics.match_tempo >= 1.5
        attacking_teams = metrics.dominance_home >= 0.25 and metrics.dominance_away >= 0.25
        
        conditions = [
            moderate_expectancy,
            decent_tempo,
            attacking_teams,
            metrics.attacking_intensity >= 1.2,
            metrics.dxg_home + metrics.dxg_away >= 1.5
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 4:
            base_confidence = (conditions_met / 5) * 0.75
            final_confidence = min(0.82, base_confidence)
            
            return SignalResult(
                strategy_name="over_1_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Over 1.5 Goals",
                threshold_used=1.8,
                reasoning=f"Over 1.5: Ожидание {metrics.goal_expectancy:.2f}, Темп {metrics.match_tempo:.2f}",
                trigger_metrics={"goal_expectancy": metrics.goal_expectancy, "match_tempo": metrics.match_tempo},
                recommended_odds=self.default_odds["over_1_5_goals"]
            )
        return None

    def analyze_under_1_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал меньше 1.5 голов"""
        current_goals = metrics.goals_home + metrics.goals_away
        if current_goals >= 2:
            return None
            
        very_low_expectancy = metrics.goal_expectancy <= 1.2
        defensive_game = metrics.match_tempo <= 1.0
        strong_defenses = (metrics.defensive_stability_home >= 0.8 and 
                          metrics.defensive_stability_away >= 0.8)
        
        conditions = [
            very_low_expectancy,
            defensive_game,
            strong_defenses,
            metrics.attacking_intensity <= 0.8,
            metrics.conversion_rate_home + metrics.conversion_rate_away <= 0.2,
            current_goals <= 1,
            minute >= 30
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            base_confidence = (conditions_met / 7) * 0.72
            final_confidence = min(0.79, base_confidence)
            
            return SignalResult(
                strategy_name="under_1_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Under 1.5 Goals",
                threshold_used=1.2,
                reasoning=f"Under 1.5: Низкое ожидание {metrics.goal_expectancy:.2f}, Оборона",
                trigger_metrics={"goal_expectancy": metrics.goal_expectancy, "defensive_avg": (metrics.defensive_stability_home + metrics.defensive_stability_away) / 2},
                recommended_odds=self.default_odds["under_1_5_goals"]
            )
        return None

    def analyze_over_3_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал больше 3.5 голов"""
        if minute > 20:
            return None
            
        current_goals = metrics.goals_home + metrics.goals_away
        very_high_expectancy = metrics.goal_expectancy >= 3.8
        explosive_tempo = metrics.match_tempo >= 3.0
        both_attacking_well = metrics.dominance_home >= 0.4 and metrics.dominance_away >= 0.4
        
        conditions = [
            very_high_expectancy,
            explosive_tempo,
            both_attacking_well,
            metrics.attacking_intensity >= 2.5,
            metrics.defensive_pressure >= 20,
            (metrics.defensive_stability_home <= 0.4 or metrics.defensive_stability_away <= 0.4),
            current_goals >= 1
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            base_confidence = (conditions_met / 7) * 0.69
            final_confidence = min(0.76, base_confidence)
            
            return SignalResult(
                strategy_name="over_3_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Over 3.5 Goals",
                threshold_used=3.8,
                reasoning=f"Over 3.5: Высокое ожидание {metrics.goal_expectancy:.2f}, Взрывной темп",
                trigger_metrics={"goal_expectancy": metrics.goal_expectancy, "match_tempo": metrics.match_tempo},
                recommended_odds=self.default_odds["over_3_5_goals"]
            )
        return None

    def analyze_under_3_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал меньше 3.5 голов"""
        current_goals = metrics.goals_home + metrics.goals_away
        if current_goals >= 4:
            return None
            
        controlled_expectancy = metrics.goal_expectancy <= 3.0
        controlled_tempo = metrics.match_tempo <= 2.5
        decent_defense = (metrics.defensive_stability_home >= 0.5 or 
                         metrics.defensive_stability_away >= 0.5)
        
        conditions = [
            controlled_expectancy,
            controlled_tempo,
            decent_defense,
            metrics.attacking_intensity <= 2.0,
            metrics.conversion_rate_home + metrics.conversion_rate_away <= 0.6,
            current_goals <= 2
        ]
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 4:
            base_confidence = (conditions_met / 6) * 0.73
            final_confidence = min(0.81, base_confidence)
            
            return SignalResult(
                strategy_name="under_3_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="Under 3.5 Goals",
                threshold_used=3.0,
                reasoning=f"Under 3.5: Контролируемое ожидание {metrics.goal_expectancy:.2f}",
                trigger_metrics={"goal_expectancy": metrics.goal_expectancy, "match_tempo": metrics.match_tempo},
                recommended_odds=self.default_odds["under_3_5_goals"]
            )
        return None