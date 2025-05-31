"""
Анализатор тиков для live матчей с скользящими дельтами
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import numpy as np

from logger import BetBogLogger
from config import Config


@dataclass
class TickData:
    """Данные одного тика"""
    timestamp: datetime
    minute: int
    home_score: int
    away_score: int
    attacks_home: int
    attacks_away: int
    shots_home: int
    shots_away: int
    dangerous_attacks_home: int
    dangerous_attacks_away: int
    possession_home: float
    possession_away: float
    corners_home: int
    corners_away: int
    
    def get_metric_value(self, metric_name: str) -> float:
        """Получить значение метрики по имени"""
        metric_map = {
            'total_attacks': self.attacks_home + self.attacks_away,
            'total_shots': self.shots_home + self.shots_away,
            'total_dangerous': self.dangerous_attacks_home + self.dangerous_attacks_away,
            'total_corners': self.corners_home + self.corners_away,
            'total_goals': self.home_score + self.away_score,
            'attacks_home': self.attacks_home,
            'attacks_away': self.attacks_away,
            'shots_home': self.shots_home,
            'shots_away': self.shots_away,
            'possession_home': self.possession_home,
            'possession_away': self.possession_away
        }
        return metric_map.get(metric_name, 0.0)


@dataclass
class TickDelta:
    """Дельта между тиками"""
    metric_name: str
    delta_value: float
    tick_interval: int
    timestamp: datetime


@dataclass
class MovingAverage:
    """Скользящее среднее дельт"""
    metric_name: str
    window_size: int
    current_average: float
    deltas_history: deque
    confidence: float  # Уверенность на основе количества данных
    trend: str  # "rising", "falling", "stable"


class TickAnalyzer:
    """Анализатор тиков с настраиваемыми параметрами"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = BetBogLogger("TICK_ANALYZER", config.LOG_FILE if config.LOG_TO_FILE else None)
        
        # Настраиваемые параметры
        self.tick_interval = getattr(config, "TICK_INTERVAL", 60)  # секунды
        self.tick_window_size = getattr(config, "TICK_WINDOW_SIZE", 3)  # количество тиков для скользящего среднего
        self.max_ticks_history = getattr(config, "MAX_TICKS_HISTORY", 50)  # максимум тиков в истории
        
        # Метрики для анализа
        self.tracked_metrics = [
            'total_attacks',
            'total_shots', 
            'total_dangerous',
            'total_corners',
            'total_goals',
            'attacks_home',
            'attacks_away',
            'shots_home',
            'shots_away'
        ]
        
        # Хранилища данных для каждого матча
        self.match_ticks: Dict[str, deque] = {}  # match_id -> deque of TickData
        self.match_deltas: Dict[str, Dict[str, deque]] = {}  # match_id -> metric -> deque of deltas
        self.match_moving_averages: Dict[str, Dict[str, MovingAverage]] = {}  # match_id -> metric -> MovingAverage
        
    def initialize_match(self, match_id: str):
        """Инициализация хранилищ для нового матча"""
        if match_id not in self.match_ticks:
            self.match_ticks[match_id] = deque(maxlen=self.max_ticks_history)
            self.match_deltas[match_id] = {}
            self.match_moving_averages[match_id] = {}
            
            for metric in self.tracked_metrics:
                self.match_deltas[match_id][metric] = deque(maxlen=self.tick_window_size * 2)
                self.match_moving_averages[match_id][metric] = MovingAverage(
                    metric_name=metric,
                    window_size=self.tick_window_size,
                    current_average=0.0,
                    deltas_history=deque(maxlen=self.tick_window_size),
                    confidence=0.0,
                    trend="stable"
                )
            
            self.logger.info(f"Инициализирован анализ тиков для матча {match_id}")
    
    def add_tick(self, match_id: str, match_data: Dict[str, Any]) -> bool:
        """Добавить новый тик для матча"""
        self.initialize_match(match_id)
        
        try:
            # Создаем объект тика
            tick = TickData(
                timestamp=datetime.now(),
                minute=match_data.get('minute', 0),
                home_score=match_data.get('home_score', 0),
                away_score=match_data.get('away_score', 0),
                attacks_home=match_data.get('attacks_home', 0),
                attacks_away=match_data.get('attacks_away', 0),
                shots_home=match_data.get('shots_home', 0),
                shots_away=match_data.get('shots_away', 0),
                dangerous_attacks_home=match_data.get('dangerous_attacks_home', 0),
                dangerous_attacks_away=match_data.get('dangerous_attacks_away', 0),
                possession_home=match_data.get('possession_home', 50.0),
                possession_away=match_data.get('possession_away', 50.0),
                corners_home=match_data.get('corners_home', 0),
                corners_away=match_data.get('corners_away', 0)
            )
            
            # Проверяем временной интервал
            if self.match_ticks[match_id]:
                last_tick = self.match_ticks[match_id][-1]
                time_diff = (tick.timestamp - last_tick.timestamp).total_seconds()
                
                if time_diff < self.tick_interval:
                    return False  # Слишком рано для нового тика
            
            # Добавляем тик
            self.match_ticks[match_id].append(tick)
            
            # Вычисляем дельты если есть предыдущий тик
            if len(self.match_ticks[match_id]) >= 2:
                self._calculate_deltas(match_id, tick)
                self._update_moving_averages(match_id)
            
            self.logger.debug(f"Добавлен тик для матча {match_id}, минута {tick.minute}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка добавления тика для матча {match_id}: {e}")
            return False
    
    def _calculate_deltas(self, match_id: str, current_tick: TickData):
        """Вычислить дельты между текущим и предыдущим тиком"""
        if len(self.match_ticks[match_id]) < 2:
            return
            
        previous_tick = self.match_ticks[match_id][-2]
        
        for metric in self.tracked_metrics:
            current_value = current_tick.get_metric_value(metric)
            previous_value = previous_tick.get_metric_value(metric)
            delta = current_value - previous_value
            
            # Создаем объект дельты
            tick_delta = TickDelta(
                metric_name=metric,
                delta_value=delta,
                tick_interval=self.tick_interval,
                timestamp=current_tick.timestamp
            )
            
            # Добавляем в историю дельт
            self.match_deltas[match_id][metric].append(tick_delta)
            self.logger.debug(f"Дельта {metric}: {delta} для матча {match_id}")
    
    def _update_moving_averages(self, match_id: str):
        """Обновить скользящие средние для всех метрик"""
        for metric in self.tracked_metrics:
            deltas = self.match_deltas[match_id][metric]
            moving_avg = self.match_moving_averages[match_id][metric]
            
            if len(deltas) >= 1:  # Начинаем анализ с первой дельты
                # Берем последние N дельт (или все, если их меньше N)
                recent_deltas = list(deltas)[-self.tick_window_size:]
                delta_values = [d.delta_value for d in recent_deltas]
                
                # Просто суммируем дельты без деления (как вы просили)
                moving_avg.current_average = sum(delta_values)
                # Пересоздаем deque с новыми значениями
                moving_avg.deltas_history = deque(delta_values, maxlen=self.tick_window_size)
                moving_avg.confidence = min(len(deltas) / self.tick_window_size, 1.0)
                
                # Отладочная информация
                self.logger.debug(f"Обновлены средние для {metric}: дельты={delta_values}, сумма={moving_avg.current_average}")
                
                # Определяем тренд на основе последних дельт
                if len(delta_values) >= 2:
                    if delta_values[-1] > delta_values[-2]:
                        moving_avg.trend = "rising"
                    elif delta_values[-1] < delta_values[-2]:
                        moving_avg.trend = "falling"
                    else:
                        moving_avg.trend = "stable"
                elif len(delta_values) == 1:
                    # Для одной дельты определяем тренд по знаку
                    if delta_values[0] > 0:
                        moving_avg.trend = "rising"
                    elif delta_values[0] < 0:
                        moving_avg.trend = "falling"
                    else:
                        moving_avg.trend = "stable"
    
    def get_moving_average(self, match_id: str, metric_name: str) -> Optional[MovingAverage]:
        """Получить скользящее среднее для метрики"""
        if match_id in self.match_moving_averages:
            return self.match_moving_averages[match_id].get(metric_name)
        return None
    
    def get_all_moving_averages(self, match_id: str) -> Dict[str, MovingAverage]:
        """Получить все скользящие средние для матча"""
        return self.match_moving_averages.get(match_id, {})
    
    def get_trend_analysis(self, match_id: str) -> Dict[str, Any]:
        """Получить анализ трендов для матча"""
        if match_id not in self.match_moving_averages:
            return {"status": "no_data"}
        
        analysis = {
            "status": "success",
            "match_id": match_id,
            "tick_count": len(self.match_ticks.get(match_id, [])),
            "metrics": {}
        }
        
        for metric, moving_avg in self.match_moving_averages[match_id].items():
            if moving_avg.confidence > 0.5:  # Достаточно данных для анализа
                analysis["metrics"][metric] = {
                    "current_average": moving_avg.current_average,
                    "trend": moving_avg.trend,
                    "confidence": moving_avg.confidence,
                    "strength": abs(moving_avg.current_average)  # Сила тренда
                }
        
        return analysis
    
    def detect_momentum_shifts(self, match_id: str) -> List[Dict[str, Any]]:
        """Обнаружить смены моментума в матче"""
        momentum_shifts = []
        
        if match_id not in self.match_moving_averages:
            return momentum_shifts
        
        # Анализируем ключевые метрики на предмет резких изменений
        key_metrics = ['total_attacks', 'total_shots', 'total_dangerous']
        
        for metric in key_metrics:
            moving_avg = self.match_moving_averages[match_id].get(metric)
            if not moving_avg or moving_avg.confidence < 0.7:
                continue
            
            # Проверяем резкое изменение тренда
            if len(moving_avg.deltas_history) >= 3:
                recent_deltas = list(moving_avg.deltas_history)
                
                # Смена с падающего на растущий тренд
                if (recent_deltas[-3] < 0 and recent_deltas[-2] < 0 and 
                    recent_deltas[-1] > recent_deltas[-2] * 1.5):
                    momentum_shifts.append({
                        "type": "momentum_gain",
                        "metric": metric,
                        "strength": abs(recent_deltas[-1]),
                        "confidence": moving_avg.confidence
                    })
                
                # Смена с растущего на падающий тренд
                elif (recent_deltas[-3] > 0 and recent_deltas[-2] > 0 and 
                      recent_deltas[-1] < recent_deltas[-2] * 0.5):
                    momentum_shifts.append({
                        "type": "momentum_loss",
                        "metric": metric,
                        "strength": abs(recent_deltas[-1] - recent_deltas[-2]),
                        "confidence": moving_avg.confidence
                    })
        
        return momentum_shifts
    
    def cleanup_old_matches(self, hours_old: int = 24):
        """Очистка данных старых матчей"""
        cutoff_time = datetime.now() - timedelta(hours=hours_old)
        matches_to_remove = []
        
        for match_id, ticks in self.match_ticks.items():
            if ticks and ticks[-1].timestamp < cutoff_time:
                matches_to_remove.append(match_id)
        
        for match_id in matches_to_remove:
            self.match_ticks.pop(match_id, None)
            self.match_deltas.pop(match_id, None)
            self.match_moving_averages.pop(match_id, None)
            self.logger.info(f"Очищены данные для старого матча {match_id}")
    
    def clear_match_data(self, match_id: str):
        """Очистка данных тиков для завершенного матча"""
        cleared = False
        
        if match_id in self.match_ticks:
            del self.match_ticks[match_id]
            cleared = True
        
        if match_id in self.match_deltas:
            del self.match_deltas[match_id]
            cleared = True
            
        if match_id in self.match_moving_averages:
            del self.match_moving_averages[match_id]
            cleared = True
        
        if cleared:
            self.logger.info(f"Очищены все данные тиков для матча {match_id}")


# Функция для тестирования
async def test_tick_analyzer():
    """Тестирование анализатора тиков"""
    config = Config()
    analyzer = TickAnalyzer(config)
    
    # Симуляция тиков матча
    match_id = "test_match_123"
    
    # Тик 0 (начальное состояние)
    match_data_0 = {
        'minute': 10,
        'attacks_home': 13, 'attacks_away': 8,
        'shots_home': 4, 'shots_away': 2,
        'dangerous_attacks_home': 3, 'dangerous_attacks_away': 1
    }
    analyzer.add_tick(match_id, match_data_0)
    
    # Тик 1 (через минуту)
    await asyncio.sleep(1)  # Имитируем прошедшее время
    match_data_1 = {
        'minute': 11,
        'attacks_home': 15, 'attacks_away': 10,  # дельта +2, +2
        'shots_home': 5, 'shots_away': 3,       # дельта +1, +1
        'dangerous_attacks_home': 4, 'dangerous_attacks_away': 2  # дельта +1, +1
    }
    analyzer.add_tick(match_id, match_data_1)
    
    # Тик 2
    await asyncio.sleep(1)
    match_data_2 = {
        'minute': 12,
        'attacks_home': 18, 'attacks_away': 13,  # дельта +3, +3
        'shots_home': 7, 'shots_away': 4,       # дельта +2, +1
        'dangerous_attacks_home': 6, 'dangerous_attacks_away': 3  # дельта +2, +1
    }
    analyzer.add_tick(match_id, match_data_2)
    
    # Тик 3
    await asyncio.sleep(1)
    match_data_3 = {
        'minute': 13,
        'attacks_home': 19, 'attacks_away': 16,  # дельта +1, +3
        'shots_home': 8, 'shots_away': 5,       # дельта +1, +1
        'dangerous_attacks_home': 7, 'dangerous_attacks_away': 4  # дельта +1, +1
    }
    analyzer.add_tick(match_id, match_data_3)
    
    # Получаем анализ
    trend_analysis = analyzer.get_trend_analysis(match_id)
    print("Анализ трендов:", trend_analysis)
    
    # Получаем скользящее среднее для атак
    total_attacks_avg = analyzer.get_moving_average(match_id, 'total_attacks')
    if total_attacks_avg:
        print(f"Скользящее среднее для общих атак: {total_attacks_avg.current_average}")
        print(f"Тренд: {total_attacks_avg.trend}")


if __name__ == "__main__":
    asyncio.run(test_tick_analyzer())