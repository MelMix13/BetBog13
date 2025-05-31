from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import math
from metrics_calculator import MatchMetrics
from logger import BetBogLogger

@dataclass
class SignalResult:
    """Result of strategy analysis"""
    strategy_name: str
    signal_type: str
    confidence: float
    prediction: str
    threshold_used: float
    reasoning: str
    trigger_metrics: Dict[str, float]
    recommended_odds: float = 0.0
    stake_multiplier: float = 1.0

class BettingStrategies:
    """Advanced betting strategies with adaptive thresholds"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = BetBogLogger("STRATEGIES")
        self.strategies = {
            "over_2_5_goals": self.analyze_over_2_5_goals,
            "under_2_5_goals": self.analyze_under_2_5_goals,
            "momentum_shift": self.analyze_momentum_shift,
            "next_goal_away": self.analyze_next_goal_away
        }
    
    def analyze_all_strategies(self, 
                             current_metrics: MatchMetrics,
                             match_data: Dict[str, Any],
                             minute: int) -> List[SignalResult]:
        """Analyze all strategies and return signals"""
        signals = []
        
        for strategy_name, strategy_func in self.strategies.items():
            try:
                result = strategy_func(current_metrics, match_data, minute)
                if result and result.confidence > 0.5:  # Minimum confidence threshold
                    signals.append(result)
                    self.logger.info(f"Signal generated: {strategy_name} - {result.confidence:.2f}")
            except Exception as e:
                self.logger.error(f"Error in strategy {strategy_name}: {str(e)}")
        
        return signals
    
    def analyze_over_2_5_goals(self, metrics: MatchMetrics, match_data: Dict[str, Any], minute: int) -> Optional[SignalResult]:
        """Analyze sudden spikes in derived xG for over/under signals"""
        
        config = self.config.get("dxg_spike", {})
        threshold = config.get("threshold", 0.15)
        min_confidence = config.get("min_confidence", 0.7)
        
        # Calculate total dxG and spike intensity
        total_dxg = metrics.dxg_home + metrics.dxg_away
        dxg_imbalance = abs(metrics.dxg_home - metrics.dxg_away)
        
        # Check for significant dxG levels
        if total_dxg > threshold and minute > 20:
            # Determine signal type based on dxG level and match context
            if total_dxg > 1.5 and minute < 70:
                signal_type = "over_2.5"
                confidence = min(0.9, 0.5 + (total_dxg - 1.5) * 0.3)
            elif total_dxg > 1.0 and minute < 60:
                signal_type = "over_1.5"
                confidence = min(0.85, 0.5 + (total_dxg - 1.0) * 0.4)
            elif total_dxg > 0.8 and dxg_imbalance > 0.3:
                signal_type = "btts"  # Both teams to score
                confidence = min(0.8, 0.5 + dxg_imbalance * 0.5)
            else:
                return None
            
            # Adjust confidence based on time and momentum
            time_factor = self._get_time_confidence_factor(minute)
            momentum_factor = (abs(metrics.momentum_home) + abs(metrics.momentum_away)) * 0.1
            
            final_confidence = confidence * time_factor * (1 + momentum_factor)
            
            if final_confidence >= min_confidence:
                return SignalResult(
                    strategy_name="dxg_spike",
                    signal_type=signal_type,
                    confidence=round(final_confidence, 3),
                    prediction=signal_type.replace("_", " ").title(),
                    threshold_used=threshold,
                    reasoning=f"dxG spike detected: {total_dxg:.2f} total, imbalance: {dxg_imbalance:.2f}",
                    trigger_metrics={
                        "total_dxg": total_dxg,
                        "dxg_imbalance": dxg_imbalance,
                        "minute": minute
                    },
                    recommended_odds=self._calculate_recommended_odds(signal_type, final_confidence),
                    stake_multiplier=min(2.0, final_confidence + 0.5)
                )
        
        return None

    def analyze_under_2_5_goals(self, 
                              metrics: MatchMetrics, 
                              match_data: Dict[str, Any], 
                              minute: int) -> Optional[SignalResult]:
        """Analyze under 2.5 goals signal - defensive play"""
        
        config = self.config.get("under_2_5_goals", {})
        threshold = config.get("threshold", 0.6)
        min_confidence = config.get("min_confidence", 0.65)
        
        # Check for defensive indicators
        total_attacks = metrics.attacks_home + metrics.attacks_away
        total_shots = metrics.shots_home + metrics.shots_away
        total_dxg = metrics.dxg_home + metrics.dxg_away
        
        # Low attacking activity suggests under 2.5
        attacking_factor = 1.0 - min(1.0, (total_attacks / 20.0 + total_shots / 15.0) / 2.0)
        dxg_factor = 1.0 - min(1.0, total_dxg / 2.5)
        
        confidence = (attacking_factor * 0.6 + dxg_factor * 0.4)
        
        if confidence >= threshold:
            time_factor = self._get_time_confidence_factor(minute)
            final_confidence = confidence * time_factor
            
            if final_confidence >= min_confidence:
                return SignalResult(
                    strategy_name="under_2_5_goals",
                    signal_type="under_2_5",
                    confidence=round(final_confidence, 3),
                    prediction="Under 2.5 Goals",
                    threshold_used=threshold,
                    reasoning=f"Low attacking activity: {total_attacks} attacks, {total_shots} shots, {total_dxg:.2f} dxG",
                    trigger_metrics={
                        "total_attacks": total_attacks,
                        "total_shots": total_shots,
                        "total_dxg": total_dxg,
                        "minute": minute
                    },
                    recommended_odds=self._calculate_recommended_odds("under_2_5", final_confidence),
                    stake_multiplier=min(1.8, final_confidence + 0.3)
                )
        
        return None
    
    def analyze_momentum_shift(self, 
                             metrics: MatchMetrics, 
                             match_data: Dict[str, Any], 
                             minute: int) -> Optional[SignalResult]:
        """Analyze momentum shifts for next goal predictions"""
        
        config = self.config.get("momentum_shift", {})
        threshold = config.get("threshold", 0.25)
        stability_factor = config.get("stability_factor", 0.8)
        
        momentum_home = metrics.momentum_home
        momentum_away = metrics.momentum_away
        momentum_diff = abs(momentum_home - momentum_away)
        
        # Check for significant momentum shift
        if momentum_diff > threshold and minute > 15:
            leading_team = "home" if momentum_home > momentum_away else "away"
            momentum_strength = max(abs(momentum_home), abs(momentum_away))
            
            # Calculate confidence based on momentum strength and stability
            base_confidence = min(0.9, 0.4 + momentum_strength * 0.3)
            stability_avg = (metrics.stability_home + metrics.stability_away) / 2
            
            if stability_avg < stability_factor:  # Lower stability = more volatile = higher chance of goals
                confidence_multiplier = 1.2
            else:
                confidence_multiplier = 1.0
            
            final_confidence = base_confidence * confidence_multiplier
            
            # Determine signal type
            current_score = match_data.get('home_score', 0) + match_data.get('away_score', 0)
            
            if momentum_strength > 0.5 and current_score == 0:
                signal_type = "first_goal"
                prediction = f"First goal by {leading_team} team"
            elif momentum_strength > 0.3:
                signal_type = "next_goal"
                prediction = f"Next goal by {leading_team} team"
            else:
                return None
            
            if final_confidence >= 0.6:
                return SignalResult(
                    strategy_name="momentum_shift",
                    signal_type=signal_type,
                    confidence=round(final_confidence, 3),
                    prediction=prediction,
                    threshold_used=threshold,
                    reasoning=f"Momentum shift: {leading_team} team leading with {momentum_strength:.2f}",
                    trigger_metrics={
                        "momentum_home": momentum_home,
                        "momentum_away": momentum_away,
                        "momentum_diff": momentum_diff,
                        "leading_team": leading_team
                    },
                    recommended_odds=self._calculate_recommended_odds(signal_type, final_confidence)
                )
        
        return None
    
    def analyze_tiredness_advantage(self, 
                                  metrics: MatchMetrics, 
                                  match_data: Dict[str, Any], 
                                  minute: int) -> Optional[SignalResult]:
        """Analyze tiredness differences for late game opportunities"""
        
        config = self.config.get("tiredness_advantage", {})
        threshold = config.get("threshold", 0.3)
        gradient_factor = config.get("gradient_factor", 0.2)
        
        if minute < 60:  # Only relevant in later stages
            return None
        
        tiredness_diff = abs(metrics.tiredness_home - metrics.tiredness_away)
        
        if tiredness_diff > threshold:
            less_tired_team = "home" if metrics.tiredness_home < metrics.tiredness_away else "away"
            advantage_magnitude = tiredness_diff
            
            # Factor in gradient (team getting stronger vs weaker)
            gradient_home = metrics.gradient_home
            gradient_away = metrics.gradient_away
            
            if less_tired_team == "home" and gradient_home > gradient_factor:
                confidence_boost = 0.2
            elif less_tired_team == "away" and gradient_away > gradient_factor:
                confidence_boost = 0.2
            else:
                confidence_boost = 0.0
            
            base_confidence = 0.5 + advantage_magnitude
            final_confidence = min(0.9, base_confidence + confidence_boost)
            
            # Late game time boost
            late_game_boost = (minute - 60) / 30 * 0.1
            final_confidence += late_game_boost
            
            if final_confidence >= 0.65:
                return SignalResult(
                    strategy_name="tiredness_advantage",
                    signal_type="late_goal",
                    confidence=round(final_confidence, 3),
                    prediction=f"Late goal by {less_tired_team} team",
                    threshold_used=threshold,
                    reasoning=f"Tiredness advantage: {less_tired_team} team less tired by {advantage_magnitude:.2f}",
                    trigger_metrics={
                        "tiredness_home": metrics.tiredness_home,
                        "tiredness_away": metrics.tiredness_away,
                        "tiredness_diff": tiredness_diff,
                        "advantage_team": less_tired_team
                    },
                    recommended_odds=self._calculate_recommended_odds("late_goal", final_confidence)
                )
        
        return None
    
    def analyze_shots_efficiency(self, 
                               metrics: MatchMetrics, 
                               match_data: Dict[str, Any], 
                               minute: int) -> Optional[SignalResult]:
        """Analyze shots per attack efficiency for scoring predictions"""
        
        if minute < 25:  # Need enough data
            return None
        
        spa_home = metrics.shots_per_attack_home
        spa_away = metrics.shots_per_attack_away
        
        # High efficiency threshold
        high_efficiency_threshold = 0.4
        
        if spa_home > high_efficiency_threshold or spa_away > high_efficiency_threshold:
            efficient_team = "home" if spa_home > spa_away else "away"
            max_efficiency = max(spa_home, spa_away)
            
            # Check if team also has momentum
            momentum_home = abs(metrics.momentum_home)
            momentum_away = abs(metrics.momentum_away)
            
            if efficient_team == "home" and momentum_home > 0.2:
                confidence = 0.6 + max_efficiency * 0.5 + momentum_home * 0.2
            elif efficient_team == "away" and momentum_away > 0.2:
                confidence = 0.6 + max_efficiency * 0.5 + momentum_away * 0.2
            else:
                confidence = 0.5 + max_efficiency * 0.3
            
            final_confidence = min(0.88, confidence)
            
            if final_confidence >= 0.6:
                return SignalResult(
                    strategy_name="shots_efficiency",
                    signal_type="team_to_score",
                    confidence=round(final_confidence, 3),
                    prediction=f"{efficient_team.title()} team to score",
                    threshold_used=high_efficiency_threshold,
                    reasoning=f"High shots efficiency: {efficient_team} team {max_efficiency:.2f} shots/attack",
                    trigger_metrics={
                        "spa_home": spa_home,
                        "spa_away": spa_away,
                        "efficient_team": efficient_team,
                        "max_efficiency": max_efficiency
                    },
                    recommended_odds=self._calculate_recommended_odds("team_to_score", final_confidence)
                )
        
        return None
    
    def analyze_wave_pattern(self, 
                           metrics: MatchMetrics, 
                           match_data: Dict[str, Any], 
                           minute: int) -> Optional[SignalResult]:
        """Analyze wave patterns for intensity-based predictions"""
        
        wave_amplitude = metrics.wave_amplitude
        
        if wave_amplitude > 2.0 and minute > 20:  # High volatility match
            # High amplitude suggests unpredictable, goal-rich match
            total_goals = match_data.get('home_score', 0) + match_data.get('away_score', 0)
            
            if total_goals < 2:  # Still room for more goals
                confidence = 0.55 + (wave_amplitude - 2.0) * 0.1
                confidence = min(0.8, confidence)
                
                return SignalResult(
                    strategy_name="wave_pattern",
                    signal_type="over_2.5" if total_goals <= 1 else "over_3.5",
                    confidence=round(confidence, 3),
                    prediction="Over 2.5 goals" if total_goals <= 1 else "Over 3.5 goals",
                    threshold_used=2.0,
                    reasoning=f"High wave amplitude {wave_amplitude:.2f} indicates volatile match",
                    trigger_metrics={
                        "wave_amplitude": wave_amplitude,
                        "current_goals": total_goals,
                        "minute": minute
                    },
                    recommended_odds=self._calculate_recommended_odds("over_goals", confidence)
                )
        
        return None
    
    def analyze_gradient_breakout(self, 
                                metrics: MatchMetrics, 
                                match_data: Dict[str, Any], 
                                minute: int) -> Optional[SignalResult]:
        """Analyze gradient breakouts for trend continuation"""
        
        gradient_home = metrics.gradient_home
        gradient_away = metrics.gradient_away
        
        strong_gradient_threshold = 0.3
        
        if abs(gradient_home) > strong_gradient_threshold or abs(gradient_away) > strong_gradient_threshold:
            if abs(gradient_home) > abs(gradient_away):
                trending_team = "home"
                gradient_strength = abs(gradient_home)
                trend_direction = "up" if gradient_home > 0 else "down"
            else:
                trending_team = "away"
                gradient_strength = abs(gradient_away)
                trend_direction = "up" if gradient_away > 0 else "down"
            
            if trend_direction == "up":  # Positive trend
                confidence = 0.55 + gradient_strength * 0.4
                confidence = min(0.85, confidence)
                
                return SignalResult(
                    strategy_name="gradient_breakout",
                    signal_type="team_performance",
                    confidence=round(confidence, 3),
                    prediction=f"{trending_team.title()} team strong trend",
                    threshold_used=strong_gradient_threshold,
                    reasoning=f"Strong upward gradient {gradient_strength:.2f} for {trending_team}",
                    trigger_metrics={
                        "gradient_home": gradient_home,
                        "gradient_away": gradient_away,
                        "trending_team": trending_team,
                        "gradient_strength": gradient_strength
                    },
                    recommended_odds=self._calculate_recommended_odds("team_performance", confidence)
                )
        
        return None
    
    def analyze_stability_disruption(self, 
                                   metrics: MatchMetrics, 
                                   match_data: Dict[str, Any], 
                                   minute: int) -> Optional[SignalResult]:
        """Analyze stability disruptions for chaos-based predictions"""
        
        stability_home = metrics.stability_home
        stability_away = metrics.stability_away
        avg_stability = (stability_home + stability_away) / 2
        
        low_stability_threshold = 0.3
        
        if avg_stability < low_stability_threshold and minute > 30:
            # Low stability = chaotic match = more goals likely
            chaos_level = 1.0 - avg_stability
            confidence = 0.5 + chaos_level * 0.3
            
            # Factor in current goal situation
            total_goals = match_data.get('home_score', 0) + match_data.get('away_score', 0)
            
            if total_goals == 0:
                signal_type = "btts"
                prediction = "Both teams to score"
            elif total_goals == 1:
                signal_type = "over_2.5"
                prediction = "Over 2.5 goals"
            else:
                signal_type = "over_3.5"
                prediction = "Over 3.5 goals"
            
            final_confidence = min(0.8, confidence)
            
            if final_confidence >= 0.6:
                return SignalResult(
                    strategy_name="stability_disruption",
                    signal_type=signal_type,
                    confidence=round(final_confidence, 3),
                    prediction=prediction,
                    threshold_used=low_stability_threshold,
                    reasoning=f"Low stability {avg_stability:.2f} indicates chaotic match",
                    trigger_metrics={
                        "stability_home": stability_home,
                        "stability_away": stability_away,
                        "avg_stability": avg_stability,
                        "chaos_level": chaos_level
                    },
                    recommended_odds=self._calculate_recommended_odds(signal_type, final_confidence)
                )
        
        return None

    def analyze_next_goal_away(self, 
                             metrics: MatchMetrics, 
                             match_data: Dict[str, Any], 
                             minute: int) -> Optional[SignalResult]:
        """Analyze away team next goal prediction"""
        
        config = self.config.get("next_goal_away", {})
        threshold = config.get("threshold", 0.7)
        min_confidence = config.get("min_confidence", 0.65)
        
        # Analyze away team momentum and attacking metrics
        away_momentum = metrics.momentum_away
        away_efficiency = metrics.shots_per_attack_away
        momentum_diff = metrics.momentum_away - metrics.momentum_home
        
        confidence = 0.0
        
        # Strong away momentum suggests next goal
        if away_momentum > 0.3 and momentum_diff > 0.15:
            confidence += 0.4
        
        # High away efficiency
        if away_efficiency > 0.3:
            confidence += 0.3
        
        # Away pressure indicators
        if metrics.attacks_away > metrics.attacks_home * 1.2:
            confidence += 0.2
            
        if metrics.shots_away > metrics.shots_home:
            confidence += 0.1
        
        if confidence >= threshold:
            time_factor = self._get_time_confidence_factor(minute)
            final_confidence = confidence * time_factor
            
            if final_confidence >= min_confidence:
                return SignalResult(
                    strategy_name="next_goal_away",
                    signal_type="next_goal_away",
                    confidence=round(final_confidence, 3),
                    prediction="Next Goal: Away Team",
                    threshold_used=threshold,
                    reasoning=f"Away momentum: {away_momentum:.2f}, efficiency: {away_efficiency:.2f}",
                    trigger_metrics={
                        "away_momentum": away_momentum,
                        "away_efficiency": away_efficiency,
                        "momentum_diff": momentum_diff,
                        "minute": minute
                    },
                    recommended_odds=self._calculate_recommended_odds("next_goal_away", final_confidence),
                    stake_multiplier=min(1.5, final_confidence + 0.2)
                )
        
        return None
    
    def _get_time_confidence_factor(self, minute: int) -> float:
        """Get time-based confidence factor"""
        if minute < 20:
            return 0.7  # Lower confidence early
        elif minute < 45:
            return 1.0  # Peak confidence
        elif minute < 70:
            return 0.9  # Slightly lower
        else:
            return 1.1  # Higher in late game
    
    def _calculate_recommended_odds(self, signal_type: str, confidence: float) -> float:
        """Calculate recommended minimum odds based on confidence"""
        # Convert confidence to implied probability and add margin
        implied_prob = confidence
        fair_odds = 1.0 / implied_prob
        
        # Add safety margin (10-20%)
        margin = 0.15 if confidence > 0.8 else 0.1
        recommended_odds = fair_odds * (1 + margin)
        
        return round(recommended_odds, 2)
    
    def update_strategy_config(self, strategy_name: str, new_config: Dict[str, Any]):
        """Update configuration for a specific strategy"""
        if strategy_name in self.config:
            self.config[strategy_name].update(new_config)
            self.logger.info(f"Updated config for {strategy_name}: {new_config}")
        else:
            self.logger.warning(f"Strategy {strategy_name} not found in config")
