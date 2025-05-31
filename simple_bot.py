import asyncio
from typing import Dict, Any
from config import Config
from logger import BetBogLogger

class SimpleBettingBot:
    """Упрощенная версия бота для тестирования системы мониторинга"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("SIMPLE_BOT")
        self.running = False
        
    async def initialize(self):
        """Инициализация бота"""
        self.logger.info("Инициализация упрощенного бота мониторинга")
        
    async def send_signal_notification(self, 
                                     signal_data: Dict[str, Any],
                                     match_data: Dict[str, Any]):
        """Отправка уведомления о сигнале (консольный вывод)"""
        self.logger.strategy_signal(
            signal_data.get('strategy_name', 'UNKNOWN'),
            signal_data.get('signal_type', 'BUY'),
            signal_data.get('confidence', 0.0),
            f"Матч: {match_data.get('home_team', 'HOME')} vs {match_data.get('away_team', 'AWAY')}"
        )
        
        print(f"\n🚨 СИГНАЛ СТАВКИ 🚨")
        print(f"Стратегия: {signal_data.get('strategy_name')}")
        print(f"Тип: {signal_data.get('signal_type')}")
        print(f"Уверенность: {signal_data.get('confidence', 0):.1%}")
        print(f"Матч: {match_data.get('home_team')} vs {match_data.get('away_team')}")
        print(f"Минута: {signal_data.get('minute', 0)}")
        print(f"Описание: {signal_data.get('description', 'Нет описания')}")
        print("-" * 50)
        
    async def send_result_notification(self, 
                                     signal_data: Dict[str, Any],
                                     match_data: Dict[str, Any],
                                     result: str,
                                     profit_loss: float):
        """Отправка уведомления о результате"""
        status_emoji = "✅" if result == "won" else "❌" if result == "lost" else "⏳"
        
        self.logger.profit_loss_update(
            signal_data.get('strategy_name', 'UNKNOWN'),
            profit_loss,
            1,
            1.0 if result == "won" else 0.0
        )
        
        print(f"\n{status_emoji} РЕЗУЛЬТАТ СТАВКИ {status_emoji}")
        print(f"Стратегия: {signal_data.get('strategy_name')}")
        print(f"Матч: {match_data.get('home_team')} vs {match_data.get('away_team')}")
        print(f"Результат: {result.upper()}")
        print(f"Прибыль/Убыток: {profit_loss:+.2f}")
        print("-" * 50)
        
    async def start_bot(self):
        """Запуск бота"""
        self.running = True
        self.logger.success("Упрощенный бот запущен - мониторинг сигналов активен")
        
    async def stop_bot(self):
        """Остановка бота"""
        self.running = False
        self.logger.info("Упрощенный бот остановлен")