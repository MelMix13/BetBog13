import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

from config import Config
from database import init_database, close_database, AsyncSessionLocal
from models import Match, Signal, StrategyConfig, MatchMetrics, SystemLog
from api_client import APIClient
from metrics_calculator import MetricsCalculator, MatchMetrics
from strategies import BettingStrategies, SignalResult
from simple_optimizer import SimpleOptimizer
from simple_menu_bot import SimpleTelegramMenuBot
from match_monitor import MatchMonitor
from result_tracker import ResultTracker
from logger import BetBogLogger
from tick_analyzer import TickAnalyzer

class BetBogSystem:
    """Main BetBog monitoring system"""
    
    def __init__(self):
        self.config = Config()
        self.logger = BetBogLogger("MAIN")
        self.running = False
        
        # Core components
        self.api_client: Optional[APIClient] = None
        self.metrics_calculator = MetricsCalculator()
        self.strategies = BettingStrategies(self.config.get_default_thresholds())
        self.ml_optimizer = SimpleOptimizer()
        # self.telegram_bot = SimpleTelegramMenuBot(self.config)  # Отключен - используется отдельный Menu Bot
        self.telegram_bot = None
        self.match_monitor = MatchMonitor(self.config)
        self.result_tracker = ResultTracker(self.config)
        self.tick_analyzer = TickAnalyzer(self.config)
        
        # System state
        self.monitored_matches: Dict[str, Dict] = {}
        self.active_signals: List[Dict] = []
        
    async def initialize(self):
        """Initialize all system components"""
        try:
            self.logger.header("Initializing BetBog System")
            
            # Initialize database
            await init_database()
            self.logger.success("Database initialized")
            
            # Initialize API client
            self.api_client = APIClient(self.config)
            self.logger.success("API client ready")
            
            # Telegram bot отключен - используется отдельный Menu Bot
            # await self.telegram_bot.initialize()
            self.logger.success("Telegram bot отключен - используется отдельный Menu Bot")
            
            # Initialize monitoring components
            await self.match_monitor.initialize(
                self.api_client,
                self.metrics_calculator,
                self.strategies,
                self.ml_optimizer
            )
            self.logger.success("Match monitor initialized")
            
            # Initialize result tracker
            await self.result_tracker.initialize(
                self.api_client,
                None  # Telegram bot отключен
            )
            self.logger.success("Result tracker initialized")
            
            # Load existing strategy configurations
            await self.load_strategy_configs()
            
            # Load optimization data if available
            try:
                self.ml_optimizer.load_models("optimization_data.json")
                self.logger.success("Optimization data loaded")
            except:
                self.logger.warning("No existing optimization data found - will create new profiles")
            
            self.logger.success("System initialization complete")
            
        except Exception as e:
            self.logger.error(f"System initialization failed: {str(e)}")
            raise
    
    async def load_strategy_configs(self):
        """Load strategy configurations from database"""
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                
                result = await session.execute(select(StrategyConfig))
                configs = result.scalars().all()
                
                if not configs:
                    # Create default configurations
                    await self.create_default_strategy_configs(session)
                else:
                    # Update strategies with loaded configs
                    for config in configs:
                        strategy_config = json.loads(config.config) if isinstance(config.config, str) else config.config
                        self.strategies.update_strategy_config(config.strategy_name, strategy_config)
                
                await session.commit()
                self.logger.success(f"Loaded {len(configs)} strategy configurations")
                
        except Exception as e:
            self.logger.error(f"Error loading strategy configs: {str(e)}")
    
    async def create_default_strategy_configs(self, session):
        """Create default strategy configurations"""
        default_strategies = [
            "dxg_spike", "momentum_shift", "tiredness_advantage",
            "shots_efficiency", "wave_pattern", "gradient_breakout", "stability_disruption"
        ]
        
        for strategy_name in default_strategies:
            config = StrategyConfig(
                strategy_name=strategy_name,
                config=self.config.get_default_thresholds().get(strategy_name, {}),
                total_signals=0,
                winning_signals=0,
                total_profit=0.0,
                roi=0.0
            )
            session.add(config)
        
        self.logger.info("Created default strategy configurations")
    
    async def start_monitoring(self):
        """Start the main monitoring loop"""
        self.running = True
        self.logger.header("Starting BetBog Monitoring")
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self.match_monitoring_loop()),
            asyncio.create_task(self.result_tracking_loop()),
            asyncio.create_task(self.ml_optimization_loop()),
            # asyncio.create_task(self.telegram_bot.start_polling()),  # Отключен
            asyncio.create_task(self.system_maintenance_loop())
        ]
        
        try:
            # Wait for all tasks to complete or run indefinitely
            await asyncio.gather(*tasks, return_exceptions=True)
                
        except KeyboardInterrupt:
            self.logger.warning("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Monitoring loop error: {str(e)}")
        finally:
            self.running = False
            await self.shutdown()
    
    async def match_monitoring_loop(self):
        """Main match monitoring loop"""
        self.logger.info("Started match monitoring loop")
        
        while self.running:
            try:
                # Get live matches
                if self.api_client:
                    async with self.api_client:
                        live_matches = await self.api_client.get_live_matches()
                else:
                    live_matches = []
                
                if not live_matches:
                    self.logger.info("No live matches found, checking recent finished matches for analysis")
                    # Get recent finished matches for demonstration and analysis
                    if self.api_client:
                        async with self.api_client:
                            finished_matches = await self.api_client.get_finished_matches(days_back=1)
                            if finished_matches:
                                # Take first 3 finished matches and analyze them
                                live_matches = finished_matches[:3]
                                self.logger.success(f"Found {len(live_matches)} recent matches for analysis")
                    
                    if not live_matches:
                        self.logger.info("No matches available for processing")
                        await asyncio.sleep(self.config.MATCH_CHECK_INTERVAL)
                        continue
                
                # Process each match - убрано ограничение на количество матчей
                processed_count = 0
                for match_data in live_matches:
                    try:
                        # Skip non-dict entries
                        if not isinstance(match_data, dict):
                            continue
                        
                        # Фильтр виртуальных матчей
                        if self._is_virtual_match(match_data):
                            continue
                            
                        await self.process_match(match_data)
                        processed_count += 1
                    except Exception as e:
                        match_id = match_data.get('id', 'unknown') if isinstance(match_data, dict) else 'unknown'
                        self.logger.error(f"Error processing match {match_id}: {str(e)}")
                
                self.logger.info(f"Processed {processed_count} matches")
                
                # Wait before next check
                await asyncio.sleep(self.config.MATCH_CHECK_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Match monitoring loop error: {str(e)}")
                await asyncio.sleep(self.config.MATCH_CHECK_INTERVAL)
    
    async def process_match(self, match_data: Dict[str, Any]):
        """Process a single match for signals"""
        try:
            # Parse match data
            if self.api_client:
                async with self.api_client:
                    parsed_match = self.api_client.parse_match_data(match_data)
            else:
                return
            
            if not parsed_match.get('id'):
                return
            
            match_id = str(parsed_match['id'])
            minute = parsed_match.get('minute', 0)
            
            # Skip if match is too early or too late
            if minute < 10 or minute > 85:
                return
            
            # Get or create match in database
            async with AsyncSessionLocal() as session:
                match_obj = await self.match_monitor.get_or_create_match(session, parsed_match)
                
                # Extract statistics from match data itself (avoid 404 errors)
                stats = parsed_match.get('stats', {})
                if not stats:
                    # Extract basic stats from match data if available
                    stats = {
                        'shots_home': parsed_match.get('shots_home', 0),
                        'shots_away': parsed_match.get('shots_away', 0),
                        'attacks_home': parsed_match.get('attacks_home', 0),
                        'attacks_away': parsed_match.get('attacks_away', 0),
                        'corners_home': parsed_match.get('corners_home', 0),
                        'corners_away': parsed_match.get('corners_away', 0),
                        'possession_home': parsed_match.get('possession_home', 50),
                        'possession_away': parsed_match.get('possession_away', 50),
                        'dangerous_home': parsed_match.get('dangerous_home', 0),
                        'dangerous_away': parsed_match.get('dangerous_away', 0)
                    }
                
                # Continue processing even with limited stats data
                
                # Calculate metrics
                historical_stats = await self.match_monitor.get_historical_metrics(session, match_obj.id)
                current_metrics = self.metrics_calculator.calculate_metrics(
                    stats, historical_stats, minute
                )
                
                # Добавить тик в анализатор для всех live матчей
                tick_data = {
                    'minute': minute,
                    'attacks_home': stats.get('attacks_home', 0),
                    'attacks_away': stats.get('attacks_away', 0),
                    'shots_home': stats.get('shots_home', 0),
                    'shots_away': stats.get('shots_away', 0),
                    'dangerous_home': stats.get('dangerous_home', 0),
                    'dangerous_away': stats.get('dangerous_away', 0),
                    'corners_home': stats.get('corners_home', 0),
                    'corners_away': stats.get('corners_away', 0),
                    'goals_home': stats.get('goals_home', 0),
                    'goals_away': stats.get('goals_away', 0)
                }
                
                # Каждый live матч обязательно проходит через анализатор тиков
                self.tick_analyzer.add_tick(match_id, tick_data)
                
                # Получить derived метрики из анализа тиков
                tick_trends = self.tick_analyzer.get_trend_analysis(match_id)
                
                # Логировать анализ тиков для мониторинга
                if tick_trends and tick_trends.get('metrics'):
                    for metric_name, trend_data in tick_trends['metrics'].items():
                        if trend_data['current_average'] > 0:
                            self.logger.info(f"Тик анализ {match_id}: {metric_name} = {trend_data['current_average']:.1f}, тренд: {trend_data['trend']}")
                
                # Store metrics
                await self.match_monitor.store_metrics(session, match_obj.id, current_metrics, minute, stats)
                
                # Check for signals
                signals = self.strategies.analyze_all_strategies(
                    current_metrics, parsed_match, minute
                )
                
                # Process any generated signals
                for signal in signals:
                    await self.process_signal(session, signal, match_obj, current_metrics)
                
                # Очистка данных тиков для завершенных матчей (после 90+ минут)
                if minute >= 90:
                    self.tick_analyzer.clear_match_data(match_id)
                    self.logger.info(f"Очищены данные тиков для завершенного матча {match_id}")
                
                await session.commit()
                
        except Exception as e:
            self.logger.error(f"Error processing match {match_data.get('id')}: {str(e)}")
    
    def _is_virtual_match(self, match_data: Dict[str, Any]) -> bool:
        """Проверить является ли матч виртуальным"""
        # Проверяем различные признаки виртуальных матчей
        league_name = match_data.get('league', {}).get('name', '').lower()
        home_team = match_data.get('home', {}).get('name', '').lower()
        away_team = match_data.get('away', {}).get('name', '').lower()
        
        # Ключевые слова для виртуальных матчей
        virtual_keywords = [
            'virtual', 'виртуал', 'simulation', 'симуляция', 'esports', 'киберспорт',
            'cyber', 'digital', 'fifa', 'pes', 'pro evolution soccer', 'counter strike',
            'dota', 'league of legends', 'valorant', 'rocket league', 'lol'
        ]
        
        # Проверяем название лиги
        for keyword in virtual_keywords:
            if keyword in league_name:
                self.logger.info(f"Фильтрован виртуальный матч: {league_name}")
                return True
        
        # Проверяем названия команд
        for keyword in virtual_keywords:
            if keyword in home_team or keyword in away_team:
                self.logger.info(f"Фильтрован виртуальный матч: {home_team} vs {away_team}")
                return True
        
        # Проверяем ID спорта (если есть информация о том, что это киберспорт)
        sport_id = match_data.get('sport_id')
        if sport_id and sport_id != 1:  # 1 - обычно футбол, остальное может быть виртуальное
            # Дополнительная проверка по названию спорта
            sport_name = match_data.get('sport', {}).get('name', '').lower()
            if any(keyword in sport_name for keyword in virtual_keywords):
                self.logger.info(f"Фильтрован виртуальный спорт: {sport_name}")
                return True
        
        return False
    
    async def process_signal(self, 
                           session, 
                           signal: SignalResult, 
                           match_obj, 
                           metrics: MatchMetrics):
        """Process a generated signal"""
        try:
            # Use statistical optimizer to enhance confidence
            ml_confidence, ml_explanation = self.ml_optimizer.predict_signal_success(
                signal.strategy_name,
                signal.trigger_metrics,
                signal.confidence,
                int(signal.trigger_metrics.get('minute', 45)),
                signal.threshold_used
            )
            
            # Update confidence with ML prediction
            final_confidence = ml_confidence
            
            # Check if signal meets minimum confidence threshold
            strategy_config = self.config.get_default_thresholds().get(signal.strategy_name, {})
            min_confidence = strategy_config.get('min_confidence', 0.7)
            
            if final_confidence < min_confidence:
                self.logger.debug(f"Signal rejected: confidence {final_confidence:.2f} < {min_confidence:.2f}")
                return
            
            # Create signal record
            signal_record = Signal(
                match_id=match_obj.id,
                strategy_name=signal.strategy_name,
                signal_type=signal.signal_type,
                confidence=final_confidence,
                threshold_used=signal.threshold_used,
                trigger_minute=signal.trigger_metrics.get('minute', 45),
                prediction=signal.prediction,
                odds=signal.recommended_odds,
                result='pending',
                profit_loss=0.0,
                stake=signal.stake_multiplier,
                trigger_metrics=signal.trigger_metrics,
                strategy_config=strategy_config
            )
            
            session.add(signal_record)
            await session.flush()  # Get the ID
            
            # Log signal
            self.logger.strategy_signal(
                signal.strategy_name,
                signal.signal_type,
                final_confidence,
                f"{signal.reasoning} | ML: {ml_explanation}"
            )
            
            # Send Telegram notification
            signal_data = {
                'strategy_name': signal.strategy_name,
                'signal_type': signal.signal_type,
                'confidence': final_confidence,
                'prediction': signal.prediction,
                'trigger_minute': signal.trigger_metrics.get('minute', 45),
                'reasoning': signal.reasoning,
                'recommended_odds': signal.recommended_odds
            }
            
            match_data = {
                'home_team': match_obj.home_team,
                'away_team': match_obj.away_team,
                'league': match_obj.league
            }
            
            # Создаем красивое уведомление о сигнале
            await self._display_beautiful_signal_notification(signal_data, match_data)
            
            self.logger.info(f"Signal generated: {signal.strategy_name} for {match_obj.home_team} vs {match_obj.away_team}")
            
            # Update strategy statistics
            await self.update_strategy_stats(session, signal.strategy_name, 'signal_generated')
            
        except Exception as e:
            self.logger.error(f"Error processing signal: {str(e)}")
    
    async def result_tracking_loop(self):
        """Track results of pending signals"""
        self.logger.info("Started result tracking loop")
        
        while self.running:
            try:
                await self.result_tracker.check_pending_results()
                await asyncio.sleep(self.config.RESULT_CHECK_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Result tracking loop error: {str(e)}")
                await asyncio.sleep(self.config.RESULT_CHECK_INTERVAL)
    
    async def ml_optimization_loop(self):
        """Periodic ML optimization of strategies"""
        self.logger.info("Started ML optimization loop")
        
        while self.running:
            try:
                # Run optimization every 24 hours
                await asyncio.sleep(self.config.ML_UPDATE_INTERVAL * 3600)
                
                if not self.running:
                    break
                
                await self.optimize_strategies()
                
            except Exception as e:
                self.logger.error(f"ML optimization loop error: {str(e)}")
    
    async def optimize_strategies(self):
        """Optimize strategy thresholds using ML"""
        try:
            self.logger.header("Starting ML Strategy Optimization")
            
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                
                # Get strategies that need optimization
                strategies_result = await session.execute(select(StrategyConfig))
                strategies = strategies_result.scalars().all()
                
                for strategy in strategies:
                    if strategy.total_signals < self.config.MIN_SAMPLES_FOR_LEARNING:
                        self.logger.warning(f"Not enough data for {strategy.strategy_name}: {strategy.total_signals}")
                        continue
                    
                    # Get historical signals for this strategy
                    signals_result = await session.execute(
                        select(Signal).where(
                            Signal.strategy_name == strategy.strategy_name,
                            Signal.result.in_(['win', 'loss'])
                        )
                    )
                    historical_signals = signals_result.scalars().all()
                    
                    # Convert to format expected by ML optimizer
                    signal_data = []
                    for signal in historical_signals:
                        signal_dict = {
                            'result': signal.result,
                            'confidence': signal.confidence,
                            'trigger_minute': signal.trigger_minute,
                            'threshold_used': signal.threshold_used,
                            'trigger_metrics': signal.trigger_metrics or {}
                        }
                        signal_data.append(signal_dict)
                    
                    # Optimize strategy
                    optimal_thresholds = await self.ml_optimizer.optimize_strategy_thresholds(
                        strategy.strategy_name,
                        signal_data,
                        self.config.MIN_SAMPLES_FOR_LEARNING
                    )
                    
                    if optimal_thresholds:
                        # Update strategy configuration
                        current_config = json.loads(strategy.config) if isinstance(strategy.config, str) else strategy.config
                        current_config.update(optimal_thresholds)
                        strategy.config = current_config
                        strategy.last_optimized = datetime.now()
                        
                        # Update strategies object
                        self.strategies.update_strategy_config(strategy.strategy_name, current_config)
                        
                        self.logger.success(f"Optimized {strategy.strategy_name}: {optimal_thresholds}")
                
                await session.commit()
                
                # Save ML models
                self.ml_optimizer.save_models("models.json")
                
                self.logger.success("ML optimization complete")
                
        except Exception as e:
            self.logger.error(f"Error in ML optimization: {str(e)}")
    
    async def system_maintenance_loop(self):
        """Periodic system maintenance tasks"""
        self.logger.info("Started system maintenance loop")
        
        while self.running:
            try:
                # Run maintenance every hour
                await asyncio.sleep(3600)
                
                if not self.running:
                    break
                
                await self.run_maintenance_tasks()
                
            except Exception as e:
                self.logger.error(f"System maintenance error: {str(e)}")
    
    async def run_maintenance_tasks(self):
        """Run periodic maintenance tasks"""
        try:
            async with AsyncSessionLocal() as session:
                # Clean up old logs (keep last 7 days)
                from sqlalchemy import delete
                cutoff_date = datetime.now() - timedelta(days=7)
                
                await session.execute(
                    delete(SystemLog).where(SystemLog.created_at < cutoff_date)
                )
                
                # Update strategy statistics
                await self.update_all_strategy_stats(session)
                
                await session.commit()
                
                self.logger.info("Maintenance tasks completed")
                
        except Exception as e:
            self.logger.error(f"Maintenance tasks error: {str(e)}")
    
    async def update_strategy_stats(self, session, strategy_name: str, event_type: str):
        """Update strategy statistics"""
        try:
            from sqlalchemy import select
            
            result = await session.execute(
                select(StrategyConfig).where(StrategyConfig.strategy_name == strategy_name)
            )
            strategy = result.scalar_one_or_none()
            
            if not strategy:
                return
            
            if event_type == 'signal_generated':
                strategy.total_signals += 1
            elif event_type == 'signal_won':
                strategy.winning_signals += 1
            
            # Update ROI
            if strategy.total_signals > 0:
                strategy.roi = strategy.total_profit / strategy.total_signals
            
        except Exception as e:
            self.logger.error(f"Error updating strategy stats: {str(e)}")
    
    async def _display_beautiful_signal_notification(self, signal_data: Dict[str, Any], match_data: Dict[str, Any]):
        """Отобразить красивое уведомление о сигнале"""
        try:
            confidence = signal_data.get('confidence', 0)
            confidence_emoji = "🔥" if confidence > 0.8 else "⚡" if confidence > 0.6 else "📊"
            
            strategy_emojis = {
                'under_2_5_goals': '🎯',
                'over_2_5_goals': '⚽',
                'btts_yes': '🥅',
                'btts_no': '🛡️',
                'home_win': '🏠',
                'away_win': '✈️',
                'draw': '🤝',
                'next_goal_home': '🏃‍♂️',
                'next_goal_away': '🏃‍♀️'
            }
            
            strategy_emoji = strategy_emojis.get(signal_data.get('strategy_name', ''), '🎲')
            
            # Красивое форматирование уведомления
            notification = f"""
╭─────────────────────────────────────────────────────────────────╮
│ {confidence_emoji} НОВЫЙ СИГНАЛ ОБНАРУЖЕН! {strategy_emoji}                                │
├─────────────────────────────────────────────────────────────────┤
│ 🎯 Стратегия: {signal_data.get('strategy_name', 'N/A')}
│ 📈 Тип: {signal_data.get('signal_type', 'N/A')}
│ 🔥 Уверенность: {confidence:.1%}
│ ⚽ Матч: {match_data.get('home_team', 'N/A')} vs {match_data.get('away_team', 'N/A')}
│ 🏆 Лига: {match_data.get('league', 'N/A')}
│ ⏰ Минута: {signal_data.get('trigger_minute', 'N/A')}'
│ 💡 Прогноз: {signal_data.get('prediction', 'N/A')}
│ 📊 Коэффициент: {signal_data.get('recommended_odds', 'N/A')}
├─────────────────────────────────────────────────────────────────┤
│ 📝 Обоснование:
│ {signal_data.get('reasoning', 'Данные анализа недоступны')}
╰─────────────────────────────────────────────────────────────────╯
"""
            
            print(notification)
            self.logger.success(f"📱 Красивое уведомление о сигнале отправлено: {signal_data.get('strategy_name')}")
            
        except Exception as e:
            self.logger.error(f"Ошибка отображения уведомления: {str(e)}")

    async def update_all_strategy_stats(self, session):
        """Update all strategy statistics from signals"""
        try:
            from sqlalchemy import select, func
            
            strategies_result = await session.execute(select(StrategyConfig))
            strategies = strategies_result.scalars().all()
            
            for strategy in strategies:
                # Count total signals
                total_result = await session.execute(
                    select(func.count(Signal.id)).where(
                        Signal.strategy_name == strategy.strategy_name
                    )
                )
                strategy.total_signals = total_result.scalar() or 0
                
                # Count winning signals
                winning_result = await session.execute(
                    select(func.count(Signal.id)).where(
                        Signal.strategy_name == strategy.strategy_name,
                        Signal.result == 'win'
                    )
                )
                strategy.winning_signals = winning_result.scalar() or 0
                
                # Sum total profit
                profit_result = await session.execute(
                    select(func.sum(Signal.profit_loss)).where(
                        Signal.strategy_name == strategy.strategy_name
                    )
                )
                strategy.total_profit = profit_result.scalar() or 0.0
                
                # Calculate ROI
                if strategy.total_signals > 0:
                    strategy.roi = strategy.total_profit / strategy.total_signals
                
        except Exception as e:
            self.logger.error(f"Error updating all strategy stats: {str(e)}")
    
    async def shutdown(self):
        """Shutdown system gracefully"""
        self.logger.header("Shutting down BetBog System")
        
        self.running = False
        
        try:
            # Telegram bot отключен
            # await self.telegram_bot.stop_polling()
            self.logger.success("Telegram bot was disabled")
            
            # Close database connections
            await close_database()
            self.logger.success("Database connections closed")
            
            self.logger.success("System shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")

def setup_signal_handlers(system: BetBogSystem):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}")
        asyncio.create_task(system.shutdown())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point"""
    system = BetBogSystem()
    
    try:
        # Setup signal handlers
        setup_signal_handlers(system)
        
        # Initialize system
        await system.initialize()
        
        # Start monitoring
        await system.start_monitoring()
        
    except KeyboardInterrupt:
        system.logger.warning("Interrupted by user")
    except Exception as e:
        system.logger.error(f"System error: {str(e)}")
        raise
    finally:
        await system.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGraceful shutdown completed")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)
