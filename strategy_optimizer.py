"""
Индивидуальная адаптация стратегий на основе результатов
"""
import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import asyncpg
from config import Config
from logger import BetBogLogger

class StrategyOptimizer:
    """Оптимизатор стратегий с индивидуальной адаптацией"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("STRATEGY_OPTIMIZER")
        
        # Параметры адаптации для каждой стратегии
        self.adaptation_rules = {
            "over_2_5_goals": {
                "primary_metrics": ["dxg_combined", "attacks_total", "shots_total"],
                "adjustment_factor": 0.15,
                "min_samples": 20,
                "target_accuracy": 0.65
            },
            "under_2_5_goals": {
                "primary_metrics": ["dxg_combined", "stability_both", "shots_per_attack"],
                "adjustment_factor": 0.12,
                "min_samples": 25,
                "target_accuracy": 0.70
            },
            "btts_yes": {
                "primary_metrics": ["dxg_both_teams", "shots_both", "momentum_both"],
                "adjustment_factor": 0.18,
                "min_samples": 15,
                "target_accuracy": 0.62
            },
            "btts_no": {
                "primary_metrics": ["dxg_weaker", "stability_stronger", "away_shots"],
                "adjustment_factor": 0.20,
                "min_samples": 18,
                "target_accuracy": 0.68
            },
            "home_win": {
                "primary_metrics": ["dxg_advantage", "home_momentum", "shots_ratio"],
                "adjustment_factor": 0.16,
                "min_samples": 22,
                "target_accuracy": 0.58
            },
            "away_win": {
                "primary_metrics": ["dxg_advantage", "away_momentum", "dangerous_attacks"],
                "adjustment_factor": 0.18,
                "min_samples": 20,
                "target_accuracy": 0.55
            },
            "draw": {
                "primary_metrics": ["dxg_difference", "stability_both", "momentum_range"],
                "adjustment_factor": 0.10,
                "min_samples": 30,
                "target_accuracy": 0.45
            },
            "next_goal_home": {
                "primary_metrics": ["home_momentum", "recent_attacks", "away_stability"],
                "adjustment_factor": 0.25,
                "min_samples": 12,
                "target_accuracy": 0.60
            },
            "next_goal_away": {
                "primary_metrics": ["away_momentum", "recent_attacks", "home_stability"],
                "adjustment_factor": 0.25,
                "min_samples": 12,
                "target_accuracy": 0.58
            }
        }
    
    async def get_db_connection(self):
        """Получение подключения к базе данных"""
        try:
            return await asyncpg.connect(self.config.DATABASE_URL)
        except Exception as e:
            self.logger.error(f"Ошибка подключения к БД: {e}")
            return None
    
    async def analyze_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """Анализ результативности стратегии"""
        conn = await self.get_db_connection()
        if not conn:
            return {}
        
        try:
            # Получаем результаты за последние 30 дней
            query = """
            SELECT result, confidence, trigger_metrics, created_at
            FROM signals 
            WHERE strategy_name = $1 
            AND created_at >= $2 
            AND result IS NOT NULL
            ORDER BY created_at DESC
            """
            
            since_date = datetime.now() - timedelta(days=30)
            results = await conn.fetch(query, strategy_name, since_date)
            
            if len(results) < self.adaptation_rules[strategy_name]["min_samples"]:
                return {"status": "insufficient_data", "samples": len(results)}
            
            # Анализируем результаты
            wins = sum(1 for r in results if r['result'] == 'win')
            total = len(results)
            current_accuracy = wins / total if total > 0 else 0
            
            # Анализируем конфиденция vs результат
            confidence_analysis = self._analyze_confidence_correlation(results)
            
            # Анализируем триггерные метрики
            metrics_analysis = self._analyze_trigger_metrics(results, strategy_name)
            
            return {
                "status": "sufficient_data",
                "total_signals": total,
                "wins": wins,
                "current_accuracy": current_accuracy,
                "target_accuracy": self.adaptation_rules[strategy_name]["target_accuracy"],
                "confidence_analysis": confidence_analysis,
                "metrics_analysis": metrics_analysis,
                "needs_adjustment": abs(current_accuracy - self.adaptation_rules[strategy_name]["target_accuracy"]) > 0.05
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа стратегии {strategy_name}: {e}")
            return {}
        finally:
            await conn.close()
    
    def _analyze_confidence_correlation(self, results: List[Dict]) -> Dict[str, Any]:
        """Анализ корреляции между confidence и результатом"""
        if not results:
            return {}
        
        high_conf_results = [r for r in results if r.get('confidence', 0) >= 0.8]
        low_conf_results = [r for r in results if r.get('confidence', 0) < 0.6]
        
        high_conf_accuracy = 0
        low_conf_accuracy = 0
        
        if high_conf_results:
            high_conf_wins = sum(1 for r in high_conf_results if r['result'] == 'win')
            high_conf_accuracy = high_conf_wins / len(high_conf_results)
        
        if low_conf_results:
            low_conf_wins = sum(1 for r in low_conf_results if r['result'] == 'win')
            low_conf_accuracy = low_conf_wins / len(low_conf_results)
        
        return {
            "high_confidence_accuracy": high_conf_accuracy,
            "low_confidence_accuracy": low_conf_accuracy,
            "confidence_correlation": high_conf_accuracy - low_conf_accuracy
        }
    
    def _analyze_trigger_metrics(self, results: List[Dict], strategy_name: str) -> Dict[str, Any]:
        """Анализ триггерных метрик для выявления паттернов"""
        if not results:
            return {}
        
        primary_metrics = self.adaptation_rules[strategy_name]["primary_metrics"]
        metrics_performance = {}
        
        for metric in primary_metrics:
            wins_with_metric = []
            losses_with_metric = []
            
            for result in results:
                if result.get('trigger_metrics'):
                    try:
                        metrics = json.loads(result['trigger_metrics']) if isinstance(result['trigger_metrics'], str) else result['trigger_metrics']
                        if metric in metrics:
                            if result['result'] == 'win':
                                wins_with_metric.append(metrics[metric])
                            else:
                                losses_with_metric.append(metrics[metric])
                    except:
                        continue
            
            if wins_with_metric and losses_with_metric:
                avg_win_value = sum(wins_with_metric) / len(wins_with_metric)
                avg_loss_value = sum(losses_with_metric) / len(losses_with_metric)
                
                metrics_performance[metric] = {
                    "avg_win_value": avg_win_value,
                    "avg_loss_value": avg_loss_value,
                    "difference": avg_win_value - avg_loss_value,
                    "win_samples": len(wins_with_metric),
                    "loss_samples": len(losses_with_metric)
                }
        
        return metrics_performance
    
    async def adapt_strategy_thresholds(self, strategy_name: str) -> bool:
        """Адаптация порогов стратегии на основе анализа"""
        analysis = await self.analyze_strategy_performance(strategy_name)
        
        if analysis.get("status") != "sufficient_data" or not analysis.get("needs_adjustment"):
            return False
        
        conn = await self.get_db_connection()
        if not conn:
            return False
        
        try:
            # Получаем текущую конфигурацию
            current_config = await conn.fetchval(
                "SELECT config FROM strategy_configs WHERE strategy_name = $1",
                strategy_name
            )
            
            if not current_config:
                return False
            
            config_dict = json.loads(current_config) if isinstance(current_config, str) else current_config
            
            # Применяем адаптацию
            adjusted_config = self._adjust_config(config_dict, analysis, strategy_name)
            
            # Сохраняем обновленную конфигурацию
            await conn.execute(
                """UPDATE strategy_configs 
                   SET config = $1, last_optimized = $2 
                   WHERE strategy_name = $3""",
                json.dumps(adjusted_config),
                datetime.now(),
                strategy_name
            )
            
            self.logger.ml_update(
                strategy_name,
                {
                    "old_accuracy": analysis["current_accuracy"],
                    "target_accuracy": analysis["target_accuracy"],
                    "adjustments_made": len(adjusted_config)
                },
                f"Адаптированы пороги для повышения точности"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка адаптации стратегии {strategy_name}: {e}")
            return False
        finally:
            await conn.close()
    
    def _adjust_config(self, config: Dict[str, Any], analysis: Dict[str, Any], strategy_name: str) -> Dict[str, Any]:
        """Корректировка конфигурации на основе анализа"""
        adjusted_config = config.copy()
        adjustment_factor = self.adaptation_rules[strategy_name]["adjustment_factor"]
        current_accuracy = analysis["current_accuracy"]
        target_accuracy = analysis["target_accuracy"]
        
        # Определяем направление корректировки
        if current_accuracy < target_accuracy:
            # Нужно повысить точность - делаем критерии строже
            multiplier = 1 + adjustment_factor
        else:
            # Можно ослабить критерии для большего количества сигналов
            multiplier = 1 - adjustment_factor
        
        # Корректируем метрики на основе анализа
        metrics_analysis = analysis.get("metrics_analysis", {})
        
        for metric_key, metric_data in metrics_analysis.items():
            if metric_data.get("difference", 0) != 0:
                # Находим соответствующий параметр в конфигурации
                config_key = self._map_metric_to_config_key(metric_key, strategy_name)
                
                if config_key in adjusted_config:
                    old_value = adjusted_config[config_key]
                    
                    if metric_data["difference"] > 0:
                        # Победные значения выше - увеличиваем порог
                        adjusted_config[config_key] = old_value * multiplier
                    else:
                        # Победные значения ниже - уменьшаем порог
                        adjusted_config[config_key] = old_value / multiplier
                    
                    # Ограничиваем экстремальные значения
                    adjusted_config[config_key] = max(0.1, min(10.0, adjusted_config[config_key]))
        
        return adjusted_config
    
    def _map_metric_to_config_key(self, metric: str, strategy_name: str) -> str:
        """Маппинг метрики на ключ конфигурации"""
        mapping = {
            "over_2_5_goals": {
                "dxg_combined": "min_dxg_combined",
                "attacks_total": "min_attacks_total",
                "shots_total": "min_shots_total"
            },
            "under_2_5_goals": {
                "dxg_combined": "max_dxg_combined",
                "stability_both": "min_stability_both",
                "shots_per_attack": "max_shots_per_attack"
            },
            "btts_yes": {
                "dxg_both_teams": "min_dxg_both_teams",
                "shots_both": "min_shots_both",
                "momentum_both": "min_momentum_both"
            },
            "btts_no": {
                "dxg_weaker": "max_dxg_weaker",
                "stability_stronger": "min_stability_stronger",
                "away_shots": "max_away_shots"
            },
            "home_win": {
                "dxg_advantage": "min_dxg_advantage",
                "home_momentum": "min_home_momentum",
                "shots_ratio": "min_home_shots_ratio"
            },
            "away_win": {
                "dxg_advantage": "min_dxg_advantage",
                "away_momentum": "min_away_momentum",
                "dangerous_attacks": "min_away_dangerous_attacks"
            },
            "draw": {
                "dxg_difference": "max_dxg_difference",
                "stability_both": "min_stability_both",
                "momentum_range": "balanced_momentum_range"
            },
            "next_goal_home": {
                "home_momentum": "min_home_momentum",
                "recent_attacks": "recent_attacks_home",
                "away_stability": "low_away_stability"
            },
            "next_goal_away": {
                "away_momentum": "min_away_momentum",
                "recent_attacks": "recent_attacks_away",
                "home_stability": "low_home_stability"
            }
        }
        
        return mapping.get(strategy_name, {}).get(metric, metric)
    
    async def optimize_all_strategies(self):
        """Оптимизация всех стратегий"""
        strategies = list(self.adaptation_rules.keys())
        optimized_count = 0
        
        for strategy_name in strategies:
            try:
                if await self.adapt_strategy_thresholds(strategy_name):
                    optimized_count += 1
                    self.logger.success(f"Стратегия {strategy_name} адаптирована")
                else:
                    self.logger.info(f"Стратегия {strategy_name} не требует адаптации")
                    
                # Небольшая задержка между оптимизациями
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Ошибка оптимизации стратегии {strategy_name}: {e}")
        
        self.logger.header(f"Оптимизация завершена. Адаптировано стратегий: {optimized_count}/{len(strategies)}")
        return optimized_count

async def main():
    """Тестирование оптимизатора стратегий"""
    config = Config()
    optimizer = StrategyOptimizer(config)
    
    # Анализируем все стратегии
    for strategy_name in optimizer.adaptation_rules.keys():
        print(f"\n=== Анализ стратегии: {strategy_name} ===")
        analysis = await optimizer.analyze_strategy_performance(strategy_name)
        print(f"Результат анализа: {analysis}")
    
    # Запускаем оптимизацию
    print("\n=== Запуск оптимизации ===")
    optimized = await optimizer.optimize_all_strategies()
    print(f"Оптимизировано стратегий: {optimized}")

if __name__ == "__main__":
    asyncio.run(main())