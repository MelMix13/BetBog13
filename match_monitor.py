import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import json

from config import Config
from models import Match, MatchMetrics as MatchMetricsModel, Signal
from metrics_calculator import MatchMetrics, MetricsCalculator
from strategies import BettingStrategies
from ml_optimizer import MLOptimizer
from api_client import APIClient
from logger import BetBogLogger

class MatchMonitor:
    """Monitors individual matches and manages their data"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("MATCH_MONITOR")
        self.active_matches: Dict[str, Dict] = {}
        
        # Components (will be injected)
        self.api_client: Optional[APIClient] = None
        self.metrics_calculator: Optional[MetricsCalculator] = None
        self.strategies: Optional[BettingStrategies] = None
        self.ml_optimizer: Optional[MLOptimizer] = None
    
    async def initialize(self, 
                        api_client: APIClient,
                        metrics_calculator: MetricsCalculator,
                        strategies: BettingStrategies,
                        ml_optimizer: MLOptimizer):
        """Initialize with required components"""
        self.api_client = api_client
        self.metrics_calculator = metrics_calculator
        self.strategies = strategies
        self.ml_optimizer = ml_optimizer
        
        self.logger.success("Match monitor initialized")
    
    async def get_or_create_match(self, session: AsyncSession, match_data: Dict[str, Any]) -> Match:
        """Get existing match or create new one"""
        try:
            match_id = str(match_data['id'])
            
            # Try to find existing match
            result = await session.execute(
                select(Match).where(Match.match_id == match_id)
            )
            match = result.scalar_one_or_none()
            
            if match:
                # Update existing match data
                match.minute = match_data.get('minute', match.minute)
                match.home_score = match_data.get('home_score', match.home_score)
                match.away_score = match_data.get('away_score', match.away_score)
                match.status = match_data.get('status', match.status)
                match.stats = match_data.get('stats', match.stats)
                match.updated_at = datetime.now()
                
                self.logger.debug(f"Updated match: {match.home_team} vs {match.away_team}")
            else:
                # Create new match
                match = Match(
                    match_id=match_id,
                    home_team=match_data['home_team'],
                    away_team=match_data['away_team'],
                    league=match_data.get('league', 'Unknown'),
                    start_time=match_data.get('start_time'),
                    status=match_data.get('status', 'live'),
                    minute=match_data.get('minute', 0),
                    home_score=match_data.get('home_score', 0),
                    away_score=match_data.get('away_score', 0),
                    stats=match_data.get('stats', {})
                )
                session.add(match)
                await session.flush()  # Get the ID
                
                self.logger.info(f"Created new match: {match.home_team} vs {match.away_team}")
            
            return match
            
        except Exception as e:
            self.logger.error(f"Error getting/creating match: {str(e)}")
            raise
    
    async def get_historical_metrics(self, session: AsyncSession, match_id: int) -> List[Dict[str, Any]]:
        """Get historical metrics for a match"""
        try:
            result = await session.execute(
                select(MatchMetricsModel)
                .where(MatchMetricsModel.match_id == match_id)
                .order_by(MatchMetricsModel.minute.asc())
            )
            metrics = result.scalars().all()
            
            historical_data = []
            for metric in metrics:
                historical_data.append({
                    'minute': metric.minute,
                    'shots_home': metric.shots_home,
                    'shots_away': metric.shots_away,
                    'attacks_home': metric.attacks_home,
                    'attacks_away': metric.attacks_away,
                    'possession_home': metric.possession_home,
                    'possession_away': metric.possession_away,
                    'corners_home': metric.corners_home,
                    'corners_away': metric.corners_away
                })
            
            return historical_data
            
        except Exception as e:
            self.logger.error(f"Error getting historical metrics: {str(e)}")
            return []
    
    async def store_metrics(self, 
                          session: AsyncSession, 
                          match_id: int, 
                          metrics: MatchMetrics, 
                          minute: int, 
                          raw_stats: Dict[str, Any]):
        """Store calculated metrics in database"""
        try:
            # Check if metrics already exist for this minute
            existing_result = await session.execute(
                select(MatchMetricsModel).where(
                    and_(
                        MatchMetricsModel.match_id == match_id,
                        MatchMetricsModel.minute == minute
                    )
                )
            )
            existing_metrics = existing_result.scalar_one_or_none()
            
            if existing_metrics:
                # Update existing metrics
                self._update_metrics_record(existing_metrics, metrics, raw_stats)
                self.logger.debug(f"Updated metrics for match {match_id}, minute {minute}")
            else:
                # Create new metrics record
                metrics_record = MatchMetricsModel(
                    match_id=match_id,
                    minute=minute,
                    **metrics.to_dict(),
                    **self._extract_raw_stats(raw_stats)
                )
                session.add(metrics_record)
                self.logger.debug(f"Created new metrics for match {match_id}, minute {minute}")
            
        except Exception as e:
            self.logger.error(f"Error storing metrics: {str(e)}")
    
    def _update_metrics_record(self, record: MatchMetricsModel, metrics: MatchMetrics, raw_stats: Dict[str, Any]):
        """Update existing metrics record"""
        # Update derived metrics
        record.dxg_home = metrics.dxg_home
        record.dxg_away = metrics.dxg_away
        record.gradient_home = metrics.gradient_home
        record.gradient_away = metrics.gradient_away
        record.wave_amplitude = metrics.wave_amplitude
        record.tiredness_home = metrics.tiredness_home
        record.tiredness_away = metrics.tiredness_away
        record.momentum_home = metrics.momentum_home
        record.momentum_away = metrics.momentum_away
        record.stability_home = metrics.stability_home
        record.stability_away = metrics.stability_away
        record.shots_per_attack_home = metrics.shots_per_attack_home
        record.shots_per_attack_away = metrics.shots_per_attack_away
        
        # Update raw stats
        raw_stats_dict = self._extract_raw_stats(raw_stats)
        for key, value in raw_stats_dict.items():
            if hasattr(record, key):
                setattr(record, key, value)
    
    def _extract_raw_stats(self, raw_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and normalize raw statistics"""
        return {
            'shots_home': raw_stats.get('shots_home', 0),
            'shots_away': raw_stats.get('shots_away', 0),
            'attacks_home': raw_stats.get('attacks_home', 0),
            'attacks_away': raw_stats.get('attacks_away', 0),
            'possession_home': raw_stats.get('possession_home', 50.0),
            'possession_away': raw_stats.get('possession_away', 50.0),
            'corners_home': raw_stats.get('corners_home', 0),
            'corners_away': raw_stats.get('corners_away', 0)
        }
    
    async def detect_significant_changes(self, 
                                       session: AsyncSession,
                                       match_id: int,
                                       current_metrics: MatchMetrics,
                                       minute: int) -> Dict[str, bool]:
        """Detect significant changes in match metrics"""
        try:
            # Get previous metrics (from 5 minutes ago)
            previous_result = await session.execute(
                select(MatchMetricsModel)
                .where(
                    and_(
                        MatchMetricsModel.match_id == match_id,
                        MatchMetricsModel.minute <= minute - 5
                    )
                )
                .order_by(desc(MatchMetricsModel.minute))
                .limit(1)
            )
            previous_record = previous_result.scalar_one_or_none()
            
            if not previous_record:
                return {}
            
            # Convert previous record to MatchMetrics
            previous_metrics = MatchMetrics(
                dxg_home=previous_record.dxg_home or 0.0,
                dxg_away=previous_record.dxg_away or 0.0,
                gradient_home=previous_record.gradient_home or 0.0,
                gradient_away=previous_record.gradient_away or 0.0,
                wave_amplitude=previous_record.wave_amplitude or 0.0,
                tiredness_home=previous_record.tiredness_home or 0.0,
                tiredness_away=previous_record.tiredness_away or 0.0,
                momentum_home=previous_record.momentum_home or 0.0,
                momentum_away=previous_record.momentum_away or 0.0,
                stability_home=previous_record.stability_home or 0.0,
                stability_away=previous_record.stability_away or 0.0,
                shots_per_attack_home=previous_record.shots_per_attack_home or 0.0,
                shots_per_attack_away=previous_record.shots_per_attack_away or 0.0
            )
            
            # Use metrics calculator to detect changes
            thresholds = {
                'dxg_spike': 0.15,
                'momentum_shift': 0.25,
                'tiredness_advantage': 0.3,
                'gradient_change': 0.2
            }
            
            changes = self.metrics_calculator.detect_significant_changes(
                current_metrics, previous_metrics, thresholds
            )
            
            return changes
            
        except Exception as e:
            self.logger.error(f"Error detecting significant changes: {str(e)}")
            return {}
    
    async def should_monitor_match(self, match_data: Dict[str, Any]) -> bool:
        """Determine if a match should be monitored"""
        try:
            minute = match_data.get('minute', 0)
            status = match_data.get('status', '')
            
            # Only monitor live matches in reasonable time range
            if status != 'live':
                return False
            
            if minute < 10 or minute > 85:
                return False
            
            # Check if we have too many matches already
            if len(self.active_matches) >= self.config.MAX_CONCURRENT_MATCHES:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking if should monitor match: {str(e)}")
            return False
    
    async def cleanup_finished_matches(self, session: AsyncSession):
        """Clean up matches that have finished"""
        try:
            # Update status of finished matches
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=3)  # Matches older than 3 hours
            
            result = await session.execute(
                select(Match).where(
                    and_(
                        Match.status == 'live',
                        Match.updated_at < cutoff_time
                    )
                )
            )
            old_matches = result.scalars().all()
            
            for match in old_matches:
                match.status = 'finished'
                self.logger.info(f"Marked match as finished: {match.home_team} vs {match.away_team}")
            
            # Remove from active monitoring
            finished_ids = [str(match.match_id) for match in old_matches]
            for match_id in finished_ids:
                if match_id in self.active_matches:
                    del self.active_matches[match_id]
            
            if old_matches:
                self.logger.info(f"Cleaned up {len(old_matches)} finished matches")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up finished matches: {str(e)}")
    
    async def get_match_summary(self, session: AsyncSession, match_id: int) -> Dict[str, Any]:
        """Get comprehensive match summary"""
        try:
            # Get match basic info
            match_result = await session.execute(
                select(Match).where(Match.id == match_id)
            )
            match = match_result.scalar_one_or_none()
            
            if not match:
                return {}
            
            # Get latest metrics
            metrics_result = await session.execute(
                select(MatchMetricsModel)
                .where(MatchMetricsModel.match_id == match_id)
                .order_by(desc(MatchMetricsModel.minute))
                .limit(1)
            )
            latest_metrics = metrics_result.scalar_one_or_none()
            
            # Get signals for this match
            signals_result = await session.execute(
                select(Signal).where(Signal.match_id == match_id)
            )
            signals = signals_result.scalars().all()
            
            return {
                'match_info': {
                    'id': match.id,
                    'match_id': match.match_id,
                    'home_team': match.home_team,
                    'away_team': match.away_team,
                    'league': match.league,
                    'minute': match.minute,
                    'score': f"{match.home_score}:{match.away_score}",
                    'status': match.status
                },
                'latest_metrics': latest_metrics.to_dict() if latest_metrics else {},
                'signals': [
                    {
                        'strategy': signal.strategy_name,
                        'type': signal.signal_type,
                        'confidence': signal.confidence,
                        'prediction': signal.prediction,
                        'minute': signal.trigger_minute,
                        'result': signal.result,
                        'profit_loss': signal.profit_loss
                    }
                    for signal in signals
                ],
                'total_signals': len(signals),
                'pending_signals': len([s for s in signals if s.result == 'pending'])
            }
            
        except Exception as e:
            self.logger.error(f"Error getting match summary: {str(e)}")
            return {}
