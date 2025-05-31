from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from typing import Optional, Dict, Any
import json

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String, unique=True, index=True)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    league = Column(String)
    start_time = Column(DateTime)
    status = Column(String)  # live, finished, postponed
    minute = Column(Integer)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    stats = Column(JSON)  # Raw match statistics
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    signals = relationship("Signal", back_populates="match")
    metrics = relationship("MatchMetrics", back_populates="match")

class MatchMetrics(Base):
    __tablename__ = "match_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    minute = Column(Integer, nullable=False)
    
    # Derived metrics
    dxg_home = Column(Float)
    dxg_away = Column(Float)
    gradient_home = Column(Float)
    gradient_away = Column(Float)
    wave_amplitude = Column(Float)
    tiredness_home = Column(Float)
    tiredness_away = Column(Float)
    momentum_home = Column(Float)
    momentum_away = Column(Float)
    stability_home = Column(Float)
    stability_away = Column(Float)
    shots_per_attack_home = Column(Float)
    shots_per_attack_away = Column(Float)
    
    # Raw stats for calculation
    shots_home = Column(Integer, default=0)
    shots_away = Column(Integer, default=0)
    attacks_home = Column(Integer, default=0)
    attacks_away = Column(Integer, default=0)
    possession_home = Column(Float)
    possession_away = Column(Float)
    corners_home = Column(Integer, default=0)
    corners_away = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    match = relationship("Match", back_populates="metrics")

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    strategy_name = Column(String, nullable=False)
    signal_type = Column(String)  # bet_type like "over_1.5", "btts"
    confidence = Column(Float, nullable=False)
    threshold_used = Column(Float)
    trigger_minute = Column(Integer)
    prediction = Column(String)  # The actual prediction
    odds = Column(Float)
    
    # Result tracking
    result = Column(String)  # win, loss, push, pending
    profit_loss = Column(Float, default=0.0)
    stake = Column(Float, default=1.0)
    
    # Metadata
    trigger_metrics = Column(JSON)  # Metrics that triggered this signal
    strategy_config = Column(JSON)  # Configuration used for this signal
    
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime)
    
    # Relationships
    match = relationship("Match", back_populates="signals")

class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String, unique=True, nullable=False)
    config = Column(JSON, nullable=False)
    
    # Performance tracking
    total_signals = Column(Integer, default=0)
    winning_signals = Column(Integer, default=0)
    total_profit = Column(Float, default=0.0)
    roi = Column(Float, default=0.0)
    
    # ML optimization
    last_optimized = Column(DateTime)
    optimization_score = Column(Float)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class MLModel(Base):
    __tablename__ = "ml_models"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    model_data = Column(Text)  # Serialized model
    features = Column(JSON)  # Feature names and importance
    performance_metrics = Column(JSON)  # Accuracy, precision, recall, etc.
    training_samples = Column(Integer)
    
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, nullable=False)  # INFO, WARNING, ERROR
    category = Column(String)  # API, STRATEGY, ML, BOT
    message = Column(Text, nullable=False)
    details = Column(JSON)
    
    created_at = Column(DateTime, default=func.now())
