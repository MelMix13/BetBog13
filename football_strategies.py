"""
Футбольные стратегии для реальных ставок с высоким винрейтом
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

class FootballStrategies:
    """Продвинутые футбольные стратегии с адаптивными порогами"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = BetBogLogger("FOOTBALL_STRATEGIES")
        from config import Config
        self.historical_analyzer = HistoricalAnalyzer(Config())
        
        # Коэффициенты для каждого типа ставки (среднерыночные)
        self.default_odds = {
            "over_2_5_goals": 1.85,
            "under_2_5_goals": 2.10,
            "btts_yes": 1.75,
            "btts_no": 2.20,
            "home_win": 1.95,
            "away_win": 3.20,
            "draw": 3.40,
            "next_goal_home": 1.65,
            "next_goal_away": 2.10
        }
    
    def analyze_all_strategies(self, 
                             current_metrics: MatchMetrics,
                             match_data: Dict[str, Any],
                             minute: int) -> List[SignalResult]:
        """Анализ всех стратегий и возврат сигналов"""
        signals = []
        
        strategies = {
            "over_2_5_goals": self.analyze_over_2_5_goals,
            "under_2_5_goals": self.analyze_under_2_5_goals,
            "btts_yes": self.analyze_btts_yes,
            "btts_no": self.analyze_btts_no,
            "home_win": self.analyze_home_win,
            "away_win": self.analyze_away_win,
            "draw": self.analyze_draw,
            "next_goal_home": self.analyze_next_goal_home,
            "next_goal_away": self.analyze_next_goal_away
        }
        
        for strategy_name, strategy_func in strategies.items():
            try:
                result = strategy_func(current_metrics, match_data, minute)
                if result and result.confidence > 0.55:  # Минимальный порог confidence
                    signals.append(result)
                    self.logger.strategy_signal(
                        strategy_name, 
                        result.prediction, 
                        result.confidence,
                        result.reasoning
                    )
            except Exception as e:
                self.logger.error(f"Ошибка в стратегии {strategy_name}: {str(e)}")
        
        return signals

    async def analyze_over_2_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал больше 2.5 голов - анализ с историей команд"""
        config = self.config.get("over_2_5_goals", {})
        
        # Получаем названия команд
        home_team = match_data.get('home_team', '')
        away_team = match_data.get('away_team', '')
        
        # Проводим исторический анализ (асинхронно)
        try:
            historical_prediction = await self.historical_analyzer.analyze_match_totals_prediction(home_team, away_team)
        except Exception as e:
            self.logger.warning(f"Ошибка исторического анализа: {e}")
            historical_prediction = {"status": "error"}
        
        # Текущие метрики матча
        dxg_combined = metrics.dxg_home + metrics.dxg_away
        attacks_total = match_data.get('attacks_home', 0) + match_data.get('attacks_away', 0)
        shots_total = match_data.get('shots_home', 0) + match_data.get('shots_away', 0)
        dangerous_total = match_data.get('dangerous_attacks_home', 0) + match_data.get('dangerous_attacks_away', 0)
        
        # Фактор времени
        time_factor = max(0.6, 1.0 - (minute / 90) * 0.4)
        
        # Усталость команд
        max_tiredness = max(metrics.tiredness_home, metrics.tiredness_away)
        avg_momentum = (metrics.momentum_home + metrics.momentum_away) / 2
        
        # Базовые условия игры
        live_conditions = []
        live_conditions.append(dxg_combined >= config.get("min_dxg_combined", 2.8))  
        live_conditions.append(attacks_total >= config.get("min_attacks_total", 20))  
        live_conditions.append(shots_total >= config.get("min_shots_total", 12))     
        live_conditions.append(max_tiredness <= config.get("max_tiredness_both", 0.6))
        live_conditions.append(avg_momentum >= config.get("min_momentum_either", 0.6))
        live_conditions.append(dangerous_total >= 6)
        live_conditions.append(metrics.wave_amplitude >= config.get("min_wave_amplitude", 0.35))
        
        live_conditions_met = sum(live_conditions)
        
        # Анализ истории команд
        historical_factor = 1.0
        historical_confidence = 0.0
        reasoning_parts = []
        
        if historical_prediction.get("status") == "success":
            pred = historical_prediction.get("prediction", {})
            hist_over_prob = pred.get("over_25_probability", 0.5)
            hist_recommendation = pred.get("recommendation", "no_bet")
            predicted_total = pred.get("predicted_total", 2.5)
            
            # Учитываем историческую склонность к тоталам
            if hist_recommendation == "over_2.5" and hist_over_prob > 0.6:
                historical_factor = 1.2
                historical_confidence = hist_over_prob
                reasoning_parts.append(f"История: over 2.5 ({hist_over_prob:.1%})")
            elif predicted_total > 2.7:
                historical_factor = 1.1
                historical_confidence = hist_over_prob
                reasoning_parts.append(f"Прогноз: {predicted_total:.1f} голов")
            
            # Анализ домашнего фактора
            home_analysis = historical_prediction.get("home_analysis", {})
            away_analysis = historical_prediction.get("away_analysis", {})
            
            if home_analysis.get("status") == "success":
                home_home_avg = home_analysis.get("home_away_analysis", {}).get("home_avg_total", 0)
                if home_home_avg > 2.8:
                    historical_factor += 0.1
                    reasoning_parts.append(f"Хозяева дома: {home_home_avg:.1f}")
            
            if away_analysis.get("status") == "success":
                away_away_avg = away_analysis.get("home_away_analysis", {}).get("away_avg_total", 0)
                if away_away_avg > 2.6:
                    historical_factor += 0.1
                    reasoning_parts.append(f"Гости в выезде: {away_away_avg:.1f}")
        
        # Нужно минимум 4 из 7 условий + положительный исторический фактор
        min_conditions = 4 if historical_factor > 1.0 else 5
        
        if live_conditions_met >= min_conditions:
            # Базовая уверенность от текущей игры
            base_confidence = (live_conditions_met / 7) * 0.75
            
            # Исторический бонус
            if historical_confidence > 0:
                base_confidence = (base_confidence * 0.7) + (historical_confidence * 0.3)
            
            # Бонусы за особые факторы
            if dxg_combined >= 3.5:
                base_confidence += 0.05
            if shots_total >= 16:
                base_confidence += 0.03
            if minute <= 30 and attacks_total >= 18:
                base_confidence += 0.04
                
            final_confidence = min(0.88, base_confidence * time_factor * historical_factor)
            
            # Формируем обоснование
            live_reasoning = f"Текущая игра: dxG={dxg_combined:.2f}, атаки={attacks_total}, удары={shots_total}"
            if reasoning_parts:
                full_reasoning = live_reasoning + " | " + ", ".join(reasoning_parts)
            else:
                full_reasoning = live_reasoning
            
            return SignalResult(
                strategy_name="over_2_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="over_2.5",
                threshold_used=config.get("min_dxg_combined", 2.8),
                reasoning=full_reasoning,
                trigger_metrics={
                    "dxg_combined": dxg_combined, 
                    "attacks_total": float(attacks_total), 
                    "shots_total": float(shots_total),
                    "momentum_avg": avg_momentum,
                    "historical_factor": historical_factor
                },
                recommended_odds=self.default_odds["over_2_5_goals"]
            )
        return None

    async def analyze_under_2_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Тотал меньше 2.5 голов - анализ с историей команд"""
        config = self.config.get("under_2_5_goals", {})
        
        # Получаем названия команд
        home_team = match_data.get('home_team', '')
        away_team = match_data.get('away_team', '')
        
        # Проводим исторический анализ
        try:
            historical_prediction = await self.historical_analyzer.analyze_match_totals_prediction(home_team, away_team)
        except Exception as e:
            self.logger.warning(f"Ошибка исторического анализа: {e}")
            historical_prediction = {"status": "error"}
        
        # Текущие метрики матча
        dxg_combined = metrics.dxg_home + metrics.dxg_away
        attacks_total = match_data.get('attacks_home', 0) + match_data.get('attacks_away', 0)
        shots_total = match_data.get('shots_home', 0) + match_data.get('shots_away', 0)
        
        # Стабильность обороны
        stability_avg = (metrics.stability_home + metrics.stability_away) / 2
        shots_per_attack = (metrics.shots_per_attack_home + metrics.shots_per_attack_away) / 2
        
        # Низкое качество атак
        low_danger = match_data.get('dangerous_attacks_home', 0) + match_data.get('dangerous_attacks_away', 0) <= 4
        
        # Базовые условия игры
        live_conditions = []
        live_conditions.append(dxg_combined <= config.get("max_dxg_combined", 1.8))
        live_conditions.append(attacks_total <= config.get("max_attacks_total", 18))
        live_conditions.append(stability_avg >= config.get("min_stability_both", 0.7))
        live_conditions.append(shots_per_attack <= config.get("max_shots_per_attack", 0.65))
        live_conditions.append(metrics.wave_amplitude <= config.get("max_wave_amplitude", 0.35))
        live_conditions.append(low_danger)
        live_conditions.append(shots_total <= 12)
        
        live_conditions_met = sum(live_conditions)
        
        # Анализ истории команд для under
        historical_factor = 1.0
        historical_confidence = 0.0
        reasoning_parts = []
        
        if historical_prediction.get("status") == "success":
            pred = historical_prediction.get("prediction", {})
            hist_under_prob = pred.get("under_25_probability", 0.5)
            hist_recommendation = pred.get("recommendation", "no_bet")
            predicted_total = pred.get("predicted_total", 2.5)
            
            # Учитываем историческую склонность к low scoring
            if hist_recommendation == "under_2.5" and hist_under_prob > 0.6:
                historical_factor = 1.2
                historical_confidence = hist_under_prob
                reasoning_parts.append(f"История: under 2.5 ({hist_under_prob:.1%})")
            elif predicted_total < 2.3:
                historical_factor = 1.1
                historical_confidence = hist_under_prob
                reasoning_parts.append(f"Прогноз: {predicted_total:.1f} голов")
            
            # Анализ оборонительных показателей команд
            home_analysis = historical_prediction.get("home_analysis", {})
            away_analysis = historical_prediction.get("away_analysis", {})
            
            if home_analysis.get("status") == "success":
                home_home_avg = home_analysis.get("home_away_analysis", {}).get("home_avg_total", 0)
                if home_home_avg < 2.2:
                    historical_factor += 0.1
                    reasoning_parts.append(f"Хозяева дома: {home_home_avg:.1f}")
            
            if away_analysis.get("status") == "success":
                away_away_avg = away_analysis.get("home_away_analysis", {}).get("away_avg_total", 0)
                if away_away_avg < 2.4:
                    historical_factor += 0.1
                    reasoning_parts.append(f"Гости в выезде: {away_away_avg:.1f}")
        
        # Нужно минимум 4 из 7 условий + положительный исторический фактор для under
        min_conditions = 4 if historical_factor > 1.0 else 5
        
        if live_conditions_met >= min_conditions:
            # Базовая уверенность от текущей игры
            base_confidence = (live_conditions_met / 7) * 0.75
            
            # Исторический бонус
            if historical_confidence > 0:
                base_confidence = (base_confidence * 0.7) + (historical_confidence * 0.3)
            
            # Бонусы за оборонительную игру
            if stability_avg >= 0.85:
                base_confidence += 0.05
            if dxg_combined <= 1.4:
                base_confidence += 0.04
            if shots_per_attack <= 0.5:
                base_confidence += 0.03
                
            final_confidence = min(0.85, base_confidence * historical_factor)
            
            # Формируем обоснование
            live_reasoning = f"Оборонительная игра: dxG={dxg_combined:.2f}, стабильность={stability_avg:.2f}, удары/атака={shots_per_attack:.2f}"
            if reasoning_parts:
                full_reasoning = live_reasoning + " | " + ", ".join(reasoning_parts)
            else:
                full_reasoning = live_reasoning
                
            return SignalResult(
                strategy_name="under_2_5_goals",
                signal_type="total_goals",
                confidence=final_confidence,
                prediction="under_2.5",
                threshold_used=config.get("max_dxg_combined", 1.8),
                reasoning=full_reasoning,
                trigger_metrics={
                    "dxg_combined": dxg_combined, 
                    "stability_both": stability_avg, 
                    "shots_per_attack": shots_per_attack,
                    "historical_factor": historical_factor
                },
                recommended_odds=self.default_odds["under_2_5_goals"]
            )
        return None

    def analyze_btts_yes(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Обе забьют ДА - сбалансированная атака обеих команд"""
        config = self.config.get("btts_yes", {})
        
        # Минимальные показатели каждой команды
        min_dxg = min(metrics.dxg_home, metrics.dxg_away)
        min_shots = min(match_data.get('shots_home', 0), match_data.get('shots_away', 0))
        min_attacks = min(match_data.get('attacks_home', 0), match_data.get('attacks_away', 0))
        min_momentum = min(metrics.momentum_home, metrics.momentum_away)
        
        # Баланс команд
        dxg_balance = 1.0 - abs(metrics.dxg_home - metrics.dxg_away) / max(metrics.dxg_home + metrics.dxg_away, 1)
        away_quality = match_data.get('attacks_away', 0) >= 6  # Гости должны атаковать
        
        conditions = []
        conditions.append(min_dxg >= config.get("min_dxg_both_teams", 0.9))
        conditions.append(min_shots >= config.get("min_shots_both", 4))
        conditions.append(min_attacks >= 6)
        conditions.append(min_momentum >= config.get("min_momentum_both", 0.5))
        conditions.append(dxg_balance >= 0.4)  # Не слишком большая разница
        conditions.append(away_quality)
        conditions.append(max(metrics.stability_home, metrics.stability_away) <= 0.9)  # Не железная оборона
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.70
            
            # Бонусы за баланс
            if dxg_balance >= 0.6:
                confidence += 0.05
            if min_dxg >= 1.2:
                confidence += 0.04
                
            return SignalResult(
                strategy_name="btts_yes",
                signal_type="both_teams_score",
                confidence=min(0.80, confidence),
                prediction="yes",
                threshold_used=config.get("min_dxg_both_teams", 0.9),
                reasoning=f"Сбалансированная атака: мин.dxG={min_dxg:.2f}, баланс={dxg_balance:.2f}",
                trigger_metrics={
                    "dxg_both_teams": min_dxg, 
                    "shots_both": float(min_shots), 
                    "momentum_both": min_momentum
                },
                recommended_odds=self.default_odds["btts_yes"]
            )
        return None

    def analyze_btts_no(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Обе забьют НЕТ - слабая атака одной команды"""
        config = self.config.get("btts_no", {})
        
        # Ищем слабое звено
        weaker_dxg = min(metrics.dxg_home, metrics.dxg_away)
        weaker_shots = min(match_data.get('shots_home', 0), match_data.get('shots_away', 0))
        away_attacks = match_data.get('attacks_away', 0)
        away_dangerous = match_data.get('dangerous_attacks_away', 0)
        
        # Сильная оборона
        stronger_stability = max(metrics.stability_home, metrics.stability_away)
        
        conditions = []
        conditions.append(weaker_dxg <= config.get("max_dxg_weaker", 0.4))
        conditions.append(stronger_stability >= config.get("min_stability_stronger", 0.85))
        conditions.append(weaker_shots <= config.get("max_away_shots", 3))
        conditions.append(away_attacks <= 8)  # Слабая атака гостей
        conditions.append(away_dangerous <= config.get("max_dangerous_attacks_away", 2))
        conditions.append(min(metrics.momentum_home, metrics.momentum_away) <= 0.4)
        conditions.append(metrics.wave_amplitude <= 0.35)  # Спокойная игра
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.75
            
            # Бонусы за оборонительное превосходство
            if stronger_stability >= 0.9:
                confidence += 0.05
            if weaker_dxg <= 0.3:
                confidence += 0.04
                
            return SignalResult(
                strategy_name="btts_no",
                signal_type="both_teams_score",
                confidence=min(0.82, confidence),
                prediction="no",
                threshold_used=config.get("max_dxg_weaker", 0.4),
                reasoning=f"Слабая атака: мин.dxG={weaker_dxg:.2f}, сильная оборона={stronger_stability:.2f}",
                trigger_metrics={
                    "dxg_weaker": weaker_dxg, 
                    "stability_stronger": stronger_stability, 
                    "away_shots": float(weaker_shots)
                },
                recommended_odds=self.default_odds["btts_no"]
            )
        return None

    def analyze_home_win(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Победа хозяев - превосходство на своем поле"""
        config = self.config.get("home_win", {})
        
        dxg_advantage = metrics.dxg_home - metrics.dxg_away
        home_shots = match_data.get('shots_home', 0)
        away_shots = match_data.get('shots_away', 0)
        home_shots_ratio = home_shots / max(away_shots, 1)
        
        # Эффективность гостей
        away_attacks = match_data.get('attacks_away', 0)
        away_efficiency = away_shots / max(away_attacks, 1) if away_attacks > 0 else 0
        
        # Домашний фактор
        home_pressure = metrics.momentum_home * (1.0 - metrics.tiredness_home)
        
        conditions = []
        conditions.append(dxg_advantage >= config.get("min_dxg_advantage", 1.2))
        conditions.append(metrics.momentum_home >= config.get("min_home_momentum", 0.75))
        conditions.append(metrics.tiredness_home <= config.get("max_home_tiredness", 0.45))
        conditions.append(home_shots_ratio >= config.get("min_home_shots_ratio", 1.8))
        conditions.append(away_efficiency <= config.get("away_low_efficiency", 0.4))
        conditions.append(home_pressure >= 0.6)
        conditions.append(metrics.stability_away <= 0.7)  # Слабая оборона гостей
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.60  # Победы сложнее предсказать
            
            # Домашние бонусы
            if dxg_advantage >= 1.8:
                confidence += 0.05
            if home_shots_ratio >= 2.5:
                confidence += 0.04
                
            return SignalResult(
                strategy_name="home_win",
                signal_type="match_result",
                confidence=min(0.75, confidence),
                prediction="1",
                threshold_used=config.get("min_dxg_advantage", 1.2),
                reasoning=f"Домашнее превосходство: dxG+{dxg_advantage:.2f}, давление={home_pressure:.2f}",
                trigger_metrics={
                    "dxg_advantage": dxg_advantage, 
                    "home_momentum": metrics.momentum_home, 
                    "shots_ratio": home_shots_ratio
                },
                recommended_odds=self.default_odds["home_win"]
            )
        return None

    def analyze_away_win(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Победа гостей - эффективная игра в гостях"""
        config = self.config.get("away_win", {})
        
        dxg_advantage = metrics.dxg_away - metrics.dxg_home
        away_dangerous = match_data.get('dangerous_attacks_away', 0)
        home_defensive_errors = 1.0 - metrics.stability_home
        
        # Качество атак гостей
        away_attacks = match_data.get('attacks_away', 0)
        away_shots = match_data.get('shots_away', 0)
        away_efficiency = away_shots / max(away_attacks, 1) if away_attacks > 0 else 0
        
        conditions = []
        conditions.append(dxg_advantage >= config.get("min_dxg_advantage", 1.3))
        conditions.append(metrics.momentum_away >= config.get("min_away_momentum", 0.8))
        conditions.append(metrics.tiredness_away <= config.get("max_away_tiredness", 0.4))
        conditions.append(home_defensive_errors >= config.get("home_defensive_weakness", 0.3))
        conditions.append(away_dangerous >= config.get("min_away_dangerous_attacks", 4))
        conditions.append(away_efficiency >= 0.7)  # Эффективные контратаки
        conditions.append(away_attacks >= 8)  # Достаточная активность
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.50  # Победы гостей сложнее
            
            # Бонусы за качественную игру гостей
            if dxg_advantage >= 2.0:
                confidence += 0.06
            if away_efficiency >= 0.9:
                confidence += 0.05
                
            return SignalResult(
                strategy_name="away_win",
                signal_type="match_result",
                confidence=min(0.68, confidence),
                prediction="2",
                threshold_used=config.get("min_dxg_advantage", 1.3),
                reasoning=f"Эффективность гостей: dxG+{dxg_advantage:.2f}, опасные атаки={away_dangerous}",
                trigger_metrics={
                    "dxg_advantage": dxg_advantage, 
                    "away_momentum": metrics.momentum_away, 
                    "dangerous_attacks": float(away_dangerous)
                },
                recommended_odds=self.default_odds["away_win"]
            )
        return None

    def analyze_draw(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Ничья - равновесие команд"""
        config = self.config.get("draw", {})
        
        dxg_diff = abs(metrics.dxg_home - metrics.dxg_away)
        momentum_diff = abs(metrics.momentum_home - metrics.momentum_away)
        shots_diff = abs(match_data.get('shots_home', 0) - match_data.get('shots_away', 0))
        attacks_diff = abs(match_data.get('attacks_home', 0) - match_data.get('attacks_away', 0))
        
        # Средние показатели
        stability_avg = (metrics.stability_home + metrics.stability_away) / 2
        
        conditions = []
        conditions.append(dxg_diff <= config.get("max_dxg_difference", 0.25))
        conditions.append(stability_avg >= config.get("min_stability_both", 0.8))
        conditions.append(momentum_diff <= config.get("balanced_momentum_range", 0.2))
        conditions.append(shots_diff <= config.get("max_shots_difference", 3))
        conditions.append(attacks_diff <= 5)
        conditions.append(metrics.wave_amplitude <= 0.4)  # Спокойная игра
        conditions.append(max(metrics.tiredness_home, metrics.tiredness_away) >= 0.5)  # Усталость
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 6:  # Ничья требует больше условий
            confidence = (conditions_met / 7) * 0.40  # Самая сложная для предсказания
            
            # Бонусы за точное равенство
            if dxg_diff <= 0.15:
                confidence += 0.05
            if momentum_diff <= 0.1:
                confidence += 0.04
                
            return SignalResult(
                strategy_name="draw",
                signal_type="match_result",
                confidence=min(0.55, confidence),
                prediction="X",
                threshold_used=config.get("max_dxg_difference", 0.25),
                reasoning=f"Равенство команд: разница dxG={dxg_diff:.2f}, стабильность={stability_avg:.2f}",
                trigger_metrics={
                    "dxg_difference": dxg_diff, 
                    "stability_both": stability_avg, 
                    "momentum_range": momentum_diff
                },
                recommended_odds=self.default_odds["draw"]
            )
        return None

    def analyze_next_goal_home(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Следующий гол забьют хозяева - текущее давление"""
        config = self.config.get("next_goal_home", {})
        
        # Недавняя активность (более важна для next_goal)
        recent_factor = 1.0 if minute >= 15 else 0.8
        
        # Давление хозяев
        home_pressure = metrics.momentum_home * (1.1 - metrics.tiredness_home)
        recent_attacks = match_data.get('attacks_home', 0)
        
        # Уязвимость гостей
        away_vulnerability = 1.0 - metrics.stability_away
        
        conditions = []
        conditions.append(metrics.momentum_home >= config.get("min_home_momentum", 0.85))
        conditions.append(recent_attacks >= config.get("recent_attacks_home", 7) * recent_factor)
        conditions.append(metrics.stability_away <= config.get("low_away_stability", 0.25))
        conditions.append(home_pressure >= config.get("home_pressing", 0.7))
        conditions.append(metrics.gradient_home > metrics.gradient_away)
        conditions.append(away_vulnerability >= 0.6)
        conditions.append(match_data.get('dangerous_attacks_home', 0) >= 3)
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.55 * recent_factor
            
            # Бонусы за активное давление
            if home_pressure >= 0.85:
                confidence += 0.05
            if metrics.momentum_home >= 0.9:
                confidence += 0.04
                
            return SignalResult(
                strategy_name="next_goal_home",
                signal_type="next_goal",
                confidence=min(0.70, confidence),
                prediction="home_goal",
                threshold_used=config.get("min_home_momentum", 0.85),
                reasoning=f"Давление хозяев: моментум={metrics.momentum_home:.2f}, атаки={recent_attacks}",
                trigger_metrics={
                    "home_momentum": metrics.momentum_home, 
                    "recent_attacks": float(recent_attacks), 
                    "away_stability": metrics.stability_away
                },
                recommended_odds=self.default_odds["next_goal_home"]
            )
        return None

    def analyze_next_goal_away(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Следующий гол забьют гости - контратаки"""
        config = self.config.get("next_goal_away", {})
        
        # Эффективность контратак
        away_attacks = match_data.get('attacks_away', 0)
        away_shots = match_data.get('shots_away', 0)
        counter_efficiency = away_shots / max(away_attacks, 1) if away_attacks > 0 else 0
        
        # Скорость переходов
        transition_speed = metrics.momentum_away * (1.0 - metrics.stability_home)
        
        # Уязвимость хозяев при атаке
        home_open_defense = metrics.momentum_home * (1.0 - metrics.stability_home)
        
        conditions = []
        conditions.append(metrics.momentum_away >= config.get("min_away_momentum", 0.9))
        conditions.append(away_attacks >= config.get("recent_attacks_away", 6))
        conditions.append(metrics.stability_home <= config.get("low_home_stability", 0.2))
        conditions.append(counter_efficiency >= config.get("away_counter_efficiency", 0.8))
        conditions.append(transition_speed >= config.get("transition_speed", 0.75))
        conditions.append(home_open_defense >= 0.5)
        conditions.append(match_data.get('dangerous_attacks_away', 0) >= 2)
        
        conditions_met = sum(conditions)
        
        if conditions_met >= 5:
            confidence = (conditions_met / 7) * 0.50  # Гости сложнее
            
            # Бонусы за эффективные контратаки
            if counter_efficiency >= 1.0:
                confidence += 0.06
            if transition_speed >= 0.85:
                confidence += 0.05
                
            return SignalResult(
                strategy_name="next_goal_away",
                signal_type="next_goal",
                confidence=min(0.65, confidence),
                prediction="away_goal",
                threshold_used=config.get("min_away_momentum", 0.9),
                reasoning=f"Контратаки гостей: эффективность={counter_efficiency:.2f}, скорость={transition_speed:.2f}",
                trigger_metrics={
                    "away_momentum": metrics.momentum_away, 
                    "recent_attacks": float(away_attacks), 
                    "home_stability": metrics.stability_home
                },
                recommended_odds=self.default_odds["next_goal_away"]
            )
        return None