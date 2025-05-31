"""
Сборщик исторических данных матчей
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Any
from api_client import APIClient
from config import Config
from logger import BetBogLogger

class DataCollector:
    """Сборщик и сохранение исторических данных матчей"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("DATA_COLLECTOR")
    
    async def collect_and_store_historical_data(self, days_back: int = 7):
        """Сбор и сохранение исторических данных за указанный период"""
        self.logger.info(f"Начинаем сбор исторических данных за {days_back} дней")
        
        async with APIClient(self.config) as api_client:
            # Получаем исторические матчи
            historical_matches = await api_client.get_finished_matches(days_back)
            self.logger.info(f"Получено {len(historical_matches)} исторических матчей")
            
            if not historical_matches:
                self.logger.warning("Нет доступных исторических данных")
                return False
            
            # Подключаемся к базе данных
            conn = await asyncpg.connect(self.config.DATABASE_URL)
            try:
                stored_count = 0
                for match in historical_matches:
                    parsed_match = api_client.parse_match_data(match)
                    if await self._store_match(conn, parsed_match):
                        stored_count += 1
                
                self.logger.success(f"Сохранено {stored_count} матчей в базу данных")
                return True
                
            finally:
                await conn.close()
    
    async def _store_match(self, conn, match_data: Dict[str, Any]) -> bool:
        """Сохранение одного матча в базу данных"""
        try:
            # Проверяем, что у нас есть необходимые данные
            if not match_data.get('home_team') or not match_data.get('away_team'):
                return False
            
            # Проверяем, существует ли уже такой матч
            existing = await conn.fetchrow(
                """SELECT id FROM matches 
                   WHERE home_team = $1 AND away_team = $2 
                   AND start_time = $3""",
                match_data.get('home_team'),
                match_data.get('away_team'), 
                match_data.get('start_time')
            )
            
            if existing:
                return False  # Матч уже существует
            
            # Вставляем новый матч
            await conn.execute(
                """INSERT INTO matches 
                   (home_team, away_team, home_score, away_score, 
                    start_time, match_date, league, status, match_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                match_data.get('home_team'),
                match_data.get('away_team'),
                match_data.get('home_score'),
                match_data.get('away_score'),
                match_data.get('start_time'),
                match_data.get('start_time'),  # match_date = start_time
                match_data.get('league'),
                'finished',
                match_data.get('id')
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения матча: {e}")
            return False

async def main():
    """Основная функция для сбора данных"""
    config = Config()
    collector = DataCollector(config)
    
    # Собираем данные за последние 7 дней
    success = await collector.collect_and_store_historical_data(7)
    
    if success:
        print("✅ Данные успешно собраны и сохранены")
    else:
        print("❌ Ошибка при сборе данных")

if __name__ == "__main__":
    asyncio.run(main())