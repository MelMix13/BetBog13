#!/usr/bin/env python3
"""
Реальный Telegram бот для BetBog с настоящим Bot API
Работает с python-telegram-bot библиотекой
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import Config
from logger import BetBogLogger
from database import AsyncSessionLocal
from models import Signal, Match, StrategyConfig
from sqlalchemy import select, desc, func


class RealTelegramBot:
    """Реальный Telegram бот для BetBog"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("TELEGRAM_BOT", config.LOG_FILE)
        self.application = None
        self.authorized_users = {123456789}  # Добавьте свой Telegram ID
        
    async def initialize(self):
        """Инициализация Telegram бота"""
        try:
            # Создаем приложение с токеном бота
            self.application = Application.builder().token(self.config.BOT_TOKEN).build()
            
            # Добавляем обработчики команд
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("menu", self.menu_command))
            self.application.add_handler(CommandHandler("signals", self.signals_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("matches", self.matches_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            # Добавляем обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            self.logger.success("🤖 Реальный Telegram бот инициализирован")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации бота: {str(e)}")
            return False

    def _is_authorized(self, user_id: int) -> bool:
        """Проверка авторизации пользователя"""
        return user_id in self.authorized_users

    def _get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Создание главного меню с кнопками"""
        keyboard = [
            [
                InlineKeyboardButton("🎯 Сигналы", callback_data="signals"),
                InlineKeyboardButton("📊 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton("⚽ Live Матчи", callback_data="matches"),
                InlineKeyboardButton("🔧 Стратегии", callback_data="strategies")
            ],
            [
                InlineKeyboardButton("📈 P&L Отчет", callback_data="pnl"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ],
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        welcome_text = """
╭─────────────────────────────────────────╮
│         🎯 Добро пожаловать в BetBog     │
╰─────────────────────────────────────────╯

🤖 Интеллектуальная система мониторинга ставок

🟢 Система активна и анализирует live матчи
📊 7 стратегий работают в реальном времени
🎯 Поиск сигналов с высокой точностью

Выберите нужный раздел:
        """
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=self._get_main_menu_keyboard()
        )

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        await update.message.reply_text(
            "📋 Главное меню BetBog:",
            reply_markup=self._get_main_menu_keyboard()
        )

    async def signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать сигналы"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        try:
            session = AsyncSessionLocal()
            try:
                # Получаем статистику сигналов
                total_signals = await session.scalar(select(func.count(Signal.id)))
                active_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "pending")
                )
                won_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "won")
                )
                lost_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "lost")
                )

                # Получаем последние активные сигналы
                stmt = (
                    select(Signal)
                    .where(Signal.result == "pending")
                    .order_by(desc(Signal.created_at))
                    .limit(5)
                )
                signals = await session.scalars(stmt)
                signals_list = list(signals)

                winrate = (won_signals / max(won_signals + lost_signals, 1) * 100) if (won_signals or lost_signals) else 0
            except Exception as e:
                self.logger.error(f"Ошибка получения статистики сигналов: {e}")
                total_signals = active_signals = won_signals = lost_signals = 0
                signals_list = []
                winrate = 0
            finally:
                await session.close()

            signals_text = f"""
╭─────────────────────────────────────────╮
│           🎯 Сигналы BetBog              │
╰─────────────────────────────────────────╯

📊 Общая статистика:
• Всего сигналов: {total_signals or 0}
• Активных: {active_signals or 0}
• Выиграно: {won_signals or 0} 
• Проиграно: {lost_signals or 0}
• Winrate: {winrate:.1f}%

🔴 Активные сигналы:
            """

            if not signals_list:
                signals_text += "\n❌ Нет активных сигналов"
            else:
                for i, signal in enumerate(signals_list, 1):
                    confidence_emoji = "🔥" if signal.confidence > 0.8 else "⚡" if signal.confidence > 0.6 else "📈"
                    signals_text += f"""
{i}. {confidence_emoji} {signal.strategy_name}
   📊 {signal.signal_type} | {signal.confidence:.1%}
   💰 Размер: {signal.bet_size:.2f}
                    """

            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="refresh_signals"),
                    InlineKeyboardButton("📋 Меню", callback_data="main_menu")
                ]
            ]
            
            await update.message.reply_text(
                signals_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка показа сигналов: {str(e)}")
            await update.message.reply_text("❌ Ошибка получения данных о сигналах")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        try:
            async with AsyncSessionLocal() as session:
                # Базовая статистика
                total_signals = await session.scalar(select(func.count(Signal.id)))
                won_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "won")
                )
                lost_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "lost")
                )
                
                # P&L
                total_pnl_result = await session.scalar(
                    select(func.sum(Signal.profit_loss)).where(Signal.profit_loss.isnot(None))
                )
                total_pnl = total_pnl_result or 0
                
                completed_signals = (won_signals or 0) + (lost_signals or 0)
                winrate = (won_signals / completed_signals * 100) if completed_signals > 0 else 0

            stats_text = f"""
╭─────────────────────────────────────────╮
│          📊 Статистика BetBog            │
╰─────────────────────────────────────────╯

📈 Общие показатели:
• Всего сигналов: {total_signals or 0}
• Завершено: {completed_signals}
• Выиграно: {won_signals or 0}
• Проиграно: {lost_signals or 0}
• Winrate: {winrate:.1f}%

💰 Финансовые показатели:
• Общий P&L: {total_pnl:+.2f}
• ROI: {(total_pnl / max(completed_signals, 1) * 100):+.1f}%
• Средний результат: {(total_pnl / max(completed_signals, 1)):.2f}

🎯 Производительность:
• Активность: {(total_signals or 0) / max(1, 7):.1f} сигналов/день
• Эффективность: {'Высокая' if winrate > 60 else 'Средняя' if winrate > 45 else 'Требует улучшения'}
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats"),
                    InlineKeyboardButton("📋 Меню", callback_data="main_menu")
                ]
            ]
            
            await update.message.reply_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка показа статистики: {str(e)}")
            await update.message.reply_text("❌ Ошибка получения статистики")

    async def matches_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать live матчи"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        try:
            async with AsyncSessionLocal() as session:
                # Получаем последние матчи
                stmt = select(Match).order_by(desc(Match.updated_at)).limit(10)
                matches = await session.scalars(stmt)
                matches_list = list(matches)

            matches_text = """
╭─────────────────────────────────────────╮
│           ⚽ Live Матчи                   │
╰─────────────────────────────────────────╯
            """

            if not matches_list:
                matches_text += "\n❌ Нет активных матчей"
            else:
                matches_text += f"\n📊 Найдено {len(matches_list)} матчей:\n"
                
                for i, match in enumerate(matches_list[:5], 1):
                    status = "🔴 LIVE" if match.status == "live" else "⚪ Завершен"
                    matches_text += f"""
{i}. {status} {match.home_team} vs {match.away_team}
   📊 Счет: {match.home_score}:{match.away_score} | {match.minute}'
   🏆 Лига: {match.league}
                    """

            keyboard = [
                [
                    InlineKeyboardButton("🔄 Обновить", callback_data="refresh_matches"),
                    InlineKeyboardButton("📋 Меню", callback_data="main_menu")
                ]
            ]
            
            await update.message.reply_text(
                matches_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка показа матчей: {str(e)}")
            await update.message.reply_text("❌ Ошибка получения данных о матчах")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать помощь"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Нет доступа к боту")
            return

        help_text = """
╭─────────────────────────────────────────╮
│           ❓ Помощь BetBog               │
╰─────────────────────────────────────────╯

🤖 BetBog - система мониторинга ставок

📱 Основные команды:
• /start - Запуск и главное меню
• /menu - Главное меню
• /signals - Активные сигналы
• /stats - Статистика и P&L
• /matches - Live матчи
• /help - Эта справка

🎯 Функции системы:
• Анализ live футбольных матчей
• 7 адаптивных стратегий ставок
• Расчет продвинутых метрик (dxG, momentum, gradient)
• Отслеживание P&L и статистики
• Уведомления о новых сигналах

📊 Метрики:
• dxG - derived Expected Goals
• Gradient - тренд производительности  
• Momentum - импульс команд
• Wave - амплитуда интенсивности
• Tiredness - фактор усталости

Система работает 24/7 с реальными данными!
        """
        
        keyboard = [
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self._is_authorized(user_id):
            await query.answer("❌ Нет доступа к боту")
            return

        await query.answer()

        if query.data == "main_menu":
            await query.edit_message_text(
                "📋 Главное меню BetBog:",
                reply_markup=self._get_main_menu_keyboard()
            )
        elif query.data == "signals":
            # Перенаправляем на команду сигналов
            await self.signals_command(update, context)
        elif query.data == "stats":
            # Перенаправляем на команду статистики
            await self.stats_command(update, context)
        elif query.data == "matches":
            # Перенаправляем на команду матчей
            await self.matches_command(update, context)
        elif query.data == "help":
            # Перенаправляем на команду помощи
            await self.help_command(update, context)
        elif query.data.startswith("refresh_"):
            # Обновляем соответствующие данные
            section = query.data.replace("refresh_", "")
            if section == "main":
                await query.edit_message_text(
                    "📋 Главное меню BetBog (обновлено):",
                    reply_markup=self._get_main_menu_keyboard()
                )

    async def send_signal_notification(self, signal_data: Dict[str, Any], match_data: Dict[str, Any]):
        """Отправить уведомление о новом сигнале"""
        try:
            confidence = signal_data.get('confidence', 0)
            confidence_emoji = "🔥" if confidence > 0.8 else "⚡" if confidence > 0.6 else "📈"
            
            notification_text = f"""
╭─────────────────────────────────────────╮
│           🎯 НОВЫЙ СИГНАЛ СТАВКИ          │
╰─────────────────────────────────────────╯

{confidence_emoji} Стратегия: {signal_data.get('strategy_name', 'Unknown')}
⚽ Матч: {match_data.get('home_team', 'Unknown')} vs {match_data.get('away_team', 'Unknown')}
🎯 Тип: {signal_data.get('signal_type', 'Unknown')}
📊 Уверенность: {confidence:.1%}
💰 Размер ставки: {signal_data.get('bet_size', 0):.2f}
⏰ Время: {datetime.now().strftime('%H:%M:%S')}

📈 Ключевые метрики:
• dxG: {signal_data.get('details', {}).get('dxg_home', 0):.2f} - {signal_data.get('details', {}).get('dxg_away', 0):.2f}
• Momentum: {signal_data.get('details', {}).get('momentum', 0):.2f}
• Минута: {match_data.get('minute', 0)}'
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                    InlineKeyboardButton("📋 Меню", callback_data="main_menu")
                ]
            ]
            
            # Отправляем всем авторизованным пользователям
            for user_id in self.authorized_users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=notification_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
            
            self.logger.success("📱 Уведомление о сигнале отправлено")
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления: {str(e)}")

    async def send_result_notification(self, signal_data: Dict[str, Any], match_data: Dict[str, Any], result: str, profit_loss: float):
        """Отправить уведомление о результате"""
        try:
            result_emoji = "✅" if result == "won" else "❌" if result == "lost" else "⏳"
            pnl_emoji = "💚" if profit_loss > 0 else "❤️" if profit_loss < 0 else "💛"
            
            notification_text = f"""
╭─────────────────────────────────────────╮
│        📈 РЕЗУЛЬТАТ СИГНАЛА              │
╰─────────────────────────────────────────╯

{result_emoji} Результат: {result.upper()}
🎯 Стратегия: {signal_data.get('strategy_name', 'Unknown')}
⚽ Матч: {match_data.get('home_team', 'Unknown')} vs {match_data.get('away_team', 'Unknown')}
{pnl_emoji} P&L: {profit_loss:+.2f}
⏰ Время: {datetime.now().strftime('%H:%M:%S')}
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                    InlineKeyboardButton("📋 Меню", callback_data="main_menu")
                ]
            ]
            
            # Отправляем всем авторизованным пользователям
            for user_id in self.authorized_users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=notification_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки результата пользователю {user_id}: {e}")
            
            self.logger.success(f"📱 Уведомление о результате отправлено: {result}")
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления о результате: {str(e)}")

    async def start_polling(self):
        """Запуск бота в режиме polling"""
        try:
            if not self.application:
                self.logger.error("Бот не инициализирован")
                return
                
            self.logger.success("🚀 Telegram бот запущен в режиме polling")
            await self.application.run_polling()
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска polling: {str(e)}")

    async def stop_polling(self):
        """Остановка бота"""
        try:
            if self.application:
                await self.application.stop()
            self.logger.info("🛑 Telegram бот остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка остановки бота: {str(e)}")


# Функция для интеграции с основной системой
async def create_telegram_bot(config: Config) -> RealTelegramBot:
    """Создать и инициализировать реальный Telegram бота"""
    bot = RealTelegramBot(config)
    success = await bot.initialize()
    if not success:
        raise Exception("Не удалось инициализировать Telegram бота")
    return bot


if __name__ == "__main__":
    # Для тестирования
    async def main():
        config = Config()
        bot = await create_telegram_bot(config)
        await bot.start_polling()

    asyncio.run(main())