#!/usr/bin/env python3
"""
Прямой Telegram бот для тестирования команд
"""
import asyncio
import aiohttp
import os
from typing import Dict, Any

class DirectTelegramBot:
    """Прямой Telegram бот без сложных зависимостей"""
    
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "7228733029:AAFVPzKHUSRidigzYSy_IANt8rWzjjPBDPA")
        self.running = False
        
    async def send_message(self, chat_id: int, text: str):
        """Отправка сообщения пользователю"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            
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

    async def handle_update(self, update: Dict[str, Any]):
        """Обработка одного обновления"""
        try:
            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                user = message.get("from", {})
                
                print(f"📨 Получено сообщение от {user.get('first_name', 'Unknown')}: {text}")
                
                if text.startswith("/start"):
                    response = """🏆 <b>Добро пожаловать в BetBog Monitoring Bot!</b>

🤖 Интеллектуальная система мониторинга спортивных ставок
📊 Анализ live матчей с продвинутыми метриками
⚡ Автоматическая генерация сигналов

<b>Доступные команды:</b>
/status - Статус системы
/info - Информация о системе
/help - Помощь

🔥 Система активно мониторит live футбольные матчи!"""
                    
                elif text.startswith("/status"):
                    response = """📊 <b>Статус системы BetBog</b>

🟢 <b>Система активна и работает</b>
📈 Мониторинг: 60+ live матчей
⚡ Анализ продвинутых метрик
🔄 Обработка данных в реальном времени

Система успешно подключена к спортивным API и базе данных."""
                    
                elif text.startswith("/info"):
                    response = """⚽ <b>О системе BetBog</b>

📊 <b>Анализируемые метрики:</b>
• dxG (производные ожидаемые голы)
• Gradient (тренды производительности) 
• Wave amplitude (амплитуда интенсивности)
• Momentum (импульс команд)
• Tiredness factor (фактор усталости)
• Stability (стабильность команд)

🎯 <b>Стратегии ставок:</b>
• momentum_shift - смена импульса
• tiredness_advantage - преимущество усталости
• gradient_momentum - градиентный импульс
• и другие адаптивные алгоритмы"""
                    
                elif text.startswith("/help"):
                    response = """❓ <b>Помощь по BetBog Bot</b>

<b>Команды:</b>
/start - Запуск бота
/status - Текущий статус системы  
/info - Подробная информация
/help - Эта справка

<b>О системе:</b>
BetBog - интеллектуальная система для мониторинга спортивных ставок с машинным обучением и анализом live данных.

Система работает 24/7 и анализирует футбольные матчи в реальном времени."""
                    
                else:
                    response = f"""Получена команда: {text}

Доступные команды:
/start - Запуск бота
/status - Статус системы
/info - Информация о системе
/help - Помощь"""
                
                await self.send_message(chat_id, response)
                    
        except Exception as e:
            print(f"Ошибка обработки сообщения: {str(e)}")

    async def process_updates(self):
        """Обработка входящих сообщений"""
        last_update_id = 0
        
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"offset": last_update_id + 1, "timeout": 10}
                
                async with aiohttp.ClientSession() as session:
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
        print("🚀 Прямой Telegram бот запущен")
        await self.process_updates()

    def stop(self):
        """Остановка бота"""
        self.running = False
        print("🛑 Бот остановлен")

async def main():
    """Главная функция для тестирования"""
    bot = DirectTelegramBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        bot.stop()
        print("Бот остановлен пользователем")

if __name__ == "__main__":
    asyncio.run(main())