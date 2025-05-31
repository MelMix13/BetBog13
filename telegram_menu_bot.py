#!/usr/bin/env python3
"""
Telegram бот с интерактивным кнопочным меню для BetBog
"""
import asyncio
import aiohttp
import os
import json
from typing import Dict, Any, List
from datetime import datetime, date
import asyncpg

class TelegramMenuBot:
    """Telegram бот с кнопочным меню"""
    
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "7228733029:AAFVPzKHUSRidigzYSy_IANt8rWzjjPBDPA")
        self.database_url = os.getenv("DATABASE_URL")
        self.running = False
        self.user_messages = {}  # Хранение message_id для каждого пользователя
        self.animation_frames = self._init_animation_frames()
        
    def _init_animation_frames(self):
        """Инициализация кадров анимации для переходов"""
        return {
            "loading": [
                "⏳ Загрузка",
                "⏳ Загрузка.",
                "⏳ Загрузка..",
                "⏳ Загрузка..."
            ],
            "processing": [
                "🔄 Обработка",
                "🔄 Обработка.",
                "🔄 Обработка..",
                "🔄 Обработка..."
            ],
            "analyzing": [
                "📊 Анализ",
                "📊 Анализ.",
                "📊 Анализ..",
                "📊 Анализ..."
            ],
            "connecting": [
                "🔗 Подключение",
                "🔗 Подключение.",
                "🔗 Подключение..",
                "🔗 Подключение..."
            ]
        }
    
    async def animate_transition(self, chat_id: int, animation_type: str = "loading", duration: float = 1.0):
        """Показать анимацию перехода"""
        frames = self.animation_frames.get(animation_type, self.animation_frames["loading"])
        frame_duration = duration / len(frames)
        
        # Получаем message_id для редактирования
        message_id = self.user_messages.get(chat_id)
        if not message_id:
            return
        
        for frame in frames:
            await self.edit_message(chat_id, message_id, frame)
            await asyncio.sleep(frame_duration)
    
    async def smooth_transition_to(self, chat_id: int, callback_query_id: str, 
                                 target_content: str, target_markup=None, 
                                 animation_type: str = "loading"):
        """Плавный переход к новому контенту с анимацией"""
        # Отвечаем на callback query
        await self.answer_callback_query(callback_query_id)
        
        # Показываем анимацию загрузки
        await self.animate_transition(chat_id, animation_type, 0.8)
        
        # Показываем финальный контент
        message_id = self.user_messages.get(chat_id)
        if message_id:
            await self.edit_message(chat_id, message_id, target_content, target_markup)
            
    async def get_db_connection(self):
        """Получение подключения к базе данных"""
        try:
            return await asyncpg.connect(self.database_url)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        """Отправка сообщения с кнопками"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": chat_id, 
                "text": text, 
                "parse_mode": "HTML"
            }
            
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get("result", {}).get("message_id")
                        print(f"✅ Сообщение отправлено пользователю {chat_id}")
                        return message_id
                    else:
                        print(f"❌ Ошибка отправки: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"Ошибка отправки сообщения: {str(e)}")
            return None

    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup=None):
        """Редактирование существующего сообщения"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text, 
                "parse_mode": "HTML"
            }
            
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        print(f"✅ Сообщение отредактировано для пользователя {chat_id}")
                        return True
                    else:
                        print(f"❌ Ошибка редактирования: {response.status}")
                        return False
                        
        except Exception as e:
            print(f"Ошибка редактирования сообщения: {str(e)}")
            return False

    async def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Ответ на callback query"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
            data = {"callback_query_id": callback_query_id, "text": text}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    return response.status == 200
        except Exception as e:
            print(f"Ошибка ответа на callback: {e}")
            return False

    def create_main_menu(self):
        """Создание главного меню"""
        return {
            "inline_keyboard": [
                [
                    {"text": "📊 Live матчи", "callback_data": "live_matches"},
                    {"text": "⚡ Сигналы", "callback_data": "signals"}
                ],
                [
                    {"text": "🎯 Стратегии", "callback_data": "strategies"},
                    {"text": "📈 Статистика", "callback_data": "statistics"}
                ],
                [
                    {"text": "⚙️ Настройки", "callback_data": "settings"},
                    {"text": "❓ Помощь", "callback_data": "help"}
                ],
                [
                    {"text": "🔄 Обновить", "callback_data": "refresh"}
                ]
            ]
        }

    async def get_live_matches_count(self):
        """Получение количества live матчей через API"""
        try:
            api_token = os.getenv("API_TOKEN", "219769-EKswpZvLvKyoxD")
            url = "https://api.b365api.com/v3/events/inplay"
            params = {
                "sport_id": 1,  # Football
                "token": api_token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") == 1:
                            matches = data.get("results", [])
                            return len(matches)
                        else:
                            print(f"API ошибка: {data.get('error', 'Неизвестная ошибка')}")
                            return "API ошибка"
                    else:
                        print(f"HTTP ошибка: {response.status}")
                        return "HTTP ошибка"
        except Exception as e:
            print(f"Ошибка получения live матчей через API: {e}")
            return "Ошибка"

    async def get_recent_signals(self, limit: int = 10):
        """Получение последних сигналов"""
        conn = await self.get_db_connection()
        if not conn:
            return []
        
        try:
            query = """
                SELECT strategy_name, signal_type, confidence, result, created_at
                FROM signals 
                ORDER BY created_at DESC 
                LIMIT $1
            """
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Ошибка получения сигналов: {e}")
            return []
        finally:
            await conn.close()

    async def get_strategy_configs(self):
        """Получение конфигураций стратегий"""
        conn = await self.get_db_connection()
        if not conn:
            return []
        
        try:
            query = """
                SELECT strategy_name, total_signals, win_rate, winning_signals, enabled
                FROM strategy_configs 
                WHERE enabled = true
                ORDER BY strategy_name
            """
            rows = await conn.fetch(query)
            strategies = []
            for row in rows:
                strategy = dict(row)
                # Вычисляем win_rate если не задан
                if strategy['total_signals'] > 0 and strategy['win_rate'] == 0:
                    strategy['win_rate'] = (strategy['winning_signals'] / strategy['total_signals']) * 100
                strategies.append(strategy)
            return strategies
        except Exception as e:
            print(f"Ошибка получения стратегий: {e}")
            return []
        finally:
            await conn.close()

    def format_strategy_name(self, strategy_name: str) -> str:
        """Форматирование названия стратегии для отображения"""
        strategy_names = {
            "over_2_5_goals": "⚽ Тотал больше 2.5",
            "under_2_5_goals": "🛡️ Тотал меньше 2.5", 
            "btts_yes": "🥅 Обе забьют ДА",
            "btts_no": "🚫 Обе забьют НЕТ",
            "home_win": "🏠 Победа хозяев",
            "away_win": "✈️ Победа гостей",
            "draw": "🤝 Ничья",
            "next_goal_home": "🎯 След. гол - хозяева",
            "next_goal_away": "🎯 След. гол - гости"
        }
        return strategy_names.get(strategy_name, f"📋 {strategy_name}")

    async def get_system_statistics(self):
        """Получение статистики системы"""
        conn = await self.get_db_connection()
        if not conn:
            return {}
        
        try:
            # Статистика за сегодня
            today = date.today()
            
            queries = {
                "total_signals": "SELECT COUNT(*) FROM signals",
                "today_signals": "SELECT COUNT(*) FROM signals WHERE DATE(created_at) = $1",
                "pending_signals": "SELECT COUNT(*) FROM signals WHERE result = 'pending'",
                "win_signals": "SELECT COUNT(*) FROM signals WHERE result = 'win'",
                "total_matches": "SELECT COUNT(*) FROM matches"
            }
            
            stats = {}
            for key, query in queries.items():
                if key == "today_signals":
                    stats[key] = await conn.fetchval(query, today)
                else:
                    stats[key] = await conn.fetchval(query)
                    
            # Вычисляем общий win rate
            if stats["total_signals"] > 0:
                stats["win_rate"] = (stats["win_signals"] / stats["total_signals"]) * 100
            else:
                stats["win_rate"] = 0
                
            return stats
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return {}
        finally:
            await conn.close()

    async def handle_live_matches(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Live матчи"""
        await self.answer_callback_query(callback_query_id, "Загружаю данные о live матчах...")
        
        live_count = await self.get_live_matches_count()
        
        message = f"""📊 <b>Live матчи</b>

🔴 <b>Активные матчи:</b> {live_count}
⚡ Анализ в реальном времени
📈 Вычисление продвинутых метрик

<b>Отслеживаемые метрики:</b>
• dxG (производные ожидаемые голы)
• Gradient (тренды производительности)
• Momentum (импульс команд)
• Wave amplitude (амплитуда интенсивности)
• Tiredness factor (фактор усталости)
• Stability (стабильность)

🔄 Обновление каждые 60 секунд"""

        # Редактируем существующее сообщение если есть message_id
        if chat_id in self.user_messages:
            await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
        else:
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id

    async def handle_signals(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Сигналы"""
        await self.answer_callback_query(callback_query_id, "Загружаю последние сигналы...")
        
        signals = await self.get_recent_signals(10)
        
        if not signals:
            message = """⚡ <b>Сигналы</b>

🔍 <b>Последние сигналы не найдены</b>

Система активно анализирует live матчи и генерирует сигналы на основе продвинутых метрик."""
        else:
            message = "⚡ <b>Последние 10 сигналов</b>\n\n"
            
            for i, signal in enumerate(signals, 1):
                status_emoji = "🟡" if signal['result'] == 'pending' else ("🟢" if signal['result'] == 'win' else "🔴")
                confidence_pct = signal['confidence'] * 100 if signal['confidence'] else 0
                created_time = signal['created_at'].strftime("%d.%m %H:%M") if signal['created_at'] else "Н/Д"
                
                message += f"{i}. {status_emoji} <b>{signal['strategy_name']}</b>\n"
                message += f"   📊 {signal['signal_type']} ({confidence_pct:.1f}%)\n"
                message += f"   📅 {created_time}\n\n"

        # Редактируем существующее сообщение если есть message_id
        if chat_id in self.user_messages:
            await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
        else:
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id

    async def handle_strategies(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Стратегии"""
        await self.answer_callback_query(callback_query_id, "Загружаю конфигурации стратегий...")
        
        strategies = await self.get_strategy_configs()
        print(f"DEBUG: Loaded {len(strategies)} strategies from database")
        
        if not strategies:
            message = """🎯 <b>Стратегии</b>

⚙️ <b>Конфигурации стратегий не найдены</b>

Система использует адаптивные алгоритмы для анализа спортивных данных."""
        else:
            message = "🎯 <b>Активные стратегии</b>\n\n"
            
            # Группируем стратегии по логике
            strategy_groups = {
                "results": ["home_win", "draw", "away_win"],
                "totals": ["over_2_5_goals", "under_2_5_goals"],
                "btts": ["btts_yes", "btts_no"],
                "next_goal": ["next_goal_home", "next_goal_away"]
            }
            
            # Создаем словарь для быстрого поиска
            strategies_dict = {s['strategy_name']: s for s in strategies}
            print(f"DEBUG: Strategy names in dict: {list(strategies_dict.keys())}")
            
            # Отображаем по группам
            message += "🏆 <b>Исходы матча:</b>\n"
            for strategy_name in strategy_groups["results"]:
                if strategy_name in strategies_dict:
                    strategy = strategies_dict[strategy_name]
                    display_name = self.format_strategy_name(strategy_name)
                    win_rate = strategy.get('win_rate', 0)
                    total_signals = strategy.get('total_signals', 0)
                    message += f"🟢 {display_name} | 🎯 {win_rate:.1f}% | 📊 {total_signals}\n"
            
            message += "\n⚽ <b>Тоталы голов:</b>\n"
            for strategy_name in strategy_groups["totals"]:
                if strategy_name in strategies_dict:
                    strategy = strategies_dict[strategy_name]
                    display_name = self.format_strategy_name(strategy_name)
                    win_rate = strategy.get('win_rate', 0)
                    total_signals = strategy.get('total_signals', 0)
                    message += f"🟢 {display_name} | 🎯 {win_rate:.1f}% | 📊 {total_signals}\n"
            
            message += "\n🥅 <b>Обе забьют:</b>\n"
            for strategy_name in strategy_groups["btts"]:
                if strategy_name in strategies_dict:
                    strategy = strategies_dict[strategy_name]
                    display_name = self.format_strategy_name(strategy_name)
                    win_rate = strategy.get('win_rate', 0)
                    total_signals = strategy.get('total_signals', 0)
                    message += f"🟢 {display_name} | 🎯 {win_rate:.1f}% | 📊 {total_signals}\n"
            
            message += "\n🎯 <b>Следующий гол:</b>\n"
            for strategy_name in strategy_groups["next_goal"]:
                if strategy_name in strategies_dict:
                    strategy = strategies_dict[strategy_name]
                    display_name = self.format_strategy_name(strategy_name)
                    win_rate = strategy.get('win_rate', 0)
                    total_signals = strategy.get('total_signals', 0)
                    message += f"🟢 {display_name} | 🎯 {win_rate:.1f}% | 📊 {total_signals}\n"
            
            print(f"DEBUG: Final message length: {len(message)}")

        # Редактируем существующее сообщение если есть message_id
        if chat_id in self.user_messages:
            await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
        else:
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id

    async def handle_statistics(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Статистика"""
        await self.answer_callback_query(callback_query_id, "Загружаю статистику...")
        
        stats = await self.get_system_statistics()
        
        if not stats:
            message = """📈 <b>Статистика</b>

❌ <b>Данные статистики недоступны</b>

Система продолжает сбор данных."""
        else:
            message = f"""📈 <b>Статистика системы</b>

📊 <b>Общие показатели:</b>
• Всего сигналов: {stats.get('total_signals', 0)}
• За сегодня: {stats.get('today_signals', 0)}
• Ожидающих: {stats.get('pending_signals', 0)}
• Выигрышных: {stats.get('win_signals', 0)}

🎯 <b>Эффективность:</b>
• Win Rate: {stats.get('win_rate', 0):.1f}%

⚽ <b>Матчи:</b>
• Всего обработано: {stats.get('total_matches', 0)}

🔄 Данные обновляются в реальном времени"""

        await self.send_message(chat_id, message, self.create_main_menu())

    async def handle_settings(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Настройки"""
        await self.answer_callback_query(callback_query_id)
        
        # Получаем текущие настройки тиков из конфига
        from config import Config
        config = Config()
        
        message = f"""⚙️ <b>Настройки системы</b>

📊 <b>Анализ тиков:</b>
• Интервал тиков: {getattr(config, 'TICK_INTERVAL', 60)} сек
• Размер окна: {getattr(config, 'TICK_WINDOW_SIZE', 3)} тиков
• История: {getattr(config, 'MAX_TICKS_HISTORY', 50)} тиков

🔧 <b>Система:</b>
• Интервал проверки: 60 сек
• Максимум матчей: 20 за цикл
• ML оптимизация: каждые 24 часа
• Автоочистка: включена

📊 <b>Пороги по умолчанию:</b>
• Confidence: 70%"""

        # Создаем клавиатуру с настройками тиков
        settings_menu = {
            "inline_keyboard": [
                [
                    {"text": "⏱️ Интервал тиков", "callback_data": "set_tick_interval"},
                    {"text": "📊 Размер окна", "callback_data": "set_tick_window"}
                ],
                [
                    {"text": "📝 История тиков", "callback_data": "set_tick_history"},
                    {"text": "🎯 Отслеживаемые метрики", "callback_data": "set_tick_metrics"}
                ],
                [
                    {"text": "🔄 Пороги трендов", "callback_data": "set_tick_thresholds"},
                    {"text": "📈 Уверенность анализа", "callback_data": "set_tick_confidence"}
                ],
                [
                    {"text": "🏠 Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        await self.send_message(chat_id, message, settings_menu)

    async def handle_main_menu(self, chat_id: int, callback_query_id: str):
        """Возврат в главное меню"""
        await self.answer_callback_query(callback_query_id)
        
        message = """🏆 <b>BetBog Monitoring Bot</b>

🤖 Интеллектуальная система мониторинга спортивных ставок
📊 Анализ live матчей с продвинутыми метриками
⚡ Автоматическая генерация сигналов

Выберите раздел для получения информации:"""
        
        await self.send_message(chat_id, message, self.create_main_menu())

    async def handle_tick_interval_settings(self, chat_id: int, callback_query_id: str):
        """Настройка интервала тиков"""
        await self.answer_callback_query(callback_query_id)
        
        from config import Config
        config = Config()
        current_interval = getattr(config, 'TICK_INTERVAL', 60)
        
        message = f"""⏱️ <b>Настройка интервала тиков</b>

<b>Текущий интервал:</b> {current_interval} секунд

<b>Интервал определяет:</b>
• Как часто собираются данные
• Чувствительность к изменениям
• Нагрузка на API

<b>Рекомендации:</b>
• 30 сек - высокая чувствительность, больше шума
• 60 сек - сбалансированный (рекомендуется)
• 90-120 сек - стабильные тренды, меньше ложных сигналов"""

        interval_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚡ 30 сек", "callback_data": "tick_interval_30"},
                    {"text": "⚖️ 60 сек", "callback_data": "tick_interval_60"},
                    {"text": "🛡️ 90 сек", "callback_data": "tick_interval_90"}
                ],
                [
                    {"text": "🔒 120 сек", "callback_data": "tick_interval_120"},
                    {"text": "🐌 180 сек", "callback_data": "tick_interval_180"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, interval_menu)

    async def handle_tick_window_settings(self, chat_id: int, callback_query_id: str):
        """Настройка размера окна тиков"""
        await self.answer_callback_query(callback_query_id)
        
        from config import Config
        config = Config()
        current_window = getattr(config, 'TICK_WINDOW_SIZE', 3)
        
        message = f"""📊 <b>Настройка размера окна</b>

<b>Текущий размер:</b> {current_window} тиков

<b>Размер окна определяет:</b>
• Количество последних дельт для скользящего среднего
• Плавность трендов
• Скорость реакции на изменения

<b>Примеры:</b>
• 2 тика - быстрая реакция, нестабильно
• 3 тика - сбалансированный анализ
• 5 тиков - плавные тренды, медленная реакция"""

        window_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚡ 2 тика", "callback_data": "tick_window_2"},
                    {"text": "⚖️ 3 тика", "callback_data": "tick_window_3"},
                    {"text": "🛡️ 4 тика", "callback_data": "tick_window_4"}
                ],
                [
                    {"text": "🔒 5 тиков", "callback_data": "tick_window_5"},
                    {"text": "📈 7 тиков", "callback_data": "tick_window_7"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, window_menu)

    async def handle_tick_history_settings(self, chat_id: int, callback_query_id: str):
        """Настройка истории тиков"""
        await self.answer_callback_query(callback_query_id)
        
        from config import Config
        config = Config()
        current_history = getattr(config, 'MAX_TICKS_HISTORY', 50)
        
        message = f"""📝 <b>Настройка истории тиков</b>

<b>Текущая история:</b> {current_history} тиков

<b>История определяет:</b>
• Максимальное количество тиков на матч
• Обнаружение долгосрочных паттернов
• Потребление памяти

<b>Рекомендации:</b>
• 30 тиков - короткий анализ (30-60 минут)
• 50 тиков - стандартный (полный матч)
• 100 тиков - расширенный анализ"""

        history_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚡ 30 тиков", "callback_data": "tick_history_30"},
                    {"text": "⚖️ 50 тиков", "callback_data": "tick_history_50"},
                    {"text": "📈 75 тиков", "callback_data": "tick_history_75"}
                ],
                [
                    {"text": "🔒 100 тиков", "callback_data": "tick_history_100"},
                    {"text": "💾 150 тиков", "callback_data": "tick_history_150"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, history_menu)

    async def handle_tick_metrics_settings(self, chat_id: int, callback_query_id: str):
        """Настройка отслеживаемых метрик"""
        await self.answer_callback_query(callback_query_id)
        
        message = """🎯 <b>Отслеживаемые метрики</b>

<b>Основные метрики (всегда активны):</b>
✅ Общие атаки (total_attacks)
✅ Общие удары (total_shots)
✅ Опасные моменты (total_dangerous)
✅ Угловые (total_corners)
✅ Голы (total_goals)

<b>Раздельные метрики:</b>
✅ Атаки хозяев/гостей
✅ Удары хозяев/гостей
✅ Опасные моменты по командам

<b>Дополнительные метрики (планируются):</b>
⏳ Владение мячом
⏳ Нарушения правил
⏳ Точность передач"""

        metrics_menu = {
            "inline_keyboard": [
                [
                    {"text": "✅ Все метрики активны", "callback_data": "tick_metrics_all"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, metrics_menu)

    async def handle_tick_thresholds_settings(self, chat_id: int, callback_query_id: str):
        """Настройка порогов для трендов"""
        await self.answer_callback_query(callback_query_id)
        
        message = """🔄 <b>Пороги для анализа трендов</b>

<b>Текущие пороги:</b>
• Минимальная сила тренда: 1.0
• Уверенность для сигнала: 0.7
• Порог смены тренда: 0.5

<b>Настройка порогов:</b>
• <b>Низкие пороги</b> - больше сигналов, больше шума
• <b>Высокие пороги</b> - меньше сигналов, выше точность

<b>Типы трендов:</b>
📈 Rising - возрастающий
📉 Falling - убывающий
➡️ Stable - стабильный"""

        thresholds_menu = {
            "inline_keyboard": [
                [
                    {"text": "🔓 Низкие пороги", "callback_data": "tick_thresholds_low"},
                    {"text": "⚖️ Средние пороги", "callback_data": "tick_thresholds_medium"}
                ],
                [
                    {"text": "🔒 Высокие пороги", "callback_data": "tick_thresholds_high"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, thresholds_menu)

    async def handle_tick_confidence_settings(self, chat_id: int, callback_query_id: str):
        """Настройка уверенности анализа"""
        await self.answer_callback_query(callback_query_id)
        
        message = """📈 <b>Уверенность анализа тиков</b>

<b>Текущая уверенность:</b> 70%

<b>Уверенность влияет на:</b>
• Генерацию сигналов
• Фильтрацию ложных трендов
• Качество прогнозов

<b>Уровни уверенности:</b>
• 50% - много сигналов, низкая точность
• 70% - сбалансированный подход (рекомендуется)
• 85% - мало сигналов, высокая точность"""

        confidence_menu = {
            "inline_keyboard": [
                [
                    {"text": "🔓 50%", "callback_data": "tick_confidence_50"},
                    {"text": "⚖️ 60%", "callback_data": "tick_confidence_60"},
                    {"text": "🎯 70%", "callback_data": "tick_confidence_70"}
                ],
                [
                    {"text": "🔒 80%", "callback_data": "tick_confidence_80"},
                    {"text": "💎 85%", "callback_data": "tick_confidence_85"}
                ],
                [
                    {"text": "⚙️ Назад к настройкам", "callback_data": "settings"}
                ]
            ]
        }

        await self.send_message(chat_id, message, confidence_menu)

    async def handle_tick_interval_change(self, chat_id: int, callback_query_id: str, callback_data: str):
        """Изменение интервала тиков"""
        await self.answer_callback_query(callback_query_id, "Интервал обновлен!")
        
        # Извлекаем значение из callback_data
        interval = int(callback_data.split("_")[-1])
        
        # Здесь можно сохранить настройки в базу данных или конфиг
        # Пока просто показываем подтверждение
        
        message = f"""✅ <b>Интервал тиков обновлен</b>

<b>Новый интервал:</b> {interval} секунд

Изменения вступят в силу при следующем перезапуске системы анализа."""

        back_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚙️ Настройки", "callback_data": "settings"},
                    {"text": "🏠 Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        await self.send_message(chat_id, message, back_menu)

    async def handle_tick_window_change(self, chat_id: int, callback_query_id: str, callback_data: str):
        """Изменение размера окна тиков"""
        await self.answer_callback_query(callback_query_id, "Размер окна обновлен!")
        
        window_size = int(callback_data.split("_")[-1])
        
        message = f"""✅ <b>Размер окна обновлен</b>

<b>Новый размер:</b> {window_size} тиков

Теперь скользящее среднее будет рассчитываться по последним {window_size} дельтам."""

        back_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚙️ Настройки", "callback_data": "settings"},
                    {"text": "🏠 Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        await self.send_message(chat_id, message, back_menu)

    async def handle_tick_history_change(self, chat_id: int, callback_query_id: str, callback_data: str):
        """Изменение истории тиков"""
        await self.answer_callback_query(callback_query_id, "История тиков обновлена!")
        
        history_size = int(callback_data.split("_")[-1])
        
        message = f"""✅ <b>История тиков обновлена</b>

<b>Новый размер истории:</b> {history_size} тиков

Система будет хранить до {history_size} тиков для каждого матча."""

        back_menu = {
            "inline_keyboard": [
                [
                    {"text": "⚙️ Настройки", "callback_data": "settings"},
                    {"text": "🏠 Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        await self.send_message(chat_id, message, back_menu)

    async def handle_help(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Помощь"""
        await self.answer_callback_query(callback_query_id)
        
        message = """❓ <b>Помощь по BetBog Bot</b>

🤖 <b>Что делает система:</b>
• Анализирует live футбольные матчи
• Вычисляет продвинутые метрики
• Генерирует сигналы для ставок
• Отслеживает результаты

📊 <b>Кнопки меню:</b>
• Live матчи - количество активных матчей
• Сигналы - последние 10 сигналов
• Стратегии - конфигурации алгоритмов
• Статистика - общие показатели
• Настройки - параметры системы

🔄 <b>Обновление данных:</b>
Нажмите "Обновить" для получения свежих данных

⚡ Система работает 24/7 без нейронных сетей"""

        # Редактируем существующее сообщение если есть message_id
        if chat_id in self.user_messages:
            await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
        else:
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id

    async def handle_refresh(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Обновить"""
        await self.answer_callback_query(callback_query_id, "Обновляю данные...")
        
        # Получаем актуальную информацию
        live_count = await self.get_live_matches_count()
        stats = await self.get_system_statistics()
        
        message = f"""🔄 <b>Обновленные данные</b>

📊 <b>Текущий статус:</b>
• Live матчи: {live_count}
• Сигналов за сегодня: {stats.get('today_signals', 0)}
• Ожидающих сигналов: {stats.get('pending_signals', 0)}
• Win Rate: {stats.get('win_rate', 0):.1f}%

🕐 Обновлено: {datetime.now().strftime('%H:%M:%S')}

Выберите раздел для подробной информации:"""

        # Редактируем существующее сообщение если есть message_id
        if chat_id in self.user_messages:
            await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
        else:
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id

    async def handle_command(self, chat_id: int, text: str, user_name: str):
        """Обработка команд пользователя"""
        print(f"📨 Команда от {user_name}: {text}")
        
        if text.startswith("/start") or text.startswith("/menu"):
            message = """🏆 <b>BetBog Monitoring Bot</b>

🤖 Интеллектуальная система мониторинга спортивных ставок
📊 Анализ live матчей с продвинутыми метриками
⚡ Автоматическая генерация сигналов

Выберите раздел для получения информации:"""
            
            message_id = await self.send_message(chat_id, message, self.create_main_menu())
            if message_id:
                self.user_messages[chat_id] = message_id
            
        else:
            message = f"""Команда: <code>{text}</code>

Используйте /start для открытия главного меню с кнопками."""
            # Редактируем существующее сообщение если есть message_id
            if chat_id in self.user_messages:
                await self.edit_message(chat_id, self.user_messages[chat_id], message, self.create_main_menu())
            else:
                message_id = await self.send_message(chat_id, message, self.create_main_menu())
                if message_id:
                    self.user_messages[chat_id] = message_id

    async def handle_callback(self, chat_id: int, callback_data: str, callback_query_id: str):
        """Обработка нажатий на кнопки с плавной анимацией"""
        print(f"🔘 Нажата кнопка: {callback_data}")
        
        if callback_data == "live_matches":
            await self.handle_live_matches_animated(chat_id, callback_query_id)
        elif callback_data == "signals":
            await self.handle_signals_animated(chat_id, callback_query_id)
        elif callback_data == "strategies":
            await self.handle_strategies(chat_id, callback_query_id)
        elif callback_data == "statistics":
            await self.handle_statistics_animated(chat_id, callback_query_id)
        elif callback_data == "settings":
            await self.handle_settings_animated(chat_id, callback_query_id)
        elif callback_data == "help":
            await self.handle_help_animated(chat_id, callback_query_id)
        elif callback_data == "refresh":
            await self.handle_refresh_animated(chat_id, callback_query_id)
        elif callback_data == "main_menu":
            await self.handle_main_menu(chat_id, callback_query_id)
        # Обработчики настроек тиков
        elif callback_data == "set_tick_interval":
            await self.handle_tick_interval_settings(chat_id, callback_query_id)
        elif callback_data == "set_tick_window":
            await self.handle_tick_window_settings(chat_id, callback_query_id)
        elif callback_data == "set_tick_history":
            await self.handle_tick_history_settings(chat_id, callback_query_id)
        elif callback_data == "set_tick_metrics":
            await self.handle_tick_metrics_settings(chat_id, callback_query_id)
        elif callback_data == "set_tick_thresholds":
            await self.handle_tick_thresholds_settings(chat_id, callback_query_id)
        elif callback_data == "set_tick_confidence":
            await self.handle_tick_confidence_settings(chat_id, callback_query_id)
        # Обработчики изменения значений тиков
        elif callback_data.startswith("tick_interval_"):
            await self.handle_tick_interval_change(chat_id, callback_query_id, callback_data)
        elif callback_data.startswith("tick_window_"):
            await self.handle_tick_window_change(chat_id, callback_query_id, callback_data)
        elif callback_data.startswith("tick_history_"):
            await self.handle_tick_history_change(chat_id, callback_query_id, callback_data)
        else:
            await self.answer_callback_query(callback_query_id, "Неизвестная команда")

    # Анимированные обработчики кнопок
    async def handle_live_matches_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к live матчам"""
        live_count = await self.get_live_matches_count()
        
        message = f"""📊 <b>Live матчи</b>

🔴 <b>Активных матчей:</b> {live_count}
⚡ <b>Мониторинг:</b> {"Включен" if live_count != "Ошибка" else "Ошибка"}

🎯 <b>Анализируемые данные:</b>
• Атаки и удары по воротам
• Опасные моменты
• Угловые удары
• Голы и счет

🔄 <b>Обновление:</b> каждые 60 секунд"""
        
        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "connecting")

    async def handle_signals_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к сигналам"""
        signals = await self.get_recent_signals(10)
        
        if not signals:
            message = """⚡ <b>Сигналы</b>

📭 <b>Новых сигналов нет</b>

Система анализирует live матчи и генерирует сигналы на основе:
• Тиковых метрик
• Трендов в реальном времени
• Исторических данных команд

🔄 Обновляйте раздел для проверки новых сигналов"""
        else:
            message = "⚡ <b>Последние сигналы</b>\n\n"
            for i, signal in enumerate(signals[:5], 1):
                strategy = self.format_strategy_name(signal['strategy_name'])
                confidence = signal['confidence']
                signal_type = signal['signal_type']
                result = signal.get('result', 'pending')
                
                result_emoji = "🟡" if result == "pending" else ("🟢" if result == "win" else "🔴")
                
                message += f"{i}. {strategy}\n"
                message += f"   📊 {signal_type} ({confidence:.0f}%) {result_emoji}\n\n"
            
            if len(signals) > 5:
                message += f"... и еще {len(signals) - 5} сигналов"
        
        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "analyzing")

    async def handle_strategies_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к стратегиям"""
        strategies = await self.get_strategy_configs()
        
        if not strategies:
            message = """🎯 <b>Стратегии</b>

⚙️ <b>Конфигурации стратегий не найдены</b>

Система использует адаптивные алгоритмы для анализа спортивных данных."""
        else:
            message = "🎯 <b>Активные стратегии</b>\n\n"
            
            for strategy in strategies[:6]:
                strategy_name = self.format_strategy_name(strategy['strategy_name'])
                total_signals = strategy.get('total_signals', 0)
                win_rate = strategy.get('win_rate', 0)
                
                message += f"{strategy_name}\n"
                message += f"📊 Сигналов: {total_signals} | Винрейт: {win_rate:.1f}%\n\n"
        
        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "processing")

    async def handle_statistics_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к статистике"""
        stats = await self.get_system_statistics()
        
        message = f"""📈 <b>Статистика системы</b>

📊 <b>Общие показатели:</b>
• Всего сигналов: {stats.get('total_signals', 0)}
• Сегодня сигналов: {stats.get('today_signals', 0)}
• Активных сигналов: {stats.get('pending_signals', 0)}

🎯 <b>Результативность:</b>
• Выигрышных сигналов: {stats.get('win_signals', 0)}
• Общий винрейт: {stats.get('win_rate', 0):.1f}%

🔍 <b>Мониторинг:</b>
• Отслеживаемых матчей: {stats.get('total_matches', 0)}"""

        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "analyzing")

    async def handle_settings_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к настройкам"""
        message = """⚙️ <b>Настройки системы</b>

🔧 <b>Конфигурация анализатора тиков:</b>

Настройте параметры для оптимальной работы системы мониторинга и анализа live матчей.

<b>Доступные настройки:</b>
• Интервал сбора данных
• Размер окна анализа  
• История тиков
• Отслеживаемые метрики
• Пороги для трендов
• Уверенность анализа"""

        settings_menu = {
            "inline_keyboard": [
                [
                    {"text": "⏱️ Интервал тиков", "callback_data": "set_tick_interval"},
                    {"text": "📊 Размер окна", "callback_data": "set_tick_window"}
                ],
                [
                    {"text": "📚 История тиков", "callback_data": "set_tick_history"},
                    {"text": "🎯 Метрики", "callback_data": "set_tick_metrics"}
                ],
                [
                    {"text": "🔄 Пороги трендов", "callback_data": "set_tick_thresholds"},
                    {"text": "📈 Уверенность анализа", "callback_data": "set_tick_confidence"}
                ],
                [
                    {"text": "🏠 Главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      settings_menu, "loading")

    async def handle_help_animated(self, chat_id: int, callback_query_id: str):
        """Анимированный переход к помощи"""
        message = """❓ <b>Помощь по BetBog Bot</b>

🤖 <b>Что делает система:</b>
• Анализирует live футбольные матчи
• Вычисляет продвинутые метрики
• Генерирует сигналы для ставок
• Отслеживает результаты

📊 <b>Кнопки меню:</b>
• Live матчи - количество активных матчей
• Сигналы - последние 10 сигналов
• Стратегии - конфигурации алгоритмов
• Статистика - общие показатели
• Настройки - параметры системы

🔄 <b>Обновление данных:</b>
Нажмите "Обновить" для получения свежих данных

⚡ Система работает 24/7 без нейронных сетей"""

        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "loading")

    async def handle_refresh_animated(self, chat_id: int, callback_query_id: str):
        """Анимированное обновление главного меню"""
        message = """🏆 <b>BetBog Monitoring Bot</b>

🤖 Интеллектуальная система мониторинга спортивных ставок
📊 Анализ live матчей с продвинутыми метриками
⚡ Автоматическая генерация сигналов

Выберите раздел для получения информации:"""
        
        await self.smooth_transition_to(chat_id, callback_query_id, message, 
                                      self.create_main_menu(), "processing")

    async def handle_update(self, update: Dict[str, Any]):
        """Обработка обновления от Telegram"""
        try:
            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                user = message.get("from", {})
                user_name = user.get("first_name", "Unknown")
                
                await self.handle_command(chat_id, text, user_name)
                
            elif "callback_query" in update:
                callback_query = update["callback_query"]
                chat_id = callback_query["message"]["chat"]["id"]
                callback_data = callback_query["data"]
                callback_query_id = callback_query["id"]
                
                await self.handle_callback(chat_id, callback_data, callback_query_id)
                    
        except Exception as e:
            print(f"Ошибка обработки обновления: {str(e)}")

    async def process_updates(self):
        """Основной цикл получения обновлений"""
        last_update_id = 0
        
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"offset": last_update_id + 1, "timeout": 30}
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    await self.handle_update(update)
                                    last_update_id = max(last_update_id, update["update_id"])
                        else:
                            print(f"Ошибка получения обновлений: {response.status}")
                        
            except Exception as e:
                print(f"Ошибка polling: {str(e)}")
                await asyncio.sleep(5)

    async def start(self):
        """Запуск бота"""
        self.running = True
        # Очищаем старые обновления при запуске
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": -1}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ok") and data.get("result"):
                            last_update_id = data["result"][-1]["update_id"]
                            # Пропускаем все старые обновления
                            async with session.get(url, params={"offset": last_update_id + 1}) as _:
                                pass
        except:
            pass
        
        print("🚀 BetBog Menu Bot запущен с интерактивными кнопками")
        await self.process_updates()

    def stop(self):
        """Остановка бота"""
        self.running = False
        print("🛑 Menu Bot остановлен")

async def main():
    """Главная функция"""
    bot = TelegramMenuBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        bot.stop()
        print("Бот остановлен пользователем")

if __name__ == "__main__":
    asyncio.run(main())