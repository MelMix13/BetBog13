import json
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
from logger import BetBogLogger

class SimpleOptimizer:
    """Simple statistical optimizer for betting strategies without ML dependencies"""
    
    def __init__(self):
        self.logger = BetBogLogger("OPTIMIZER")
        self.strategy_stats: Dict[str, Dict] = {}
        self.threshold_history: Dict[str, List[Dict]] = {}
        self.performance_history: Dict[str, List[Dict]] = {}
        
    async def optimize_strategy_thresholds(self, 
                                         strategy_name: str,
                                         historical_signals: List[Dict[str, Any]],
                                         min_samples: int = 30) -> Dict[str, float]:
        """Optimize strategy thresholds using statistical analysis"""
        
        if len(historical_signals) < min_samples:
            self.logger.warning(f"Not enough samples for {strategy_name}: {len(historical_signals)}")
            return {}
        
        try:
            # Analyze historical performance
            win_signals = [s for s in historical_signals if s.get('result') == 'win']
            loss_signals = [s for s in historical_signals if s.get('result') == 'loss']
            
            if not win_signals:
                self.logger.warning(f"No winning signals found for {strategy_name}")
                return {}
            
            # Calculate optimal thresholds based on winning patterns
            optimal_thresholds = self._calculate_statistical_thresholds(
                win_signals, loss_signals, strategy_name
            )
            
            # Store performance data
            self.strategy_stats[strategy_name] = {
                'win_rate': len(win_signals) / len(historical_signals),
                'total_signals': len(historical_signals),
                'avg_confidence_wins': statistics.mean([s.get('confidence', 0.5) for s in win_signals]),
                'avg_confidence_losses': statistics.mean([s.get('confidence', 0.5) for s in loss_signals]) if loss_signals else 0,
                'last_optimized': datetime.now().isoformat()
            }
            
            self.logger.success(f"Optimized {strategy_name}: {optimal_thresholds}")
            return optimal_thresholds
            
        except Exception as e:
            self.logger.error(f"Error optimizing {strategy_name}: {str(e)}")
            return {}
    
    def _calculate_statistical_thresholds(self, 
                                        win_signals: List[Dict], 
                                        loss_signals: List[Dict],
                                        strategy_name: str) -> Dict[str, float]:
        """Calculate optimal thresholds using statistical analysis"""
        
        thresholds = {}
        
        try:
            # Confidence threshold optimization
            win_confidences = [s.get('confidence', 0.5) for s in win_signals]
            loss_confidences = [s.get('confidence', 0.5) for s in loss_signals]
            
            if win_confidences and loss_confidences:
                # Find confidence threshold that maximizes precision
                avg_win_conf = statistics.mean(win_confidences)
                avg_loss_conf = statistics.mean(loss_confidences)
                
                # Set threshold slightly below average winning confidence
                optimal_confidence = max(0.6, avg_win_conf - 0.05)
                thresholds['min_confidence'] = round(optimal_confidence, 2)
            
            # Strategy-specific threshold optimization
            if strategy_name == 'dxg_spike':
                # Analyze dxG values from winning signals
                win_dxg_values = []
                for signal in win_signals:
                    metrics = signal.get('trigger_metrics', {})
                    total_dxg = metrics.get('total_dxg', 0)
                    if total_dxg > 0:
                        win_dxg_values.append(total_dxg)
                
                if win_dxg_values:
                    # Use 25th percentile of winning dxG values as threshold
                    sorted_values = sorted(win_dxg_values)
                    percentile_25 = sorted_values[len(sorted_values) // 4]
                    thresholds['threshold'] = round(max(0.1, percentile_25 * 0.8), 3)
                
            elif strategy_name == 'momentum_shift':
                # Analyze momentum differences
                win_momentum_diffs = []
                for signal in win_signals:
                    metrics = signal.get('trigger_metrics', {})
                    momentum_diff = metrics.get('momentum_diff', 0)
                    if momentum_diff > 0:
                        win_momentum_diffs.append(momentum_diff)
                
                if win_momentum_diffs:
                    avg_momentum = statistics.mean(win_momentum_diffs)
                    thresholds['threshold'] = round(max(0.15, avg_momentum * 0.7), 3)
                    
            elif strategy_name == 'tiredness_advantage':
                # Analyze tiredness differences
                win_tiredness_diffs = []
                for signal in win_signals:
                    metrics = signal.get('trigger_metrics', {})
                    tiredness_diff = metrics.get('tiredness_diff', 0)
                    if tiredness_diff > 0:
                        win_tiredness_diffs.append(tiredness_diff)
                
                if win_tiredness_diffs:
                    avg_tiredness = statistics.mean(win_tiredness_diffs)
                    thresholds['threshold'] = round(max(0.2, avg_tiredness * 0.8), 3)
            
            # Add time-based optimization
            win_minutes = [s.get('trigger_minute', 45) for s in win_signals]
            if win_minutes:
                optimal_min_minute = min(win_minutes) + 5  # Buffer
                optimal_max_minute = max(win_minutes) - 5  # Buffer
                thresholds['min_minute'] = max(15, optimal_min_minute)
                thresholds['max_minute'] = min(80, optimal_max_minute)
            
        except Exception as e:
            self.logger.error(f"Error calculating statistical thresholds: {str(e)}")
        
        return thresholds
    
    def predict_signal_success(self, 
                             strategy_name: str,
                             trigger_metrics: Dict[str, float],
                             confidence: float,
                             minute: int,
                             threshold: float) -> Tuple[float, str]:
        """Predict probability of signal success using statistical analysis"""
        
        stats = self.strategy_stats.get(strategy_name)
        if not stats:
            return confidence, "No historical data available"
        
        try:
            # Base prediction on historical win rate
            base_win_rate = stats.get('win_rate', 0.5)
            avg_win_confidence = stats.get('avg_confidence_wins', 0.7)
            avg_loss_confidence = stats.get('avg_confidence_losses', 0.5)
            
            # Adjust based on current confidence vs historical patterns
            if confidence >= avg_win_confidence:
                confidence_multiplier = 1.1
            elif confidence <= avg_loss_confidence:
                confidence_multiplier = 0.9
            else:
                confidence_multiplier = 1.0
            
            # Adjust based on timing (if historical data suggests optimal times)
            time_multiplier = 1.0
            if 30 <= minute <= 70:  # Prime time for most strategies
                time_multiplier = 1.05
            elif minute < 20 or minute > 80:  # Less reliable times
                time_multiplier = 0.95
            
            # Combine factors
            adjusted_confidence = confidence * confidence_multiplier * time_multiplier
            
            # Cap at reasonable bounds
            final_confidence = max(0.1, min(0.95, adjusted_confidence))
            
            explanation = f"Statistical prediction based on {stats['total_signals']} historical signals, {base_win_rate:.1%} win rate"
            
            return final_confidence, explanation
            
        except Exception as e:
            self.logger.error(f"Error in statistical prediction: {str(e)}")
            return confidence, f"Prediction failed: {str(e)}"
    
    def get_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """Get performance metrics for a strategy"""
        
        stats = self.strategy_stats.get(strategy_name, {})
        history = self.performance_history.get(strategy_name, [])
        
        if not stats:
            return {}
        
        return {
            'latest_performance': stats,
            'historical_data_points': len(history),
            'win_rate': stats.get('win_rate', 0),
            'total_signals': stats.get('total_signals', 0),
            'avg_confidence_wins': stats.get('avg_confidence_wins', 0),
            'last_optimized': stats.get('last_optimized', 'Never')
        }
    
    def save_models(self, filepath: str):
        """Save optimization data to file"""
        try:
            data = {
                'strategy_stats': self.strategy_stats,
                'threshold_history': self.threshold_history,
                'performance_history': self.performance_history,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.success(f"Optimization data saved to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error saving optimization data: {str(e)}")
    
    def load_models(self, filepath: str):
        """Load optimization data from file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.strategy_stats = data.get('strategy_stats', {})
            self.threshold_history = data.get('threshold_history', {})
            self.performance_history = data.get('performance_history', {})
            
            self.logger.success(f"Optimization data loaded from {filepath}")
            
        except FileNotFoundError:
            self.logger.info(f"No existing optimization data found at {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading optimization data: {str(e)}")