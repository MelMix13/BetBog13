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
                        print(f"✅ Сообщение отправлено пользователю {chat_id}")
                        return True
                    else:
                        print(f"❌ Ошибка отправки: {response.status}")
                        return False
                        
        except Exception as e:
            print(f"Ошибка отправки сообщения: {str(e)}")
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
        """Получение количества live матчей"""
        conn = await self.get_db_connection()
        if not conn:
            return "Н/Д"
        
        try:
            # Получаем количество активных матчей за последний час
            query = """
                SELECT COUNT(*) 
                FROM matches 
                WHERE updated_at > NOW() - INTERVAL '1 hour'
            """
            count = await conn.fetchval(query)
            return count or 0
        except Exception as e:
            print(f"Ошибка получения live матчей: {e}")
            return "Ошибка"
        finally:
            await conn.close()

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
                SELECT strategy_name, thresholds, enabled, total_signals, win_rate
                FROM strategy_configs 
                ORDER BY strategy_name
            """
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Ошибка получения стратегий: {e}")
            return []
        finally:
            await conn.close()

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

        await self.send_message(chat_id, message, self.create_main_menu())

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

        await self.send_message(chat_id, message, self.create_main_menu())

    async def handle_strategies(self, chat_id: int, callback_query_id: str):
        """Обработка кнопки Стратегии"""
        await self.answer_callback_query(callback_query_id, "Загружаю конфигурации стратегий...")
        
        strategies = await self.get_strategy_configs()
        
        if not strategies:
            message = """🎯 <b>Стратегии</b>

⚙️ <b>Конфигурации стратегий не найдены</b>

Система использует адаптивные алгоритмы для анализа спортивных данных."""
        else:
            message = "🎯 <b>Активные стратегии</b>\n\n"
            
            for strategy in strategies:
                status_emoji = "🟢" if strategy.get('enabled', True) else "🔴"
                strategy_name = strategy['strategy_name']
                total_signals = strategy.get('total_signals', 0)
                win_rate = strategy.get('win_rate', 0)
                
                message += f"{status_emoji} <b>{strategy_name}</b>\n"
                message += f"   📊 Сигналов: {total_signals}\n"
                message += f"   🎯 Win Rate: {win_rate:.1f}%\n"
                
                # Показываем пороги если они есть
                if strategy.get('thresholds'):
                    try:
                        thresholds = json.loads(strategy['thresholds']) if isinstance(strategy['thresholds'], str) else strategy['thresholds']
                        if thresholds:
                            message += "   ⚙️ Пороги: "
                            threshold_parts = []
                            for key, value in thresholds.items():
                                threshold_parts.append(f"{key}={value}")
                            message += ", ".join(threshold_parts[:3])  # Показываем первые 3
                            message += "\n"
                    except:
                        pass
                        
                message += "\n"

        await self.send_message(chat_id, message, self.create_main_menu())

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
        
        message = """⚙️ <b>Настройки системы</b>

🔧 <b>Текущие настройки:</b>
• Интервал проверки: 60 сек
• Максимум матчей: 20 за цикл
• ML оптимизация: каждые 24 часа
• Автоочистка: включена

📊 <b>Пороги по умолчанию:</b>
• Confidence: ≥ 0.7
• Momentum: ≥ 0.6
• Gradient: ≥ 0.5

⚡ Система работает в автоматическом режиме"""

        await self.send_message(chat_id, message, self.create_main_menu())

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

        await self.send_message(chat_id, message, self.create_main_menu())

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

        await self.send_message(chat_id, message, self.create_main_menu())

    async def handle_command(self, chat_id: int, text: str, user_name: str):
        """Обработка команд пользователя"""
        print(f"📨 Команда от {user_name}: {text}")
        
        if text.startswith("/start") or text.startswith("/menu"):
            message = """🏆 <b>BetBog Monitoring Bot</b>

🤖 Интеллектуальная система мониторинга спортивных ставок
📊 Анализ live матчей с продвинутыми метриками
⚡ Автоматическая генерация сигналов

Выберите раздел для получения информации:"""
            
            await self.send_message(chat_id, message, self.create_main_menu())
            
        else:
            message = f"""Команда: <code>{text}</code>

Используйте /start для открытия главного меню с кнопками."""
            await self.send_message(chat_id, message, self.create_main_menu())

    async def handle_callback(self, chat_id: int, callback_data: str, callback_query_id: str):
        """Обработка нажатий на кнопки"""
        print(f"🔘 Нажата кнопка: {callback_data}")
        
        if callback_data == "live_matches":
            await self.handle_live_matches(chat_id, callback_query_id)
        elif callback_data == "signals":
            await self.handle_signals(chat_id, callback_query_id)
        elif callback_data == "strategies":
            await self.handle_strategies(chat_id, callback_query_id)
        elif callback_data == "statistics":
            await self.handle_statistics(chat_id, callback_query_id)
        elif callback_data == "settings":
            await self.handle_settings(chat_id, callback_query_id)
        elif callback_data == "help":
            await self.handle_help(chat_id, callback_query_id)
        elif callback_data == "refresh":
            await self.handle_refresh(chat_id, callback_query_id)
        else:
            await self.answer_callback_query(callback_query_id, "Неизвестная команда")

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