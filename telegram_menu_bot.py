#!/usr/bin/env python3
"""
BetBog Telegram Bot с интерактивным меню
Полнофункциональный бот для мониторинга спортивных ставок
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from config import Config
from logger import BetBogLogger
from database import get_session
from models import Signal, Match, StrategyConfig
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload


class BetBogTelegramBot:
    """Продвинутый Telegram бот для BetBog с интерактивным меню"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("BOT", config.LOG_FILE)
        self.application = None
        self.authorized_users = {123456789}  # Добавьте свой Telegram ID
        
    async def initialize(self):
        """Инициализация Telegram бота"""
        try:
            self.application = Application.builder().token(self.config.BOT_TOKEN).build()
            
            # Регистрация команд
            commands = [
                ("start", "🚀 Запуск бота"),
                ("menu", "📋 Главное меню"),
                ("signals", "🎯 Активные сигналы"),
                ("stats", "📊 Статистика"),
                ("matches", "⚽ Live матчи"),
                ("settings", "⚙️ Настройки"),
                ("help", "❓ Помощь")
            ]
            
            # Установка команд для меню
            bot_commands = [BotCommand(cmd, desc) for cmd, desc in commands]
            await self.application.bot.set_my_commands(bot_commands)
            
            # Регистрация обработчиков
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("menu", self.menu_command))
            self.application.add_handler(CommandHandler("signals", self.signals_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("matches", self.matches_command))
            self.application.add_handler(CommandHandler("settings", self.settings_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            self.logger.success("Telegram бот инициализирован")
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации бота: {str(e)}")
            raise

    def _is_authorized(self, user_id: int) -> bool:
        """Проверка авторизации пользователя"""
        return user_id in self.authorized_users

    def _get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Создание главного меню с кнопками"""
        keyboard = [
            [
                InlineKeyboardButton("🎯 Активные сигналы", callback_data="signals"),
                InlineKeyboardButton("📊 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton("⚽ Live матчи", callback_data="matches"),
                InlineKeyboardButton("💰 P&L отчет", callback_data="pnl")
            ],
            [
                InlineKeyboardButton("🔧 Стратегии", callback_data="strategies"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
            ],
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_main"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _get_signals_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура для раздела сигналов"""
        keyboard = [
            [
                InlineKeyboardButton("🔴 Активные", callback_data="signals_active"),
                InlineKeyboardButton("✅ Выигрышные", callback_data="signals_won")
            ],
            [
                InlineKeyboardButton("❌ Проигрышные", callback_data="signals_lost"),
                InlineKeyboardButton("⏳ Ожидание", callback_data="signals_pending")
            ],
            [
                InlineKeyboardButton("📈 Топ стратегии", callback_data="signals_top"),
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_signals")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _get_stats_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура для статистики"""
        keyboard = [
            [
                InlineKeyboardButton("📅 Сегодня", callback_data="stats_today"),
                InlineKeyboardButton("📅 Эта неделя", callback_data="stats_week")
            ],
            [
                InlineKeyboardButton("📅 Этот месяц", callback_data="stats_month"),
                InlineKeyboardButton("📊 Общая", callback_data="stats_all")
            ],
            [
                InlineKeyboardButton("💎 По стратегиям", callback_data="stats_strategies"),
                InlineKeyboardButton("🎯 По типам", callback_data="stats_types")
            ],
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен. Обратитесь к администратору.")
            return

        welcome_text = """
🤖 <b>BetBog Monitoring Bot</b>

Добро пожаловать в систему мониторинга спортивных ставок!

<b>Возможности:</b>
🎯 Анализ live матчей в реальном времени
📊 Расчет продвинутых метрик (dxG, градиент, momentum)
💰 Отслеживание P&L по сигналам
🔧 Адаптивные стратегии ставок
📈 Детальная статистика и отчеты

<b>Система активна и анализирует:</b>
• Live футбольные матчи
• 7 стратегий ставок
• Реальные данные от bet365 API

Используйте меню ниже для навигации:
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_main_menu_keyboard()
        )

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        await update.message.reply_text(
            "📋 <b>Главное меню BetBog</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_main_menu_keyboard()
        )

    async def signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать сигналы"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        await self._show_signals_menu(update, context)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        await self._show_stats_menu(update, context)

    async def matches_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать live матчи"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        await self._show_live_matches(update, context)

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать настройки"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        await self._show_settings(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать помощь"""
        help_text = """
❓ <b>Помощь BetBog Bot</b>

<b>Основные команды:</b>
/start - Запуск бота и главное меню
/menu - Показать главное меню
/signals - Активные сигналы
/stats - Статистика и отчеты
/matches - Live матчи
/settings - Настройки

<b>Функции:</b>
🎯 <b>Сигналы</b> - анализ betting сигналов
📊 <b>Статистика</b> - P&L, winrate, ROI
⚽ <b>Матчи</b> - live данные и метрики
🔧 <b>Стратегии</b> - настройка алгоритмов

<b>Метрики системы:</b>
• dxG - derived Expected Goals
• Gradient - тренд производительности
• Wave - амплитуда интенсивности
• Momentum - импульс команд
• Tiredness - фактор усталости

<b>Стратегии:</b>
• DxG Hunter - поиск высокого xG
• Momentum Rider - игра на импульсе
• Wave Catcher - анализ волн
• Late Drama - поздние голы
• Comeback King - камбэки
• Defensive Wall - оборонительная игра
• Quick Strike - быстрые голы

Система работает 24/7 и анализирует реальные данные!
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if not self._is_authorized(user_id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        data = query.data

        # Главное меню
        if data == "main_menu":
            await self._show_main_menu(query)
        
        # Сигналы
        elif data == "signals":
            await self._show_signals_menu_callback(query)
        elif data.startswith("signals_"):
            await self._handle_signals_callback(query, data)
        
        # Статистика
        elif data == "stats":
            await self._show_stats_menu_callback(query)
        elif data.startswith("stats_"):
            await self._handle_stats_callback(query, data)
        
        # Матчи
        elif data == "matches":
            await self._show_live_matches_callback(query)
        
        # P&L
        elif data == "pnl":
            await self._show_pnl_report(query)
        
        # Стратегии
        elif data == "strategies":
            await self._show_strategies(query)
        
        # Настройки
        elif data == "settings":
            await self._show_settings_callback(query)
        
        # Помощь
        elif data == "help":
            await self._show_help_callback(query)
        
        # Обновления
        elif data.startswith("refresh_"):
            await self._handle_refresh(query, data)

    async def _show_main_menu(self, query):
        """Показать главное меню"""
        text = """
📋 <b>BetBog Monitoring Dashboard</b>

🟢 <b>Система активна</b>
📊 Анализ live матчей
💎 7 стратегий работают
🎯 Поиск сигналов

Выберите раздел:
        """
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_main_menu_keyboard()
        )

    async def _show_signals_menu_callback(self, query):
        """Показать меню сигналов через callback"""
        async with get_session() as session:
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

        text = f"""
🎯 <b>Сигналы BetBog</b>

📊 <b>Общая статистика:</b>
• Всего сигналов: {total_signals or 0}
• Активных: {active_signals or 0}
• Выиграно: {won_signals or 0}
• Проиграно: {lost_signals or 0}

Выберите категорию:
        """
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_signals_keyboard()
        )

    async def _show_signals_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню сигналов"""
        async with get_session() as session:
            total_signals = await session.scalar(select(func.count(Signal.id)))
            active_signals = await session.scalar(
                select(func.count(Signal.id)).where(Signal.result == "pending")
            )

        text = f"""
🎯 <b>Сигналы BetBog</b>

📊 Всего сигналов: {total_signals or 0}
🔴 Активных: {active_signals or 0}

Выберите категорию:
        """
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_signals_keyboard()
        )

    async def _show_stats_menu_callback(self, query):
        """Показать меню статистики через callback"""
        text = """
📊 <b>Статистика BetBog</b>

Выберите период для анализа:
        """
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_stats_keyboard()
        )

    async def _show_stats_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню статистики"""
        text = """
📊 <b>Статистика BetBog</b>

Выберите период для анализа:
        """
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self._get_stats_keyboard()
        )

    async def _show_live_matches(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать live матчи"""
        async with get_session() as session:
            # Получаем последние матчи
            stmt = select(Match).order_by(desc(Match.updated_at)).limit(10)
            matches = await session.scalars(stmt)
            matches_list = list(matches)

        if not matches_list:
            text = "⚽ <b>Live матчи</b>\n\n❌ Нет активных матчей"
        else:
            text = "⚽ <b>Live матчи</b>\n\n"
            for match in matches_list[:5]:
                status = "🔴 LIVE" if match.status == "live" else "⚪ Завершен"
                text += f"{status} <b>{match.home_team}</b> vs <b>{match.away_team}</b>\n"
                text += f"📊 {match.home_score}:{match.away_score} | {match.minute}'\n"
                text += f"🏆 {match.league}\n\n"

        keyboard = [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_matches"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_live_matches_callback(self, query):
        """Показать live матчи через callback"""
        async with get_session() as session:
            stmt = select(Match).order_by(desc(Match.updated_at)).limit(10)
            matches = await session.scalars(stmt)
            matches_list = list(matches)

        if not matches_list:
            text = "⚽ <b>Live матчи</b>\n\n❌ Нет активных матчей"
        else:
            text = "⚽ <b>Live матчи</b>\n\n"
            for match in matches_list[:5]:
                status = "🔴 LIVE" if match.status == "live" else "⚪ Завершен"
                text += f"{status} <b>{match.home_team}</b> vs <b>{match.away_team}</b>\n"
                text += f"📊 {match.home_score}:{match.away_score} | {match.minute}'\n"
                text += f"🏆 {match.league}\n\n"

        keyboard = [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_matches"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать настройки"""
        text = """
⚙️ <b>Настройки BetBog</b>

🔧 <b>Текущие настройки:</b>
• API: bet365 ✅
• База данных: PostgreSQL ✅
• Мониторинг: Активен ✅
• Стратегии: 7 активных ✅

📋 <b>Доступные функции:</b>
• Уведомления о сигналах
• P&L алерты
• Настройка стратегий
• Экспорт данных
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications"),
                InlineKeyboardButton("🎯 Стратегии", callback_data="settings_strategies")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_settings_callback(self, query):
        """Показать настройки через callback"""
        text = """
⚙️ <b>Настройки BetBog</b>

🔧 <b>Текущие настройки:</b>
• API: bet365 ✅
• База данных: PostgreSQL ✅
• Мониторинг: Активен ✅
• Стратегии: 7 активных ✅

📋 <b>Доступные функции:</b>
• Уведомления о сигналах
• P&L алерты
• Настройка стратегий
• Экспорт данных
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications"),
                InlineKeyboardButton("🎯 Стратегии", callback_data="settings_strategies")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_help_callback(self, query):
        """Показать помощь через callback"""
        help_text = """
❓ <b>Помощь BetBog Bot</b>

<b>Основные функции:</b>
🎯 <b>Сигналы</b> - betting сигналы в реальном времени
📊 <b>Статистика</b> - P&L, winrate, ROI анализ
⚽ <b>Матчи</b> - live данные и продвинутые метрики
🔧 <b>Стратегии</b> - адаптивные алгоритмы

<b>Метрики:</b>
• dxG - derived Expected Goals
• Gradient - тренд производительности
• Momentum - импульс команд
• Wave - амплитуда интенсивности

Система анализирует реальные данные 24/7!
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]
        
        await query.edit_message_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_signals_callback(self, query, data):
        """Обработка callbacks для сигналов"""
        if data == "signals_active":
            await self._show_active_signals(query)
        elif data == "signals_won":
            await self._show_won_signals(query)
        elif data == "signals_lost":
            await self._show_lost_signals(query)
        elif data == "signals_pending":
            await self._show_pending_signals(query)
        elif data == "refresh_signals":
            await self._show_signals_menu_callback(query)

    async def _show_active_signals(self, query):
        """Показать активные сигналы"""
        async with get_session() as session:
            stmt = (
                select(Signal)
                .where(Signal.result == "pending")
                .options(selectinload(Signal.match))
                .order_by(desc(Signal.created_at))
                .limit(5)
            )
            signals = await session.scalars(stmt)
            signals_list = list(signals)

        if not signals_list:
            text = "🎯 <b>Активные сигналы</b>\n\n❌ Нет активных сигналов"
        else:
            text = "🎯 <b>Активные сигналы</b>\n\n"
            for signal in signals_list:
                match = signal.match
                confidence_emoji = "🔥" if signal.confidence > 0.8 else "⚡" if signal.confidence > 0.6 else "📈"
                text += f"{confidence_emoji} <b>{signal.strategy_name}</b>\n"
                text += f"⚽ {match.home_team} vs {match.away_team}\n"
                text += f"🎯 {signal.signal_type} | {signal.confidence:.1%}\n"
                text += f"💰 Размер: {signal.bet_size:.2f}\n\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_signals")],
            [InlineKeyboardButton("🔙 Назад", callback_data="signals")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_won_signals(self, query):
        """Показать выигрышные сигналы"""
        async with get_session() as session:
            stmt = (
                select(Signal)
                .where(Signal.result == "won")
                .options(selectinload(Signal.match))
                .order_by(desc(Signal.created_at))
                .limit(5)
            )
            signals = await session.scalars(stmt)
            signals_list = list(signals)

        if not signals_list:
            text = "✅ <b>Выигрышные сигналы</b>\n\n❌ Нет выигрышных сигналов"
        else:
            text = "✅ <b>Выигрышные сигналы</b>\n\n"
            total_profit = 0
            for signal in signals_list:
                match = signal.match
                profit = signal.profit_loss or 0
                total_profit += profit
                text += f"✅ <b>{signal.strategy_name}</b>\n"
                text += f"⚽ {match.home_team} vs {match.away_team}\n"
                text += f"🎯 {signal.signal_type} | {signal.confidence:.1%}\n"
                text += f"💰 Прибыль: +{profit:.2f}\n\n"
            
            text += f"💎 <b>Общая прибыль: +{total_profit:.2f}</b>"

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_signals")],
            [InlineKeyboardButton("🔙 Назад", callback_data="signals")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_lost_signals(self, query):
        """Показать проигрышные сигналы"""
        async with get_session() as session:
            stmt = (
                select(Signal)
                .where(Signal.result == "lost")
                .options(selectinload(Signal.match))
                .order_by(desc(Signal.created_at))
                .limit(5)
            )
            signals = await session.scalars(stmt)
            signals_list = list(signals)

        if not signals_list:
            text = "❌ <b>Проигрышные сигналы</b>\n\n❌ Нет проигрышных сигналов"
        else:
            text = "❌ <b>Проигрышные сигналы</b>\n\n"
            total_loss = 0
            for signal in signals_list:
                match = signal.match
                loss = signal.profit_loss or 0
                total_loss += loss
                text += f"❌ <b>{signal.strategy_name}</b>\n"
                text += f"⚽ {match.home_team} vs {match.away_team}\n"
                text += f"🎯 {signal.signal_type} | {signal.confidence:.1%}\n"
                text += f"💸 Убыток: {loss:.2f}\n\n"
            
            text += f"📉 <b>Общий убыток: {total_loss:.2f}</b>"

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_signals")],
            [InlineKeyboardButton("🔙 Назад", callback_data="signals")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_pending_signals(self, query):
        """Показать ожидающие сигналы"""
        await self._show_active_signals(query)  # То же самое что и активные

    async def _handle_stats_callback(self, query, data):
        """Обработка callbacks для статистики"""
        period = data.replace("stats_", "")
        await self._show_stats_for_period(query, period)

    async def _show_stats_for_period(self, query, period):
        """Показать статистику за период"""
        async with get_session() as session:
            # Базовая статистика
            total_signals = await session.scalar(select(func.count(Signal.id)))
            won_signals = await session.scalar(
                select(func.count(Signal.id)).where(Signal.result == "won")
            )
            lost_signals = await session.scalar(
                select(func.count(Signal.id)).where(Signal.result == "lost")
            )
            
            # Расчет винрейта
            completed_signals = (won_signals or 0) + (lost_signals or 0)
            winrate = (won_signals / completed_signals * 100) if completed_signals > 0 else 0
            
            # Прибыль/убыток
            total_pnl_result = await session.scalar(
                select(func.sum(Signal.profit_loss)).where(Signal.profit_loss.isnot(None))
            )
            total_pnl = total_pnl_result or 0

        period_names = {
            "today": "Сегодня",
            "week": "Эта неделя", 
            "month": "Этот месяц",
            "all": "За все время"
        }
        
        period_name = period_names.get(period, "За период")
        
        text = f"""
📊 <b>Статистика - {period_name}</b>

📈 <b>Общие показатели:</b>
• Всего сигналов: {total_signals or 0}
• Выиграно: {won_signals or 0}
• Проиграно: {lost_signals or 0}
• Винрейт: {winrate:.1f}%

💰 <b>P&L:</b>
• Общий P&L: {total_pnl:+.2f}
• ROI: {(total_pnl / max(completed_signals, 1) * 100):+.1f}%

🎯 <b>Производительность:</b>
• Средний сигнал: {(total_pnl / max(completed_signals, 1)):.2f}
• Активность: {(total_signals or 0) / max(1, 7):.1f} сигналов/день
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📅 Другой период", callback_data="stats"),
                InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_stats")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_pnl_report(self, query):
        """Показать P&L отчет"""
        async with get_session() as session:
            # Статистика по стратегиям
            stmt = (
                select(Signal.strategy_name, 
                       func.count(Signal.id).label('total'),
                       func.sum(Signal.profit_loss).label('pnl'))
                .where(Signal.profit_loss.isnot(None))
                .group_by(Signal.strategy_name)
                .order_by(func.sum(Signal.profit_loss).desc())
            )
            
            strategy_stats = await session.execute(stmt)
            results = strategy_stats.fetchall()

        text = "💰 <b>P&L Отчет по стратегиям</b>\n\n"
        
        if not results:
            text += "❌ Нет данных для отображения"
        else:
            total_pnl = 0
            for row in results:
                strategy, total, pnl = row
                total_pnl += pnl or 0
                pnl_emoji = "💚" if (pnl or 0) > 0 else "❤️" if (pnl or 0) < 0 else "💛"
                text += f"{pnl_emoji} <b>{strategy}</b>\n"
                text += f"📊 Сигналов: {total} | P&L: {pnl or 0:+.2f}\n\n"
            
            text += f"💎 <b>Общий P&L: {total_pnl:+.2f}</b>"

        keyboard = [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_pnl"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_strategies(self, query):
        """Показать стратегии"""
        async with get_session() as session:
            stmt = select(StrategyConfig).order_by(StrategyConfig.name)
            strategies = await session.scalars(stmt)
            strategies_list = list(strategies)

        text = "🔧 <b>Активные стратегии BetBog</b>\n\n"
        
        if not strategies_list:
            text += "❌ Нет настроенных стратегий"
        else:
            for strategy in strategies_list:
                status_emoji = "🟢" if strategy.enabled else "🔴"
                text += f"{status_emoji} <b>{strategy.name}</b>\n"
                text += f"📊 Enabled: {'Да' if strategy.enabled else 'Нет'}\n"
                if strategy.thresholds:
                    text += f"🎯 Настройки: {len(strategy.thresholds)} параметров\n"
                text += "\n"

        keyboard = [
            [
                InlineKeyboardButton("⚙️ Настроить", callback_data="config_strategies"),
                InlineKeyboardButton("🔄 Обновить", callback_data="refresh_strategies")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_refresh(self, query, data):
        """Обработка обновлений"""
        refresh_type = data.replace("refresh_", "")
        
        if refresh_type == "main":
            await self._show_main_menu(query)
        elif refresh_type == "signals":
            await self._show_signals_menu_callback(query)
        elif refresh_type == "stats":
            await self._show_stats_menu_callback(query)
        elif refresh_type == "matches":
            await self._show_live_matches_callback(query)
        elif refresh_type == "pnl":
            await self._show_pnl_report(query)
        elif refresh_type == "strategies":
            await self._show_strategies(query)

    async def send_signal_notification(self, signal_data: Dict[str, Any], match_data: Dict[str, Any]):
        """Отправить уведомление о новом сигнале"""
        try:
            confidence_emoji = "🔥" if signal_data.get('confidence', 0) > 0.8 else "⚡"
            
            text = f"""
🎯 <b>НОВЫЙ СИГНАЛ!</b>

{confidence_emoji} <b>{signal_data.get('strategy_name', 'Unknown')}</b>
⚽ <b>{match_data.get('home_team', 'Unknown')} vs {match_data.get('away_team', 'Unknown')}</b>

🎯 Тип: {signal_data.get('signal_type', 'Unknown')}
📊 Уверенность: {signal_data.get('confidence', 0):.1%}
💰 Размер ставки: {signal_data.get('bet_size', 0):.2f}
⏰ Время: {datetime.now().strftime('%H:%M:%S')}

📈 Ключевые метрики:
• dxG: {signal_data.get('details', {}).get('dxg_home', 0):.2f} - {signal_data.get('details', {}).get('dxg_away', 0):.2f}
• Momentum: {signal_data.get('details', {}).get('momentum', 0):.2f}
            """
            
            keyboard = [
                [InlineKeyboardButton("📊 Подробнее", callback_data="signals_active")],
                [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
            ]
            
            # Отправляем всем авторизованным пользователям
            for user_id in self.authorized_users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {str(e)}")
                    
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления о сигнале: {str(e)}")

    async def start_polling(self):
        """Запуск бота в режиме polling"""
        try:
            await self.application.initialize()
            await self.application.start()
            
            self.logger.success("🤖 Telegram бот запущен и готов к работе!")
            self.logger.info("Бот будет работать в фоновом режиме...")
            
            # Запускаем polling в фоновом режиме
            await self.application.updater.start_polling()
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска бота: {str(e)}")
            raise

    async def stop_polling(self):
        """Остановка бота"""
        try:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self.logger.info("Telegram бот остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка остановки бота: {str(e)}")


# Функция для интеграции с основной системой
async def create_telegram_bot(config: Config) -> BetBogTelegramBot:
    """Создать и инициализировать Telegram бота"""
    bot = BetBogTelegramBot(config)
    await bot.initialize()
    return bot


if __name__ == "__main__":
    # Для тестирования
    async def main():
        config = Config()
        bot = await create_telegram_bot(config)
        await bot.start_polling()
        
        try:
            # Держим бота активным
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await bot.stop_polling()

    asyncio.run(main())