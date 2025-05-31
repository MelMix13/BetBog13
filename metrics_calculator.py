import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

@dataclass
class MatchMetrics:
    """Container for calculated match metrics"""
    dxg_home: float
    dxg_away: float
    gradient_home: float
    gradient_away: float
    wave_amplitude: float
    tiredness_home: float
    tiredness_away: float
    momentum_home: float
    momentum_away: float
    stability_home: float
    stability_away: float
    shots_per_attack_home: float
    shots_per_attack_away: float
    
    # Raw statistics needed by strategies
    attacks_home: int = 0
    attacks_away: int = 0
    shots_home: int = 0
    shots_away: int = 0
    corners_home: int = 0
    corners_away: int = 0
    possession_home: float = 50.0
    possession_away: float = 50.0
    dangerous_home: int = 0
    dangerous_away: int = 0
    goals_home: int = 0
    goals_away: int = 0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'dxg_home': self.dxg_home,
            'dxg_away': self.dxg_away,
            'gradient_home': self.gradient_home,
            'gradient_away': self.gradient_away,
            'wave_amplitude': self.wave_amplitude,
            'tiredness_home': self.tiredness_home,
            'tiredness_away': self.tiredness_away,
            'momentum_home': self.momentum_home,
            'momentum_away': self.momentum_away,
            'stability_home': self.stability_home,
            'stability_away': self.stability_away,
            'shots_per_attack_home': self.shots_per_attack_home,
            'shots_per_attack_away': self.shots_per_attack_away
        }

class MetricsCalculator:
    """Advanced metrics calculator for football matches"""
    
    def __init__(self):
        self.historical_data: Dict[str, List[Dict]] = {}
        
    def calculate_metrics(self, 
                         current_stats: Dict[str, Any],
                         historical_stats: List[Dict[str, Any]],
                         minute: int) -> MatchMetrics:
        """Calculate all derived metrics for current match state"""
        
        # Basic stats extraction
        shots_home = current_stats.get('shots_home', 0)
        shots_away = current_stats.get('shots_away', 0)
        attacks_home = current_stats.get('attacks_home', 0)
        attacks_away = current_stats.get('attacks_away', 0)
        possession_home = current_stats.get('possession_home', 50.0)
        possession_away = current_stats.get('possession_away', 50.0)
        dangerous_attacks_home = current_stats.get('dangerous_attacks_home', 0)
        dangerous_attacks_away = current_stats.get('dangerous_attacks_away', 0)
        corners_home = current_stats.get('corners_home', 0)
        corners_away = current_stats.get('corners_away', 0)
        
        # Calculate derived metrics
        dxg_home, dxg_away = self._calculate_dxg(
            shots_home, shots_away, attacks_home, attacks_away,
            dangerous_attacks_home, dangerous_attacks_away, minute
        )
        
        gradient_home, gradient_away = self._calculate_gradient(
            historical_stats, minute
        )
        
        wave_amplitude = self._calculate_wave_amplitude(historical_stats)
        
        tiredness_home, tiredness_away = self._calculate_tiredness(
            possession_home, possession_away, attacks_home, attacks_away, minute
        )
        
        momentum_home, momentum_away = self._calculate_momentum(
            historical_stats, minute
        )
        
        stability_home, stability_away = self._calculate_stability(
            historical_stats
        )
        
        shots_per_attack_home = self._calculate_shots_per_attack(shots_home, attacks_home)
        shots_per_attack_away = self._calculate_shots_per_attack(shots_away, attacks_away)
        
        return MatchMetrics(
            dxg_home=dxg_home,
            dxg_away=dxg_away,
            gradient_home=gradient_home,
            gradient_away=gradient_away,
            wave_amplitude=wave_amplitude,
            tiredness_home=tiredness_home,
            tiredness_away=tiredness_away,
            momentum_home=momentum_home,
            momentum_away=momentum_away,
            stability_home=stability_home,
            stability_away=stability_away,
            shots_per_attack_home=shots_per_attack_home,
            shots_per_attack_away=shots_per_attack_away,
            # Include raw statistics for strategies
            attacks_home=attacks_home,
            attacks_away=attacks_away,
            shots_home=shots_home,
            shots_away=shots_away,
            corners_home=corners_home,
            corners_away=corners_away,
            possession_home=possession_home,
            possession_away=possession_away,
            dangerous_home=dangerous_attacks_home,
            dangerous_away=dangerous_attacks_away,
            goals_home=stats.get('goals_home', 0),
            goals_away=stats.get('goals_away', 0)
        )
    
    def _calculate_dxg(self, 
                       shots_home: int, shots_away: int,
                       attacks_home: int, attacks_away: int,
                       dangerous_attacks_home: int, dangerous_attacks_away: int,
                       minute: int) -> Tuple[float, float]:
        """Calculate derived Expected Goals (dxG) based on shot quality and timing"""
        
        # Base xG calculation
        shot_quality_home = self._calculate_shot_quality(
            shots_home, attacks_home, dangerous_attacks_home
        )
        shot_quality_away = self._calculate_shot_quality(
            shots_away, attacks_away, dangerous_attacks_away
        )
        
        # Time-based modifiers
        time_modifier = self._get_time_modifier(minute)
        
        # Pressure factor (more shots in less time = higher quality)
        pressure_home = shots_home / max(minute, 1) * 90
        pressure_away = shots_away / max(minute, 1) * 90
        
        dxg_home = shot_quality_home * time_modifier * (1 + pressure_home * 0.1)
        dxg_away = shot_quality_away * time_modifier * (1 + pressure_away * 0.1)
        
        return round(dxg_home, 3), round(dxg_away, 3)
    
    def _calculate_shot_quality(self, shots: int, attacks: int, dangerous_attacks: int) -> float:
        """Calculate shot quality based on attack patterns"""
        if attacks == 0:
            return 0.0
            
        # Efficiency metrics
        shot_conversion = shots / max(attacks, 1)
        danger_ratio = dangerous_attacks / max(attacks, 1)
        
        # Quality formula
        base_quality = shot_conversion * 0.6 + danger_ratio * 0.4
        return min(base_quality * shots * 0.15, 3.0)  # Cap at 3.0 xG
    
    def _get_time_modifier(self, minute: int) -> float:
        """Get time-based modifier for xG calculation"""
        if minute < 15:
            return 0.8  # Lower in early game
        elif minute < 30:
            return 1.0  # Normal
        elif minute < 60:
            return 1.1  # Peak performance
        elif minute < 75:
            return 1.0  # Normal
        else:
            return 1.2  # Desperation/pressure time
    
    def _calculate_gradient(self, 
                           historical_stats: List[Dict[str, Any]], 
                           minute: int) -> Tuple[float, float]:
        """Calculate performance gradient (trend) over recent periods"""
        if len(historical_stats) < 3:
            return 0.0, 0.0
        
        # Get recent 10-minute window
        recent_stats = [s for s in historical_stats if s.get('minute', 0) >= minute - 10]
        
        if len(recent_stats) < 2:
            return 0.0, 0.0
        
        # Calculate gradients for key metrics
        home_shots = [s.get('shots_home', 0) for s in recent_stats]
        away_shots = [s.get('shots_away', 0) for s in recent_stats]
        
        gradient_home = self._calculate_trend(home_shots)
        gradient_away = self._calculate_trend(away_shots)
        
        return round(gradient_home, 3), round(gradient_away, 3)
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate trend using linear regression slope"""
        if len(values) < 2:
            return 0.0
            
        n = len(values)
        x = list(range(n))
        
        # Linear regression slope
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
            
        slope = numerator / denominator
        return slope
    
    def _calculate_wave_amplitude(self, historical_stats: List[Dict[str, Any]]) -> float:
        """Calculate wave amplitude of match intensity"""
        if len(historical_stats) < 5:
            return 0.0
        
        # Calculate intensity for each period
        intensities = []
        for stats in historical_stats:
            shots_total = stats.get('shots_home', 0) + stats.get('shots_away', 0)
            attacks_total = stats.get('attacks_home', 0) + stats.get('attacks_away', 0)
            intensity = shots_total + attacks_total * 0.3
            intensities.append(intensity)
        
        # Calculate amplitude as standard deviation
        if len(intensities) > 1:
            mean_intensity = sum(intensities) / len(intensities)
            variance = sum((x - mean_intensity) ** 2 for x in intensities) / len(intensities)
            amplitude = math.sqrt(variance)
            return round(amplitude, 3)
        
        return 0.0
    
    def _calculate_tiredness(self, 
                           possession_home: float, possession_away: float,
                           attacks_home: int, attacks_away: int, 
                           minute: int) -> Tuple[float, float]:
        """Calculate tiredness factor based on activity and time"""
        
        # Activity rate (attacks per minute)
        activity_home = attacks_home / max(minute, 1) * 90
        activity_away = attacks_away / max(minute, 1) * 90
        
        # Possession workload
        workload_home = possession_home * activity_home / 100
        workload_away = possession_away * activity_away / 100
        
        # Time factor (tiredness increases over time)
        time_factor = min(minute / 90, 1.0)
        
        tiredness_home = workload_home * time_factor * 0.01
        tiredness_away = workload_away * time_factor * 0.01
        
        return round(tiredness_home, 3), round(tiredness_away, 3)
    
    def _calculate_momentum(self, 
                          historical_stats: List[Dict[str, Any]], 
                          minute: int) -> Tuple[float, float]:
        """Calculate momentum based on recent performance changes"""
        if len(historical_stats) < 4:
            return 0.0, 0.0
        
        # Get last 5 minutes of data
        recent_window = [s for s in historical_stats if s.get('minute', 0) >= minute - 5]
        
        if len(recent_window) < 2:
            return 0.0, 0.0
        
        # Calculate momentum as rate of change in key metrics
        first_period = recent_window[0]
        last_period = recent_window[-1]
        
        # Change in attack intensity
        attack_change_home = (
            last_period.get('attacks_home', 0) - first_period.get('attacks_home', 0)
        )
        attack_change_away = (
            last_period.get('attacks_away', 0) - first_period.get('attacks_away', 0)
        )
        
        # Normalize by time
        time_diff = max(last_period.get('minute', 0) - first_period.get('minute', 0), 1)
        momentum_home = attack_change_home / time_diff
        momentum_away = attack_change_away / time_diff
        
        return round(momentum_home, 3), round(momentum_away, 3)
    
    def _calculate_stability(self, historical_stats: List[Dict[str, Any]]) -> Tuple[float, float]:
        """Calculate performance stability (consistency)"""
        if len(historical_stats) < 3:
            return 1.0, 1.0
        
        # Calculate coefficient of variation for key metrics
        home_attacks = [s.get('attacks_home', 0) for s in historical_stats]
        away_attacks = [s.get('attacks_away', 0) for s in historical_stats]
        
        stability_home = self._coefficient_of_variation(home_attacks)
        stability_away = self._coefficient_of_variation(away_attacks)
        
        # Convert to stability (inverse of variation)
        stability_home = max(1.0 - stability_home, 0.0)
        stability_away = max(1.0 - stability_away, 0.0)
        
        return round(stability_home, 3), round(stability_away, 3)
    
    def _coefficient_of_variation(self, values: List[float]) -> float:
        """Calculate coefficient of variation"""
        if not values or len(values) < 2:
            return 0.0
            
        mean_val = sum(values) / len(values)
        if mean_val == 0:
            return 0.0
            
        variance = sum((x - mean_val) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance)
        
        return std_dev / mean_val
    
    def _calculate_shots_per_attack(self, shots: int, attacks: int) -> float:
        """Calculate shots per attack ratio"""
        if attacks == 0:
            return 0.0
        return round(shots / attacks, 3)
    
    def detect_significant_changes(self, 
                                 current_metrics: MatchMetrics,
                                 previous_metrics: Optional[MatchMetrics],
                                 thresholds: Dict[str, float]) -> Dict[str, bool]:
        """Detect significant changes in metrics that might trigger signals"""
        
        if not previous_metrics:
            return {}
        
        changes = {}
        
        # dxG spike detection
        dxg_change_home = abs(current_metrics.dxg_home - previous_metrics.dxg_home)
        dxg_change_away = abs(current_metrics.dxg_away - previous_metrics.dxg_away)
        changes['dxg_spike'] = max(dxg_change_home, dxg_change_away) > thresholds.get('dxg_spike', 0.15)
        
        # Momentum shift detection
        momentum_change_home = abs(current_metrics.momentum_home - previous_metrics.momentum_home)
        momentum_change_away = abs(current_metrics.momentum_away - previous_metrics.momentum_away)
        changes['momentum_shift'] = max(momentum_change_home, momentum_change_away) > thresholds.get('momentum_shift', 0.25)
        
        # Tiredness advantage detection
        tiredness_diff = abs(current_metrics.tiredness_home - current_metrics.tiredness_away)
        changes['tiredness_advantage'] = tiredness_diff > thresholds.get('tiredness_advantage', 0.3)
        
        # Gradient change detection
        gradient_change_home = abs(current_metrics.gradient_home - previous_metrics.gradient_home)
        gradient_change_away = abs(current_metrics.gradient_away - previous_metrics.gradient_away)
        changes['gradient_change'] = max(gradient_change_home, gradient_change_away) > thresholds.get('gradient_change', 0.2)
        
        return changes
