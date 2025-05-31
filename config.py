import os
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Config:
    # Bot Configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "7228733029:AAFVPzKHUSRidigzYSy_IANt8rWzjjPBDPA")
    API_TOKEN: str = os.getenv("API_TOKEN", "219769-EKswpZvLvKyoxD")
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/betbog")
    
    # API Configuration
    BASE_URL: str = "https://api.b365api.com/v3"
    LIVE_ENDPOINT: str = "/events/inplay"
    HISTORY_ENDPOINT: str = "/events/ended"
    
    # Strategy Configuration
    def get_default_thresholds(self) -> Dict[str, Dict[str, float]]:
        return {
            "dxg_spike": {
                "threshold": 0.15,
                "min_confidence": 0.7,
                "lookback_minutes": 10
            },
            "momentum_shift": {
                "threshold": 0.25,
                "stability_factor": 0.8,
                "min_shots": 3
            },
            "tiredness_advantage": {
                "threshold": 0.3,
                "gradient_factor": 0.2,
                "wave_amplitude": 0.1
            }
        }
    
    # ML Configuration
    ML_UPDATE_INTERVAL: int = 24  # hours
    MIN_SAMPLES_FOR_LEARNING: int = 50
    FEATURE_IMPORTANCE_THRESHOLD: float = 0.1
    
    # Monitoring Configuration
    MATCH_CHECK_INTERVAL: int = 60  # seconds
    RESULT_CHECK_INTERVAL: int = 300  # seconds
    MAX_CONCURRENT_MATCHES: int = 20
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = True
    LOG_FILE: str = "betbog.log"
    
    # Настройки анализатора тиков
    TICK_INTERVAL: int = 60  # интервал между тиками в секундах
    TICK_WINDOW_SIZE: int = 3  # количество тиков для скользящего среднего
    MAX_TICKS_HISTORY: int = 50  # максимум тиков в истории матча
