import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
import json

from config import Config
from models import Signal, Match
from api_client import APIClient
from simple_menu_bot import SimpleTelegramMenuBot
from logger import BetBogLogger
from database import AsyncSessionLocal

class ResultTracker:
    """Tracks and resolves betting signal results"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("RESULT_TRACKER")
        
        # Components (will be injected)
        self.api_client: Optional[APIClient] = None
        self.telegram_bot: Optional[SimpleTelegramMenuBot] = None
        
        # Result evaluation rules
        self.result_evaluators = {
            'over_1.5': self._evaluate_over_goals,
            'over_2.5': self._evaluate_over_goals,
            'over_3.5': self._evaluate_over_goals,
            'btts': self._evaluate_btts,
            'first_goal': self._evaluate_first_goal,
            'next_goal': self._evaluate_next_goal,
            'late_goal': self._evaluate_late_goal,
            'team_to_score': self._evaluate_team_to_score,
            'team_performance': self._evaluate_team_performance
        }
    
    async def initialize(self, api_client: APIClient, telegram_bot: SimpleTelegramMenuBot):
        """Initialize with required components"""
        self.api_client = api_client
        self.telegram_bot = telegram_bot
        self.logger.success("Result tracker initialized")
    
    async def check_pending_results(self):
        """Check and resolve pending signal results"""
        try:
            async with AsyncSessionLocal() as session:
                # Get pending signals from matches that might have finished
                result = await session.execute(
                    select(Signal, Match)
                    .join(Match, Signal.match_id == Match.id)
                    .where(
                        and_(
                            Signal.result == 'pending',
                            Signal.created_at >= datetime.now() - timedelta(hours=6)  # Recent signals only
                        )
                    )
                )
                pending_signals = result.all()
                
                if not pending_signals:
                    self.logger.debug("No pending signals to check")
                    return
                
                self.logger.info(f"Checking {len(pending_signals)} pending signals")
                
                resolved_count = 0
                for signal, match in pending_signals:
                    try:
                        resolved = await self._resolve_signal_result(session, signal, match)
                        if resolved:
                            resolved_count += 1
                    except Exception as e:
                        self.logger.error(f"Error resolving signal {signal.id}: {str(e)}")
                
                await session.commit()
                
                if resolved_count > 0:
                    self.logger.success(f"Resolved {resolved_count} signal results")
                
        except Exception as e:
            self.logger.error(f"Error checking pending results: {str(e)}")
    
    async def _resolve_signal_result(self, 
                                   session: AsyncSession, 
                                   signal: Signal, 
                                   match: Match) -> bool:
        """Resolve the result of a single signal"""
        try:
            # First try to get updated live match data
            async with self.api_client:
                match_details = await self.api_client.get_match_details(match.match_id)
            
            # If not found in live matches, search by direct match ID
            if not match_details:
                self.logger.debug(f"Match {match.match_id} not found in live matches, searching by ID")
                async with self.api_client:
                    match_details = await self.api_client.get_match_by_id(str(match.match_id))
                
                # If direct ID search fails, fallback to finished matches search
                if not match_details:
                    self.logger.debug(f"Direct ID search failed, searching finished matches")
                    async with self.api_client:
                        finished_matches = await self.api_client.get_finished_matches(days_back=2)
                        
                        # Find match by ID or by team names and date
                        for finished_match in finished_matches:
                            if (finished_match.get('id') == match.match_id or 
                                (finished_match.get('home_team') == match.home_team and 
                                 finished_match.get('away_team') == match.away_team)):
                                match_details = finished_match
                                self.logger.info(f"Found match {match.match_id} in finished matches")
                                break
                
                if not match_details:
                    self.logger.debug(f"No data found for match {match.match_id} in live or finished matches")
                    return False
            
            # Parse updated match info
            updated_match = self.api_client.parse_match_data(match_details)
            current_minute = updated_match.get('minute', match.minute)
            match_status = updated_match.get('status', match.status)
            
            # Update match record
            match.minute = current_minute
            match.status = match_status
            match.home_score = updated_match.get('home_score', match.home_score)
            match.away_score = updated_match.get('away_score', match.away_score)
            match.updated_at = datetime.now()
            
            # Check if we can resolve the signal
            can_resolve, result, explanation = await self._can_resolve_signal(signal, match, current_minute)
            
            if can_resolve:
                # Calculate profit/loss
                profit_loss = self._calculate_profit_loss(signal, result)
                
                # Update signal
                signal.result = result
                signal.profit_loss = profit_loss
                signal.resolved_at = datetime.now()
                
                self.logger.info(f"Resolved signal {signal.id}: {result} | P&L: {profit_loss:+.2f} | {explanation}")
                
                # Send notification
                await self._send_result_notification(signal, match, result, profit_loss)
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error resolving signal result: {str(e)}")
            return False
    
    async def _can_resolve_signal(self, 
                                signal: Signal, 
                                match: Match, 
                                current_minute: int) -> Tuple[bool, str, str]:
        """Determine if a signal can be resolved and what the result is"""
        
        signal_type = signal.signal_type
        trigger_minute = signal.trigger_minute
        
        # Check if match has progressed enough to resolve
        time_since_signal = current_minute - trigger_minute
        
        # Different resolution criteria based on signal type
        if signal_type in ['over_1.5', 'over_2.5', 'over_3.5']:
            # Over/under goals - can resolve when match finishes or target is reached
            if match.status in ['finished', 'ft'] or current_minute >= 90:
                result, explanation = self._evaluate_over_goals(signal, match)
                return True, result, explanation
            else:
                # Check if target already reached
                total_goals = match.home_score + match.away_score
                target = float(signal_type.split('_')[1])
                if total_goals > target:
                    return True, 'win', f"Target {target} exceeded with {total_goals} goals"
        
        elif signal_type == 'btts':
            # Both teams to score - can resolve when both score or match finishes
            if match.home_score > 0 and match.away_score > 0:
                return True, 'win', "Both teams scored"
            elif match.status in ['finished', 'ft'] or current_minute >= 90:
                result, explanation = self._evaluate_btts(signal, match)
                return True, result, explanation
        
        elif signal_type in ['first_goal', 'next_goal']:
            # Goal-related signals - resolve when goal scored or reasonable time passed
            if time_since_signal >= 15:  # 15 minutes since signal
                result, explanation = self._evaluate_goal_signals(signal, match)
                return True, result, explanation
        
        elif signal_type == 'late_goal':
            # Late goal signals - resolve at match end
            if match.status in ['finished', 'ft'] or current_minute >= 90:
                result, explanation = self._evaluate_late_goal(signal, match)
                return True, result, explanation
        
        elif signal_type == 'team_to_score':
            # Team to score - resolve when team scores or match finishes
            result, explanation = self._evaluate_team_scoring(signal, match, current_minute)
            if result != 'pending':
                return True, result, explanation
        
        elif signal_type == 'team_performance':
            # Performance signals - resolve after reasonable time
            if time_since_signal >= 20:  # 20 minutes to evaluate performance
                result, explanation = self._evaluate_team_performance(signal, match)
                return True, result, explanation
        
        # Default: cannot resolve yet
        return False, 'pending', 'Insufficient time or data to resolve'
    
    def _evaluate_over_goals(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate over/under goals signals"""
        target = float(signal.signal_type.split('_')[1])
        total_goals = match.home_score + match.away_score
        
        if total_goals > target:
            return 'win', f"Over {target}: {total_goals} goals scored"
        else:
            return 'loss', f"Under {target}: only {total_goals} goals scored"
    
    def _evaluate_btts(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate both teams to score signals"""
        if match.home_score > 0 and match.away_score > 0:
            return 'win', f"BTTS: {match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
        else:
            return 'loss', f"BTTS failed: {match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
    
    def _evaluate_goal_signals(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate first goal / next goal signals"""
        # This is simplified - in reality would need to track goals during the signal period
        trigger_metrics = signal.trigger_metrics or {}
        leading_team = trigger_metrics.get('leading_team', 'home')
        
        # Compare current score to what it was at signal time
        # For now, simplified logic based on final score
        if leading_team == 'home' and match.home_score > match.away_score:
            return 'win', f"Home team goal prediction correct"
        elif leading_team == 'away' and match.away_score > match.home_score:
            return 'win', f"Away team goal prediction correct"
        else:
            return 'loss', f"Goal prediction incorrect"
    
    def _evaluate_first_goal(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate first goal signals"""
        return self._evaluate_goal_signals(signal, match)
    
    def _evaluate_next_goal(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate next goal signals"""
        return self._evaluate_goal_signals(signal, match)
    
    def _evaluate_late_goal(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate late goal signals"""
        trigger_metrics = signal.trigger_metrics or {}
        advantage_team = trigger_metrics.get('advantage_team', 'home')
        
        # Check if the advantaged team scored in late period (simplified)
        total_goals = match.home_score + match.away_score
        if total_goals > 0:  # Some goal was scored
            if advantage_team == 'home' and match.home_score > 0:
                return 'win', f"Late goal by advantaged team ({advantage_team})"
            elif advantage_team == 'away' and match.away_score > 0:
                return 'win', f"Late goal by advantaged team ({advantage_team})"
        
        return 'loss', f"No late goal by advantaged team ({advantage_team})"
    
    def _evaluate_team_to_score(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate team to score signals"""
        trigger_metrics = signal.trigger_metrics or {}
        efficient_team = trigger_metrics.get('efficient_team', 'home')
        
        if efficient_team == 'home' and match.home_score > 0:
            return 'win', f"Home team scored as predicted"
        elif efficient_team == 'away' and match.away_score > 0:
            return 'win', f"Away team scored as predicted"
        elif match.status in ['finished', 'ft']:
            return 'loss', f"Predicted team ({efficient_team}) did not score"
        else:
            return 'pending', "Match still in progress"
    
    def _evaluate_team_scoring(self, signal: Signal, match: Match, current_minute: int) -> Tuple[str, str]:
        """Evaluate team scoring predictions"""
        return self._evaluate_team_to_score(signal, match)
    
    def _evaluate_team_performance(self, signal: Signal, match: Match) -> Tuple[str, str]:
        """Evaluate team performance signals"""
        trigger_metrics = signal.trigger_metrics or {}
        trending_team = trigger_metrics.get('trending_team', 'home')
        
        # Simplified performance evaluation based on final result
        if trending_team == 'home':
            if match.home_score > match.away_score:
                return 'win', f"Home team performance prediction correct"
            elif match.home_score == match.away_score:
                return 'push', f"Draw - neutral result for home performance"
            else:
                return 'loss', f"Home team performance prediction incorrect"
        else:
            if match.away_score > match.home_score:
                return 'win', f"Away team performance prediction correct"
            elif match.home_score == match.away_score:
                return 'push', f"Draw - neutral result for away performance"
            else:
                return 'loss', f"Away team performance prediction incorrect"
    
    def _calculate_profit_loss(self, signal: Signal, result: str) -> float:
        """Calculate profit/loss for a signal result"""
        stake = signal.stake
        odds = signal.odds or 2.0  # Default odds if not specified
        
        if result == 'win':
            # Profit = (odds - 1) * stake
            profit = (odds - 1) * stake
        elif result == 'loss':
            # Loss = -stake
            profit = -stake
        elif result == 'push':
            # Push = no profit/loss
            profit = 0.0
        else:
            profit = 0.0
        
        return round(profit, 2)
    
    async def _send_result_notification(self, 
                                      signal: Signal, 
                                      match: Match, 
                                      result: str, 
                                      profit_loss: float):
        """Send result notification via Telegram"""
        try:
            signal_data = {
                'strategy_name': signal.strategy_name,
                'signal_type': signal.signal_type,
                'confidence': signal.confidence,
                'prediction': signal.prediction,
                'trigger_minute': signal.trigger_minute
            }
            
            match_data = {
                'home_team': match.home_team,
                'away_team': match.away_team,
                'league': match.league
            }
            
            await self.telegram_bot.send_result_notification(
                signal_data, match_data, result, profit_loss
            )
            
        except Exception as e:
            self.logger.error(f"Error sending result notification: {str(e)}")
    
    async def get_pending_signals_summary(self) -> Dict[str, Any]:
        """Get summary of pending signals"""
        try:
            async with AsyncSessionLocal() as session:
                # Get all pending signals
                result = await session.execute(
                    select(Signal, Match)
                    .join(Match, Signal.match_id == Match.id)
                    .where(Signal.result == 'pending')
                )
                pending_signals = result.all()
                
                summary = {
                    'total_pending': len(pending_signals),
                    'by_strategy': {},
                    'by_signal_type': {},
                    'oldest_signal': None,
                    'newest_signal': None,
                    'total_stake': 0.0
                }
                
                if not pending_signals:
                    return summary
                
                # Analyze pending signals
                oldest_date = None
                newest_date = None
                
                for signal, match in pending_signals:
                    # Count by strategy
                    strategy = signal.strategy_name
                    if strategy not in summary['by_strategy']:
                        summary['by_strategy'][strategy] = 0
                    summary['by_strategy'][strategy] += 1
                    
                    # Count by signal type
                    signal_type = signal.signal_type
                    if signal_type not in summary['by_signal_type']:
                        summary['by_signal_type'][signal_type] = 0
                    summary['by_signal_type'][signal_type] += 1
                    
                    # Track dates
                    signal_date = signal.created_at
                    if oldest_date is None or signal_date < oldest_date:
                        oldest_date = signal_date
                    if newest_date is None or signal_date > newest_date:
                        newest_date = signal_date
                    
                    # Sum stakes
                    summary['total_stake'] += signal.stake
                
                summary['oldest_signal'] = oldest_date.isoformat() if oldest_date else None
                summary['newest_signal'] = newest_date.isoformat() if newest_date else None
                
                return summary
                
        except Exception as e:
            self.logger.error(f"Error getting pending signals summary: {str(e)}")
            return {'error': str(e)}
    
    async def force_resolve_old_signals(self, hours_old: int = 6):
        """Force resolve signals that are too old"""
        try:
            async with AsyncSessionLocal() as session:
                cutoff_time = datetime.now() - timedelta(hours=hours_old)
                
                # Get old pending signals
                result = await session.execute(
                    select(Signal, Match)
                    .join(Match, Signal.match_id == Match.id)
                    .where(
                        and_(
                            Signal.result == 'pending',
                            Signal.created_at < cutoff_time
                        )
                    )
                )
                old_signals = result.all()
                
                if not old_signals:
                    return
                
                resolved_count = 0
                for signal, match in old_signals:
                    # Force resolve as loss if too old
                    signal.result = 'loss'
                    signal.profit_loss = -signal.stake
                    signal.resolved_at = datetime.now()
                    resolved_count += 1
                    
                    self.logger.warning(f"Force resolved old signal {signal.id} as loss")
                
                await session.commit()
                self.logger.info(f"Force resolved {resolved_count} old signals")
                
        except Exception as e:
            self.logger.error(f"Error force resolving old signals: {str(e)}")
