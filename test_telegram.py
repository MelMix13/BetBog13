#!/usr/bin/env python3
"""
Простой тест Telegram бота для проверки токена
"""
import asyncio
import os
from telegram import Bot

async def test_telegram_bot():
    """Тест подключения к Telegram боту"""
    bot_token = os.getenv("BOT_TOKEN", "7228733029:AAFVPzKHUSRidigzYSy_IANt8rWzjjPBDPA")
    
    try:
        bot = Bot(token=bot_token)
        
        # Получаем информацию о боте
        me = await bot.get_me()
        print(f"✅ Бот подключен успешно!")
        print(f"Имя бота: {me.first_name}")
        print(f"Username: @{me.username}")
        print(f"ID: {me.id}")
        
        # Проверяем, есть ли обновления
        updates = await bot.get_updates(limit=1)
        print(f"Последние обновления: {len(updates)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к боту: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_telegram_bot())