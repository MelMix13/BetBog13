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
from sqlalchemy import select
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
        
        # Таймаут между сигналами для одного матча (5 минут)
        self.match_signal_timeout = {}  # {match_id: last_signal_time}
        
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
        
        last_match_search = 0
        active_matches = []
        
        while self.running:
            try:
                current_time = time.time()
                
                # Search for new matches every 30 seconds (tick interval)
                if current_time - last_match_search >= self.config.TICK_INTERVAL:
                    self.logger.info("Searching for new matches...")
                    
                    if self.api_client:
                        async with self.api_client:
                            live_matches = await self.api_client.get_live_matches()
                    else:
                        live_matches = []
                    
                    if not live_matches:
                        self.logger.info("No live matches found, checking recent finished matches for analysis")
                        if self.api_client:
                            async with self.api_client:
                                finished_matches = await self.api_client.get_finished_matches(days_back=1)
                                if finished_matches:
                                    live_matches = finished_matches[:3]
                                    self.logger.success(f"Found {len(live_matches)} recent matches for analysis")
                    
                    # Update active matches list
                    active_matches = []
                    for match_data in live_matches:
                        if isinstance(match_data, dict) and not self._is_virtual_match(match_data):
                            active_matches.append(match_data)
                    
                    last_match_search = current_time
                    self.logger.success(f"Found {len(active_matches)} active matches to monitor")
                
                # Analyze active matches every 30 seconds (tick interval)
                if active_matches:
                    processed_count = 0
                    for match_data in active_matches:
                        try:
                            await self.process_match(match_data)
                            processed_count += 1
                        except Exception as e:
                            match_id = match_data.get('id', 'unknown')
                            self.logger.error(f"Error processing match {match_id}: {str(e)}")
                    
                    self.logger.info(f"Analyzed {processed_count} active matches")
                else:
                    self.logger.info("No active matches to analyze")
                
                # Wait for next tick (30 seconds)
                await asyncio.sleep(self.config.TICK_INTERVAL)
                
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
                
                # Валидация данных перед анализом стратегий
                if not self._validate_match_data(parsed_match, stats, minute):
                    self.logger.warning(f"Недостоверные данные для матча {match_id}, пропускаем анализ сигналов")
                    # Store metrics anyway for monitoring
                    await self.match_monitor.store_metrics(session, match_obj.id, current_metrics, minute, stats)
                    await session.commit()
                    return
                
                # Store metrics
                await self.match_monitor.store_metrics(session, match_obj.id, current_metrics, minute, stats)
                
                # Check for signals - для стратегий тоталов используем полные метрики
                strategy_metrics = current_metrics
                
                # Для стратегий тоталов получаем полные метрики из тик-анализатора
                if hasattr(self, 'tick_analyzer'):
                    full_metrics = self.tick_analyzer.get_current_full_metrics(match_id)
                    if full_metrics:
                        # Обновляем существующие метрики полными значениями для тоталов
                        strategy_metrics = current_metrics
                        strategy_metrics.total_attacks = full_metrics.get('total_attacks', 0)
                        strategy_metrics.total_shots = full_metrics.get('total_shots', 0)
                        strategy_metrics.total_dangerous = full_metrics.get('total_dangerous', 0)
                        strategy_metrics.total_corners = full_metrics.get('total_corners', 0)
                        strategy_metrics.total_goals = full_metrics.get('total_goals', 0)
                        strategy_metrics.attacks_home = full_metrics.get('attacks_home', 0)
                        strategy_metrics.attacks_away = full_metrics.get('attacks_away', 0)
                        strategy_metrics.shots_home = full_metrics.get('shots_home', 0)
                        strategy_metrics.shots_away = full_metrics.get('shots_away', 0)
                
                signals = self.strategies.analyze_all_strategies(
                    strategy_metrics, parsed_match, minute
                )
                
                # Process any generated signals
                for signal in signals:
                    # Сначала сохраняем сигнал, затем получаем дополнительную статистику
                    await self.process_signal(session, signal, match_obj, current_metrics)
                    
                    # Получаем статистику команд для тоталов асинхронно (не блокируя сохранение)
                    if signal.strategy_name in ['under_2_5_goals', 'over_2_5_goals']:
                        try:
                            home_team_id = parsed_match.get('home_team_id')
                            away_team_id = parsed_match.get('away_team_id')
                            home_team = parsed_match.get('home_team', '')
                            away_team = parsed_match.get('away_team', '')
                            
                            if home_team_id and away_team_id:
                                team_stats = await self._get_teams_totals_stats_by_id(home_team_id, away_team_id, home_team, away_team)
                                signal.team_stats = team_stats
                                self.logger.info(f"Получена статистика команд для сигнала {signal.strategy_name}")
                        except Exception as e:
                            self.logger.warning(f"Не удалось получить статистику команд: {str(e)}")
                            signal.team_stats = {}
                
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
            # Проверяем таймаут между сигналами для одного матча (5 минут)
            current_time = datetime.now()
            match_id = str(match_obj.id)
            
            if match_id in self.match_signal_timeout:
                last_signal_time = self.match_signal_timeout[match_id]
                time_diff = (current_time - last_signal_time).total_seconds()
                
                if time_diff < 300:  # 5 минут = 300 секунд
                    remaining_time = int(300 - time_diff)
                    self.logger.debug(f"Таймаут сигнала для матча {match_id}: осталось {remaining_time} сек")
                    return  # Пропускаем сигнал
            
            # Обновляем время последнего сигнала
            self.match_signal_timeout[match_id] = current_time
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
                'league': match_obj.league,
                'home_score': match_obj.home_score,
                'away_score': match_obj.away_score
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
        """Отправить красивое уведомление о сигнале в Telegram"""
        try:
            # Проверяем время сигнала - ограничение только для стратегий тоталов
            trigger_minute = signal_data.get('trigger_minute', 0)
            strategy_name = signal_data.get('strategy_name', '')
            
            # Для стратегий тоталов: только за 10 минут до матча или до 20 минуты
            if strategy_name in ['under_2_5_goals', 'over_2_5_goals']:
                if trigger_minute > 20:
                    return  # Не отправляем сигналы тоталов после 20 минуты
            
            confidence = signal_data.get('confidence', 0)
            confidence_emoji = "🔥" if confidence > 0.8 else "⚡" if confidence > 0.6 else "📊"
            
            # Русские названия стратегий
            strategy_names_ru = {
                'under_2_5_goals': 'Тотал меньше 2.5 голов',
                'over_2_5_goals': 'Тотал больше 2.5 голов',
                'btts_yes': 'Обе команды забьют ДА',
                'btts_no': 'Обе команды забьют НЕТ',
                'home_win': 'Победа хозяев',
                'away_win': 'Победа гостей',
                'draw': 'Ничья',
                'next_goal_home': 'Следующий гол - хозяева',
                'next_goal_away': 'Следующий гол - гости'
            }
            
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
            
            strategy_name = signal_data.get('strategy_name', '')
            strategy_ru = strategy_names_ru.get(strategy_name, strategy_name)
            strategy_emoji = strategy_emojis.get(strategy_name, '🎲')
            
            # Получаем текущий счет (если доступен)
            home_score = match_data.get('home_score', 0)
            away_score = match_data.get('away_score', 0)
            score_text = f"{home_score}:{away_score}"
            
            # Форматирование для Telegram
            telegram_message = f"""{confidence_emoji} <b>НОВЫЙ СИГНАЛ!</b> {strategy_emoji}

⚽ <b>{match_data.get('home_team', 'N/A')} vs {match_data.get('away_team', 'N/A')}</b>
🏆 <b>{match_data.get('league', 'N/A')}</b>
📊 <b>Счёт:</b> {score_text} | <b>Минута:</b> {trigger_minute}'

🎯 <b>Стратегия:</b> {strategy_ru}
🔥 <b>Уверенность:</b> {confidence:.1%}
💡 <b>Прогноз:</b> {signal_data.get('prediction', 'N/A')}
📈 <b>Коэффициент:</b> {signal_data.get('recommended_odds', 'N/A')}"""
            
            # Добавляем статистику истории для стратегий тоталов
            if strategy_name in ['under_2_5_goals', 'over_2_5_goals']:
                home_team = match_data.get('home_team', 'N/A')
                away_team = match_data.get('away_team', 'N/A')
                
                # Получаем статистику команд из базы данных
                team_stats = await self._get_teams_totals_stats(home_team, away_team)
                
                if team_stats:
                    home_stats = team_stats.get('home_team', {})
                    away_stats = team_stats.get('away_team', {})
                    
                    telegram_message += f"""

📈 <b>Статистика команд (исторические данные):</b>

🏠 <b>{home_team} дома:</b>
   • Среднее голов в матчах: {home_stats.get('avg_total_goals', 'N/A')}
   • Голов команды: {home_stats.get('avg_team_goals', 'N/A')}/матч
   • Under 2.5: {home_stats.get('under_25_percent_home', 'N/A')}% | Over 2.5: {home_stats.get('over_25_percent_home', 'N/A')}%
   • Атаки: {home_stats.get('avg_attacks', 'N/A')}/матч | Удары: {home_stats.get('avg_shots', 'N/A')}/матч

✈️ <b>{away_team} в гостях:</b>
   • Среднее голов в матчах: {away_stats.get('avg_total_goals', 'N/A')}
   • Голов команды: {away_stats.get('avg_team_goals', 'N/A')}/матч
   • Under 2.5: {away_stats.get('under_25_percent_away', 'N/A')}% | Over 2.5: {away_stats.get('over_25_percent_away', 'N/A')}%
   • Атаки: {away_stats.get('avg_attacks', 'N/A')}/матч | Удары: {away_stats.get('avg_shots', 'N/A')}/матч

📊 <b>Прогноз тоталов:</b> {team_stats.get('combined_trend', 'Анализ недоступен')}"""
                else:
                    telegram_message += f"""

📈 <b>Статистика команд:</b>
📊 <b>Данные истории команд недоступны</b>"""
            
            telegram_message += f"""

📝 <b>Обоснование:</b>
{signal_data.get('reasoning', 'Данные анализа недоступны')}"""
            
            # Отправляем в Telegram
            await self._send_telegram_message(telegram_message)
            
            # Дублируем в консоль
            console_notification = f"""
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
            print(console_notification)
            self.logger.success(f"📱 Уведомление отправлено в Telegram: {signal_data.get('strategy_name')}")
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления: {str(e)}")

    async def _send_telegram_message(self, message: str):
        """Отправить сообщение в Telegram"""
        try:
            import aiohttp
            
            bot_token = os.getenv("BOT_TOKEN", "7228733029:AAFVPzKHUSRidigzYSy_IANt8rWzjjPBDPA")
            chat_id = 5654340844  # Ваш chat_id
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        self.logger.success("Telegram сообщение отправлено успешно")
                    else:
                        self.logger.error(f"Ошибка отправки в Telegram: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Ошибка Telegram API: {str(e)}")

    async def _get_teams_totals_stats_by_id(self, home_team_id: str, away_team_id: str, home_team: str, away_team: str) -> Dict[str, Any]:
        """Получить статистику тоталов для команд по ID из исторических данных"""
        try:
            self.logger.info(f"Запрос статистики команд по ID: {home_team} (ID: {home_team_id}) vs {away_team} (ID: {away_team_id})")
            
            # Получаем исторические данные для команд через API по ID
            home_matches = await self.api_client.get_team_matches_by_id(home_team_id, days_back=30)
            away_matches = await self.api_client.get_team_matches_by_id(away_team_id, days_back=30)
            
            self.logger.info(f"Найдено матчей по ID: {home_team} = {len(home_matches) if home_matches else 0}, {away_team} = {len(away_matches) if away_matches else 0}")
            
            if not home_matches and not away_matches:
                self.logger.warning(f"Нет исторических данных через API по ID для команд {home_team} vs {away_team}")
                return None
            
            # Анализируем домашнюю команду
            home_stats = self._analyze_team_api_data(home_matches, home_team, True)
            
            # Анализируем гостевую команду
            away_stats = self._analyze_team_api_data(away_matches, away_team, False)
            
            # Комбинированный тренд
            combined_trend = self._get_combined_trend(home_stats, away_stats)
            
            return {
                'home_team': home_stats,
                'away_team': away_stats,
                'combined_trend': combined_trend,
                'data_source': 'API_by_ID'
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики команд по ID: {str(e)}")
            return None

    async def _get_teams_totals_stats(self, home_team: str, away_team: str) -> Dict[str, Any]:
        """Получить статистику тоталов для команд из исторических данных"""
        try:
            self.logger.info(f"Запрос статистики команд: {home_team} vs {away_team}")
            
            # Получаем исторические данные для команд через API
            home_matches = await self.api_client.get_team_matches(home_team, days_back=30)
            away_matches = await self.api_client.get_team_matches(away_team, days_back=30)
            
            self.logger.info(f"Найдено матчей: {home_team} = {len(home_matches) if home_matches else 0}, {away_team} = {len(away_matches) if away_matches else 0}")
            
            if not home_matches and not away_matches:
                self.logger.warning(f"Нет исторических данных через API для команд {home_team} vs {away_team}")
                return None
            
            # Анализируем домашнюю команду
            home_stats = self._analyze_team_api_data(home_matches, home_team, True)
            
            # Анализируем гостевую команду
            away_stats = self._analyze_team_api_data(away_matches, away_team, False)
            
            # Комбинированный тренд
            if home_stats and away_stats:
                avg_under = (home_stats.get('under_25_percent_home', 50) + away_stats.get('under_25_percent_away', 50)) / 2
                
                if avg_under >= 70:
                    trend = "Сильная тенденция к Under 2.5"
                elif avg_under >= 50:
                    trend = "Умеренная тенденция к Under 2.5" 
                else:
                    trend = "Тенденция к Over 2.5"
            else:
                trend = "Недостаточно данных для анализа"
            
            return {
                'home_team': home_stats or {},
                'away_team': away_stats or {},
                'combined_trend': trend
            }
                
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики команд: {str(e)}")
            return None

    def _analyze_team_api_data(self, matches: List[Dict], team_name: str, is_home: bool) -> Dict[str, Any]:
        """Анализ данных команды из API"""
        if not matches:
            return {}
        
        total_goals = []
        team_goals = []
        under_25_count = 0
        over_25_count = 0
        relevant_matches = []
        total_attacks = []
        total_shots = []
        
        for match in matches:
            # Фильтруем матчи где команда играла дома/в гостях
            if is_home and match.get('home_team') == team_name:
                relevant_matches.append(match)
            elif not is_home and match.get('away_team') == team_name:
                relevant_matches.append(match)
            elif not is_home and match.get('home_team') == team_name:
                continue  # Пропускаем домашние матчи для гостевой статистики
            elif is_home and match.get('away_team') == team_name:
                continue  # Пропускаем гостевые матчи для домашней статистики
            else:
                # Если команда играла в любом статусе, добавляем
                relevant_matches.append(match)
        
        if not relevant_matches:
            return {}
        
        for match in relevant_matches:
            home_score = match.get('home_score', 0) 
            away_score = match.get('away_score', 0)
            total = home_score + away_score
            total_goals.append(total)
            
            # Голы конкретной команды
            if is_home and match.get('home_team') == team_name:
                team_goals.append(home_score)
            elif not is_home and match.get('away_team') == team_name:
                team_goals.append(away_score)
            
            # Счетчики для тоталов
            if total < 2.5:
                under_25_count += 1
            else:
                over_25_count += 1
            
            # Атакующие статистики из API если есть
            stats = match.get('stats', {})
            if stats:
                if is_home and match.get('home_team') == team_name:
                    attacks = stats.get('attacks', {}).get('home', 0)
                    shots = stats.get('shots_total', {}).get('home', 0)
                elif not is_home and match.get('away_team') == team_name:
                    attacks = stats.get('attacks', {}).get('away', 0)
                    shots = stats.get('shots_total', {}).get('away', 0)
                else:
                    attacks = 0
                    shots = 0
                
                if attacks > 0:
                    total_attacks.append(attacks)
                if shots > 0:
                    total_shots.append(shots)
        
        if not total_goals:
            return {}
        
        # Основные показатели
        avg_total_goals = round(sum(total_goals) / len(total_goals), 1)
        avg_team_goals = round(sum(team_goals) / len(team_goals), 1) if team_goals else 0
        under_25_percent = round((under_25_count / len(total_goals)) * 100)
        over_25_percent = round((over_25_count / len(total_goals)) * 100)
        
        # Атакующие показатели
        avg_attacks = round(sum(total_attacks) / len(total_attacks), 1) if total_attacks else 0
        avg_shots = round(sum(total_shots) / len(total_shots), 1) if total_shots else 0
        
        result = {
            'avg_total_goals': avg_total_goals,
            'avg_team_goals': avg_team_goals,
            'under_25_percent_home' if is_home else 'under_25_percent_away': under_25_percent,
            'over_25_percent_home' if is_home else 'over_25_percent_away': over_25_percent,
            'avg_attacks': avg_attacks,
            'avg_shots': avg_shots,
            'matches_count': len(relevant_matches)
        }
        
        # Добавляем legacy поля для совместимости
        result['avg_goals_home' if is_home else 'avg_goals_away'] = avg_total_goals
        
        return result

    def _validate_match_data(self, parsed_match: Dict[str, Any], stats: Dict[str, Any], minute: int) -> bool:
        """Валидация данных матча перед анализом стратегий"""
        
        # Проверяем базовые данные матча
        if not parsed_match.get('home_team') or not parsed_match.get('away_team'):
            return False
        
        # Проверяем, что минута адекватная
        if minute < 0 or minute > 130:
            return False
        
        # Смягченная валидация - принимаем живые матчи даже с нулевой статистикой
        # API может не предоставлять детальную статистику в реальном времени
        self.logger.debug(f"Принят к анализу матч {parsed_match.get('home_team')} vs {parsed_match.get('away_team')} на {minute} минуте")
        
        return True

    def _analyze_team_totals(self, matches: List, team_name: str, is_home: bool) -> Dict[str, Any]:
        """Анализ статистики тоталов для команды"""
        if not matches:
            return {}
        
        total_goals = []
        under_25_count = 0
        home_goals = []
        away_goals = []
        
        for match in matches:
            total = match.home_score + match.away_score
            total_goals.append(total)
            
            if total < 2.5:
                under_25_count += 1
                
            if is_home and match.home_team == team_name:
                home_goals.append(total)
            elif not is_home and match.away_team == team_name:
                away_goals.append(total)
        
        relevant_goals = home_goals if is_home else away_goals
        avg_goals = round(sum(relevant_goals) / len(relevant_goals), 1) if relevant_goals else 0
        under_25_percent = round((under_25_count / len(matches)) * 100) if matches else 0
        
        return {
            'avg_goals_home' if is_home else 'avg_goals_away': avg_goals,
            'under_25_percent_home' if is_home else 'under_25_percent_away': under_25_percent,
            'matches_count': len(matches)
        }

    def _get_combined_trend(self, home_stats: Dict, away_stats: Dict) -> str:
        """Определить комбинированный тренд тоталов"""
        home_under = home_stats.get('under_25_percent_home', 0)
        away_under = away_stats.get('under_25_percent_away', 0)
        
        avg_under = (home_under + away_under) / 2
        
        if avg_under >= 70:
            return "Сильная тенденция к Under 2.5"
        elif avg_under >= 50:
            return "Умеренная тенденция к Under 2.5"
        elif avg_under >= 30:
            return "Сбалансированные тоталы"
        else:
            return "Тенденция к Over 2.5"

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
