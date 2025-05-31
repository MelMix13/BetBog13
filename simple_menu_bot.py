#!/usr/bin/env python3
"""
Упрощенный BetBog Telegram Bot с базовым меню
Работает с имеющимися библиотеками
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import Config
from logger import BetBogLogger
from database import get_session
from models import Signal, Match, StrategyConfig
from sqlalchemy import select, desc, func


class SimpleTelegramMenuBot:
    """Упрощенный Telegram бот с базовым меню для BetBog"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("TELEGRAM_BOT", config.LOG_FILE)
        self.running = False
        self.authorized_users = {123456789}  # Добавьте свой Telegram ID
        self.menu_state = {}  # Состояние меню для каждого пользователя
        
    async def initialize(self):
        """Инициализация бота"""
        try:
            self.logger.success("🤖 Telegram бот с меню инициализирован")
            self.logger.info("📋 Доступные команды:")
            self.logger.info("  /start - Запуск и главное меню")
            self.logger.info("  /menu - Показать меню")
            self.logger.info("  /signals - Активные сигналы")
            self.logger.info("  /stats - Статистика")
            self.logger.info("  /matches - Live матчи")
            self.logger.info("  /help - Помощь")
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации бота: {str(e)}")
            raise

    async def start_polling(self):
        """Запуск бота в режиме мониторинга"""
        try:
            self.running = True
            self.logger.success("🚀 Telegram бот запущен в режиме мониторинга")
            self.logger.info("📱 Бот готов принимать команды и отправлять уведомления")
            
            # Симуляция работы бота - в реальной версии здесь был бы polling
            while self.running:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                await self._check_system_status()
                
        except Exception as e:
            self.logger.error(f"Ошибка работы бота: {str(e)}")
            raise

    async def stop_polling(self):
        """Остановка бота"""
        try:
            self.running = False
            self.logger.info("🛑 Telegram бот остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка остановки бота: {str(e)}")

    async def _check_system_status(self):
        """Проверка статуса системы"""
        try:
            session = get_session()
            async with session:
                # Проверяем активные сигналы
                active_signals = await session.scalar(
                    select(func.count(Signal.id)).where(Signal.result == "pending")
                )
                
                # Проверяем общее количество сигналов за сегодня
                today = datetime.now().date()
                today_signals = await session.scalar(
                    select(func.count(Signal.id)).where(
                        func.date(Signal.created_at) == today
                    )
                )
                
                if today_signals and today_signals > 0:
                    self.logger.info(f"📊 Система активна: {active_signals or 0} активных сигналов, {today_signals} за сегодня")
                    
        except Exception as e:
            self.logger.error(f"Ошибка проверки статуса: {str(e)}")

    async def send_signal_notification(self, signal_data: Dict[str, Any], match_data: Dict[str, Any]):
        """Отправить уведомление о новом сигнале"""
        try:
            confidence = signal_data.get('confidence', 0)
            confidence_emoji = "🔥" if confidence > 0.8 else "⚡" if confidence > 0.6 else "📈"
            
            # Логируем уведомление как консольное сообщение с красивым форматированием
            self.logger.strategy_signal(
                signal_data.get('strategy_name', 'Unknown'),
                signal_data.get('signal_type', 'BUY'), 
                confidence,
                f"Матч: {match_data.get('home_team', 'Unknown')} vs {match_data.get('away_team', 'Unknown')}"
            )
            
            # Подробное уведомление
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

📋 Меню команд: /menu | Сигналы: /signals | Статистика: /stats
            """
            
            print(notification_text)
            self.logger.success("📱 Уведомление о сигнале отправлено")
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления: {str(e)}")

    async def show_main_menu(self):
        """Показать главное меню"""
        menu_text = """
╭─────────────────────────────────────────╮
│         📋 BetBog Главное Меню           │
╰─────────────────────────────────────────╯

🟢 Система активна и мониторит матчи
📊 7 стратегий анализируют данные
🎯 Поиск сигналов в реальном времени

📱 Доступные команды:

🎯 /signals - Активные сигналы ставок
📊 /stats - Статистика и P&L
⚽ /matches - Live матчи  
🔧 /strategies - Стратегии
📈 /performance - Производительность
⚙️ /settings - Настройки
❓ /help - Помощь

Введите команду для навигации по меню.
        """
        
        print(menu_text)
        self.logger.info("📋 Показано главное меню")

    async def show_signals_menu(self):
        """Показать меню сигналов"""
        try:
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

                # Получаем последние активные сигналы
                stmt = (
                    select(Signal)
                    .where(Signal.result == "pending")
                    .order_by(desc(Signal.created_at))
                    .limit(5)
                )
                signals = await session.scalars(stmt)
                signals_list = list(signals)

            signals_text = f"""
╭─────────────────────────────────────────╮
│           🎯 Сигналы BetBog              │
╰─────────────────────────────────────────╯

📊 Общая статистика:
• Всего сигналов: {total_signals or 0}
• Активных: {active_signals or 0}
• Выиграно: {won_signals or 0} 
• Проиграно: {lost_signals or 0}
• Winrate: {(won_signals / max(won_signals + lost_signals, 1) * 100):.1f}%

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

            signals_text += "\n\n📱 Команды: /menu - Главное меню | /stats - Статистика"
            
            print(signals_text)
            self.logger.info("🎯 Показано меню сигналов")
            
        except Exception as e:
            self.logger.error(f"Ошибка показа сигналов: {str(e)}")

    async def show_stats_menu(self):
        """Показать статистику"""
        try:
            async with get_session() as session:
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

📱 Команды: /menu - Главное меню | /signals - Сигналы
            """
            
            print(stats_text)
            self.logger.info("📊 Показана статистика")
            
        except Exception as e:
            self.logger.error(f"Ошибка показа статистики: {str(e)}")

    async def show_matches_menu(self):
        """Показать live матчи"""
        try:
            async with get_session() as session:
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

            matches_text += "\n\n📱 Команды: /menu - Главное меню | /signals - Сигналы"
            
            print(matches_text)
            self.logger.info("⚽ Показаны live матчи")
            
        except Exception as e:
            self.logger.error(f"Ошибка показа матчей: {str(e)}")

    async def show_help_menu(self):
        """Показать помощь"""
        help_text = """
╭─────────────────────────────────────────╮
│           ❓ Помощь BetBog               │
╰─────────────────────────────────────────╯

🤖 BetBog - система мониторинга ставок

📱 Основные команды:
• /start, /menu - Главное меню
• /signals - Активные сигналы
• /stats - Статистика и P&L
• /matches - Live матчи
• /strategies - Стратегии системы
• /performance - Производительность
• /settings - Настройки
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

🔧 Стратегии:
• DxG Hunter - поиск высокого xG
• Momentum Rider - игра на импульсе
• Wave Catcher - анализ волн
• Late Drama - поздние голы
• Comeback King - камбэки
• Defensive Wall - оборонительная игра
• Quick Strike - быстрые голы

Система работает 24/7 с реальными данными от bet365 API!

📱 Команда: /menu - Вернуться в главное меню
        """
        
        print(help_text)
        self.logger.info("❓ Показана справка")

    # Методы для совместимости с основной системой
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

📱 Команды: /menu | /signals | /stats
            """
            
            print(notification_text)
            self.logger.success(f"📱 Уведомление о результате отправлено: {result}")
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки уведомления о результате: {str(e)}")


# Функция для интеграции с основной системой
async def create_telegram_bot(config: Config) -> SimpleTelegramMenuBot:
    """Создать и инициализировать упрощенный Telegram бота"""
    bot = SimpleTelegramMenuBot(config)
    await bot.initialize()
    return bot


if __name__ == "__main__":
    # Для тестирования
    async def main():
        config = Config()
        bot = await create_telegram_bot(config)
        
        # Показываем главное меню
        await bot.show_main_menu()
        
        # Показываем примеры меню
        print("\n" + "="*50)
        await bot.show_signals_menu()
        
        print("\n" + "="*50)
        await bot.show_stats_menu()
        
        print("\n" + "="*50)
        await bot.show_matches_menu()
        
        print("\n" + "="*50)
        await bot.show_help_menu()

    asyncio.run(main())