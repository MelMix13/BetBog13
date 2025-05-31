import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from database import get_session, AsyncSessionLocal
from models import Signal, Match, StrategyConfig, SystemLog
from logger import BetBogLogger

class TelegramBot:
    """Advanced Telegram bot for BetBog monitoring"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("BOT")
        self.app: Optional[Application] = None
        self.authorized_users: set = set()
        self.user_settings: Dict[int, Dict] = {}
        
    async def initialize(self):
        """Initialize the Telegram bot"""
        try:
            self.app = Application.builder().token(self.config.BOT_TOKEN).build()
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            self.app.add_handler(CommandHandler("status", self.status_command))
            self.app.add_handler(CommandHandler("signals", self.signals_command))
            self.app.add_handler(CommandHandler("performance", self.performance_command))
            self.app.add_handler(CommandHandler("matches", self.matches_command))
            self.app.add_handler(CommandHandler("strategies", self.strategies_command))
            self.app.add_handler(CommandHandler("settings", self.settings_command))
            self.app.add_handler(CallbackQueryHandler(self.button_callback))
            
            self.logger.success("Telegram bot initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize bot: {str(e)}")
            raise
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        # Add user to authorized users (in production, implement proper auth)
        self.authorized_users.add(user_id)
        
        welcome_message = (
            "🏆 *Welcome to BetBog Monitoring Bot!*\n\n"
            "🤖 I'm your intelligent betting assistant with:\n"
            "• 📊 Advanced derived metrics analysis\n"
            "• 🎯 Adaptive ML-powered strategies\n"
            "• 📈 Real-time performance tracking\n"
            "• ⚡ Live match monitoring\n\n"
            "Use /help to see all available commands!"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Live Signals", callback_data="live_signals")],
            [InlineKeyboardButton("📈 Performance", callback_data="performance"),
             InlineKeyboardButton("⚽ Matches", callback_data="live_matches")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
             InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        self.logger.bot_notification(str(user_id), "welcome", True)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "🤖 *BetBog Bot Commands:*\n\n"
            "📊 *Monitoring:*\n"
            "/status - System status overview\n"
            "/signals - Recent betting signals\n"
            "/matches - Live matches being monitored\n\n"
            "📈 *Analytics:*\n"
            "/performance - Strategy performance stats\n"
            "/strategies - Available strategies info\n\n"
            "⚙️ *Settings:*\n"
            "/settings - Configure notifications\n\n"
            "💡 *Pro Tips:*\n"
            "• Use inline buttons for quick access\n"
            "• Enable notifications for real-time alerts\n"
            "• Check performance regularly for insights"
        )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # Get recent signals count
                recent_signals = await session.execute(
                    select(func.count(Signal.id)).where(
                        Signal.created_at >= datetime.now() - timedelta(hours=24)
                    )
                )
                signals_24h = recent_signals.scalar() or 0
                
                # Get active matches count
                active_matches = await session.execute(
                    select(func.count(Match.id)).where(
                        Match.status == 'live'
                    )
                )
                live_matches = active_matches.scalar() or 0
                
                # Get pending signals count
                pending_signals = await session.execute(
                    select(func.count(Signal.id)).where(
                        Signal.result == 'pending'
                    )
                )
                pending = pending_signals.scalar() or 0
                
                status_message = (
                    "🏆 *BetBog System Status*\n\n"
                    f"🟢 Status: *Active*\n"
                    f"⚽ Live Matches: *{live_matches}*\n"
                    f"🎯 Signals (24h): *{signals_24h}*\n"
                    f"⏳ Pending Results: *{pending}*\n"
                    f"🕐 Last Update: *{datetime.now().strftime('%H:%M:%S')}*\n\n"
                    "All systems operational! 🚀"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")],
                    [InlineKeyboardButton("📊 Live Signals", callback_data="live_signals")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    status_message, 
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            self.logger.error(f"Error in status command: {str(e)}")
            await update.message.reply_text("❌ Error retrieving status.")
    
    async def signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # Get recent signals
                result = await session.execute(
                    select(Signal).join(Match)
                    .where(Signal.created_at >= datetime.now() - timedelta(hours=6))
                    .order_by(Signal.created_at.desc())
                    .limit(10)
                )
                signals = result.scalars().all()
                
                if not signals:
                    await update.message.reply_text("📭 No recent signals found.")
                    return
                
                message = "🎯 *Recent Betting Signals:*\n\n"
                
                for signal in signals:
                    # Get match info
                    match_result = await session.execute(
                        select(Match).where(Match.id == signal.match_id)
                    )
                    match = match_result.scalar_one_or_none()
                    
                    if match:
                        status_emoji = self._get_signal_status_emoji(signal.result)
                        time_str = signal.created_at.strftime("%H:%M")
                        
                        message += (
                            f"{status_emoji} *{signal.strategy_name}*\n"
                            f"⚽ {match.home_team} vs {match.away_team}\n"
                            f"🎯 {signal.prediction}\n"
                            f"📊 Confidence: {signal.confidence:.1%}\n"
                            f"🕐 {time_str} | {signal.trigger_minute}'\n"
                        )
                        
                        if signal.result != 'pending':
                            pl_emoji = "💰" if signal.profit_loss > 0 else "📉"
                            message += f"{pl_emoji} P&L: {signal.profit_loss:+.2f}\n"
                        
                        message += "\n"
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_signals")],
                    [InlineKeyboardButton("📈 Performance", callback_data="performance")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    message, 
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            self.logger.error(f"Error in signals command: {str(e)}")
            await update.message.reply_text("❌ Error retrieving signals.")
    
    async def performance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # Get strategy performance
                strategies_result = await session.execute(select(StrategyConfig))
                strategies = strategies_result.scalars().all()
                
                if not strategies:
                    await update.message.reply_text("📊 No strategy data available yet.")
                    return
                
                message = "📈 *Strategy Performance:*\n\n"
                
                total_profit = 0
                total_signals = 0
                
                for strategy in strategies:
                    roi = strategy.roi or 0
                    win_rate = (strategy.winning_signals / max(strategy.total_signals, 1)) * 100
                    
                    roi_emoji = "🟢" if roi > 0 else "🔴" if roi < 0 else "🟡"
                    
                    message += (
                        f"{roi_emoji} *{strategy.strategy_name}*\n"
                        f"💰 ROI: {roi:+.1%}\n"
                        f"🎯 Win Rate: {win_rate:.1f}%\n"
                        f"📊 Signals: {strategy.total_signals}\n"
                        f"💵 Profit: {strategy.total_profit:+.2f}\n\n"
                    )
                    
                    total_profit += strategy.total_profit
                    total_signals += strategy.total_signals
                
                # Overall summary
                overall_roi = total_profit / max(total_signals, 1) * 100
                message += (
                    f"📊 *Overall Performance:*\n"
                    f"💰 Total Profit: {total_profit:+.2f}\n"
                    f"🎯 Total Signals: {total_signals}\n"
                    f"📈 Average ROI: {overall_roi:+.1f}%"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_performance")],
                    [InlineKeyboardButton("📊 Strategies", callback_data="strategies_detail")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    message, 
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            self.logger.error(f"Error in performance command: {str(e)}")
            await update.message.reply_text("❌ Error retrieving performance data.")
    
    async def matches_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /matches command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # Get live matches
                result = await session.execute(
                    select(Match).where(Match.status == 'live')
                    .order_by(Match.minute.desc())
                    .limit(10)
                )
                matches = result.scalars().all()
                
                if not matches:
                    await update.message.reply_text("⚽ No live matches currently being monitored.")
                    return
                
                message = "⚽ *Live Matches Being Monitored:*\n\n"
                
                for match in matches:
                    score = f"{match.home_score}:{match.away_score}"
                    minute = match.minute or 0
                    
                    message += (
                        f"🏟 *{match.home_team}* vs *{match.away_team}*\n"
                        f"⚽ Score: {score}\n"
                        f"⏱ Minute: {minute}'\n"
                        f"🏆 {match.league}\n\n"
                    )
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_matches")],
                    [InlineKeyboardButton("🎯 Recent Signals", callback_data="live_signals")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    message, 
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            self.logger.error(f"Error in matches command: {str(e)}")
            await update.message.reply_text("❌ Error retrieving matches.")
    
    async def strategies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /strategies command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        strategies_info = (
            "🧠 *Available Betting Strategies:*\n\n"
            
            "🎯 *dxG Spike*\n"
            "Detects sudden increases in derived Expected Goals\n"
            "Signals: Over/Under, BTTS\n\n"
            
            "⚡ *Momentum Shift*\n"
            "Identifies team momentum changes\n"
            "Signals: Next Goal, First Goal\n\n"
            
            "💪 *Tiredness Advantage*\n"
            "Spots fitness advantages in late game\n"
            "Signals: Late Goals\n\n"
            
            "🎯 *Shots Efficiency*\n"
            "Analyzes shot conversion rates\n"
            "Signals: Team to Score\n\n"
            
            "🌊 *Wave Pattern*\n"
            "Detects match volatility patterns\n"
            "Signals: Total Goals\n\n"
            
            "📈 *Gradient Breakout*\n"
            "Tracks performance trend breaks\n"
            "Signals: Team Performance\n\n"
            
            "⚡ *Stability Disruption*\n"
            "Identifies chaotic match periods\n"
            "Signals: Goals in Chaos\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Performance", callback_data="performance")],
            [InlineKeyboardButton("⚙️ Configure", callback_data="strategy_config")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            strategies_info, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        current_settings = self.user_settings.get(user_id, {
            'notifications': True,
            'min_confidence': 0.7,
            'strategies': 'all',
            'profit_alerts': True
        })
        
        settings_text = (
            "⚙️ *Your Settings:*\n\n"
            f"🔔 Notifications: {'✅ On' if current_settings['notifications'] else '❌ Off'}\n"
            f"📊 Min Confidence: {current_settings['min_confidence']:.0%}\n"
            f"🎯 Strategies: {current_settings['strategies']}\n"
            f"💰 P&L Alerts: {'✅ On' if current_settings['profit_alerts'] else '❌ Off'}\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔔 Toggle Notifications", callback_data="toggle_notifications")],
            [InlineKeyboardButton("📊 Confidence Level", callback_data="set_confidence")],
            [InlineKeyboardButton("🎯 Strategy Filter", callback_data="filter_strategies")],
            [InlineKeyboardButton("💰 P&L Alerts", callback_data="toggle_profit_alerts")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            settings_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if not self._is_authorized(user_id):
            await query.edit_message_text("❌ Access denied.")
            return
        
        data = query.data
        
        if data == "live_signals":
            await self._handle_live_signals_callback(query)
        elif data == "performance":
            await self._handle_performance_callback(query)
        elif data == "live_matches":
            await self._handle_matches_callback(query)
        elif data == "settings":
            await self._handle_settings_callback(query)
        elif data == "help":
            await self._handle_help_callback(query)
        elif data.startswith("refresh_"):
            await self._handle_refresh_callback(query, data)
        elif data.startswith("toggle_"):
            await self._handle_toggle_callback(query, data, user_id)
        else:
            await query.edit_message_text("❓ Unknown action.")
    
    async def send_signal_notification(self, 
                                     signal_data: Dict[str, Any],
                                     match_data: Dict[str, Any]):
        """Send signal notification to all authorized users"""
        
        notification_text = (
            f"🎯 *NEW BETTING SIGNAL!*\n\n"
            f"⚽ *{match_data['home_team']}* vs *{match_data['away_team']}*\n"
            f"🏆 {match_data.get('league', 'Unknown League')}\n"
            f"⏱ Minute: {signal_data['trigger_minute']}'\n\n"
            f"🧠 Strategy: *{signal_data['strategy_name']}*\n"
            f"🎯 Prediction: *{signal_data['prediction']}*\n"
            f"📊 Confidence: *{signal_data['confidence']:.1%}*\n"
            f"💰 Recommended Odds: *{signal_data.get('recommended_odds', 'N/A')}*\n\n"
            f"📝 Reasoning: {signal_data.get('reasoning', 'N/A')}"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View All Signals", callback_data="live_signals")],
            [InlineKeyboardButton("📈 Performance", callback_data="performance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_count = 0
        for user_id in self.authorized_users:
            user_settings = self.user_settings.get(user_id, {})
            
            # Check user notification preferences
            if not user_settings.get('notifications', True):
                continue
            
            min_confidence = user_settings.get('min_confidence', 0.7)
            if signal_data['confidence'] < min_confidence:
                continue
            
            try:
                await self.app.bot.send_message(
                    chat_id=user_id,
                    text=notification_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                sent_count += 1
                self.logger.bot_notification(str(user_id), "signal", True)
                
            except Exception as e:
                self.logger.error(f"Failed to send notification to {user_id}: {str(e)}")
                self.logger.bot_notification(str(user_id), "signal", False)
        
        self.logger.info(f"Signal notification sent to {sent_count} users")
    
    async def send_result_notification(self, 
                                     signal_data: Dict[str, Any],
                                     match_data: Dict[str, Any],
                                     result: str,
                                     profit_loss: float):
        """Send result notification to users who want P&L alerts"""
        
        result_emoji = "✅" if result == "win" else "❌" if result == "loss" else "➖"
        profit_emoji = "💰" if profit_loss > 0 else "📉" if profit_loss < 0 else "➖"
        
        notification_text = (
            f"{result_emoji} *SIGNAL RESULT*\n\n"
            f"⚽ *{match_data['home_team']}* vs *{match_data['away_team']}*\n"
            f"🎯 {signal_data['prediction']}\n"
            f"📊 Confidence: {signal_data['confidence']:.1%}\n\n"
            f"🏁 Result: *{result.upper()}*\n"
            f"{profit_emoji} P&L: *{profit_loss:+.2f} units*\n"
        )
        
        sent_count = 0
        for user_id in self.authorized_users:
            user_settings = self.user_settings.get(user_id, {})
            
            if not user_settings.get('profit_alerts', True):
                continue
            
            try:
                await self.app.bot.send_message(
                    chat_id=user_id,
                    text=notification_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                sent_count += 1
                self.logger.bot_notification(str(user_id), "result", True)
                
            except Exception as e:
                self.logger.error(f"Failed to send result to {user_id}: {str(e)}")
        
        self.logger.info(f"Result notification sent to {sent_count} users")
    
    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized (simplified for demo)"""
        # In production, implement proper authorization logic
        return user_id in self.authorized_users or len(self.authorized_users) == 0
    
    def _get_signal_status_emoji(self, result: str) -> str:
        """Get emoji for signal status"""
        status_map = {
            'win': '✅',
            'loss': '❌',
            'push': '➖',
            'pending': '⏳'
        }
        return status_map.get(result, '❓')
    
    async def _handle_live_signals_callback(self, query):
        """Handle live signals button callback"""
        # This would call the signals command logic
        await query.edit_message_text("🔄 Loading live signals...")
        # Implement similar to signals_command but for callback
    
    async def _handle_performance_callback(self, query):
        """Handle performance button callback"""
        await query.edit_message_text("🔄 Loading performance data...")
        # Implement similar to performance_command but for callback
    
    async def _handle_matches_callback(self, query):
        """Handle matches button callback"""
        await query.edit_message_text("🔄 Loading live matches...")
        # Implement similar to matches_command but for callback
    
    async def _handle_settings_callback(self, query):
        """Handle settings button callback"""
        await query.edit_message_text("🔄 Loading settings...")
        # Implement similar to settings_command but for callback
    
    async def _handle_help_callback(self, query):
        """Handle help button callback"""
        help_text = (
            "🤖 *BetBog Bot Help*\n\n"
            "Use the buttons below or type commands:\n"
            "/start - Welcome message\n"
            "/status - System overview\n"
            "/signals - Recent signals\n"
            "/performance - Strategy stats\n"
            "/matches - Live matches\n"
            "/settings - Configure bot\n"
        )
        await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def _handle_refresh_callback(self, query, data):
        """Handle refresh button callbacks"""
        await query.edit_message_text("🔄 Refreshing data...")
        # Implement refresh logic based on data parameter
    
    async def _handle_toggle_callback(self, query, data, user_id):
        """Handle toggle button callbacks"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        
        if data == "toggle_notifications":
            current = self.user_settings[user_id].get('notifications', True)
            self.user_settings[user_id]['notifications'] = not current
            status = "enabled" if not current else "disabled"
            await query.edit_message_text(f"🔔 Notifications {status}!")
        
        elif data == "toggle_profit_alerts":
            current = self.user_settings[user_id].get('profit_alerts', True)
            self.user_settings[user_id]['profit_alerts'] = not current
            status = "enabled" if not current else "disabled"
            await query.edit_message_text(f"💰 P&L alerts {status}!")
    
    async def start_bot(self):
        """Start the bot polling"""
        if not self.app:
            await self.initialize()
        
        self.logger.header("Starting Telegram Bot")
        await self.app.run_polling(drop_pending_updates=True)
    
    async def stop_bot(self):
        """Stop the bot"""
        if self.app:
            await self.app.shutdown()
            self.logger.info("Telegram bot stopped")
