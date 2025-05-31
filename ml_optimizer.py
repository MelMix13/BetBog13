import json
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
from logger import BetBogLogger

class MLOptimizer:
    """Simple statistical optimizer for betting strategies without ML dependencies"""
    
    def __init__(self):
        self.logger = BetBogLogger("OPTIMIZER")
        self.strategy_stats: Dict[str, Dict] = {}
        self.threshold_history: Dict[str, List[Dict]] = {}
        self.performance_history: Dict[str, List[Dict]] = {}
        
    async def optimize_strategy_thresholds(self, 
                                         strategy_name: str,
                                         historical_signals: List[Dict[str, Any]],
                                         min_samples: int = 30) -> Dict[str, float]:
        """Optimize strategy thresholds using statistical analysis"""
        
        if len(historical_signals) < min_samples:
            self.logger.warning(f"Not enough samples for {strategy_name}: {len(historical_signals)}")
            return {}
        
        try:
            # Analyze historical performance
            win_signals = [s for s in historical_signals if s.get('result') == 'win']
            loss_signals = [s for s in historical_signals if s.get('result') == 'loss']
            
            if not win_signals:
                self.logger.warning(f"No winning signals found for {strategy_name}")
                return {}
            
            # Calculate optimal thresholds based on winning patterns
            optimal_thresholds = self._calculate_statistical_thresholds(
                win_signals, loss_signals, strategy_name
            )
            
            # Store performance data
            self.strategy_stats[strategy_name] = {
                'win_rate': len(win_signals) / len(historical_signals),
                'total_signals': len(historical_signals),
                'avg_confidence_wins': statistics.mean([s.get('confidence', 0.5) for s in win_signals]),
                'avg_confidence_losses': statistics.mean([s.get('confidence', 0.5) for s in loss_signals]) if loss_signals else 0,
                'last_optimized': datetime.now().isoformat()
            }
            
            self.logger.success(f"Optimized {strategy_name}: {optimal_thresholds}")
            return optimal_thresholds
            
        except Exception as e:
            self.logger.error(f"Error optimizing {strategy_name}: {str(e)}")
            return {}
    
    def _prepare_training_data(self, signals: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Prepare training data from historical signals"""
        
        features = []
        labels = []
        
        for signal in signals:
            if signal.get('result') in ['win', 'loss'] and signal.get('trigger_metrics'):
                # Extract features from trigger metrics
                metrics = signal['trigger_metrics']
                confidence = signal.get('confidence', 0.5)
                minute = signal.get('trigger_minute', 45)
                threshold = signal.get('threshold_used', 0.0)
                
                feature_row = [
                    metrics.get('total_dxg', 0.0),
                    metrics.get('dxg_imbalance', 0.0),
                    metrics.get('momentum_home', 0.0),
                    metrics.get('momentum_away', 0.0),
                    metrics.get('momentum_diff', 0.0),
                    metrics.get('tiredness_home', 0.0),
                    metrics.get('tiredness_away', 0.0),
                    metrics.get('tiredness_diff', 0.0),
                    metrics.get('gradient_home', 0.0),
                    metrics.get('gradient_away', 0.0),
                    metrics.get('wave_amplitude', 0.0),
                    metrics.get('stability_home', 0.0),
                    metrics.get('stability_away', 0.0),
                    metrics.get('spa_home', 0.0),
                    metrics.get('spa_away', 0.0),
                    confidence,
                    minute,
                    threshold
                ]
                
                features.append(feature_row)
                labels.append(1 if signal['result'] == 'win' else 0)
        
        feature_names = [
            'total_dxg', 'dxg_imbalance', 'momentum_home', 'momentum_away',
            'momentum_diff', 'tiredness_home', 'tiredness_away', 'tiredness_diff',
            'gradient_home', 'gradient_away', 'wave_amplitude', 'stability_home',
            'stability_away', 'spa_home', 'spa_away', 'confidence', 'minute', 'threshold'
        ]
        
        return np.array(features), np.array(labels), feature_names
    
    async def _train_optimize_model(self, X: np.ndarray, y: np.ndarray, strategy_name: str) -> Tuple[Any, Dict]:
        """Train and optimize ML model using grid search"""
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        self.scalers[strategy_name] = scaler
        
        # Define models and parameters for grid search
        models_params = {
            'random_forest': {
                'model': RandomForestClassifier(random_state=42),
                'params': {
                    'n_estimators': [100, 200],
                    'max_depth': [5, 10, None],
                    'min_samples_split': [2, 5],
                    'min_samples_leaf': [1, 2]
                }
            },
            'gradient_boosting': {
                'model': GradientBoostingClassifier(random_state=42),
                'params': {
                    'n_estimators': [100, 200],
                    'max_depth': [3, 5],
                    'learning_rate': [0.1, 0.2],
                    'min_samples_split': [2, 5]
                }
            }
        }
        
        best_score = 0
        best_model = None
        best_params = {}
        
        for model_name, model_config in models_params.items():
            self.logger.info(f"Training {model_name} for {strategy_name}")
            
            # Grid search
            grid_search = GridSearchCV(
                model_config['model'],
                model_config['params'],
                cv=5,
                scoring='f1',
                n_jobs=-1
            )
            
            grid_search.fit(X_train_scaled, y_train)
            
            # Evaluate on test set
            y_pred = grid_search.best_estimator_.predict(X_test_scaled)
            f1 = f1_score(y_test, y_pred)
            
            self.logger.info(f"{model_name} F1 score: {f1:.3f}")
            
            if f1 > best_score:
                best_score = f1
                best_model = grid_search.best_estimator_
                best_params = grid_search.best_params_
        
        # Store performance metrics
        y_pred_final = best_model.predict(X_test_scaled)
        performance = {
            'accuracy': accuracy_score(y_test, y_pred_final),
            'precision': precision_score(y_test, y_pred_final),
            'recall': recall_score(y_test, y_pred_final),
            'f1': f1_score(y_test, y_pred_final),
            'timestamp': datetime.now().isoformat()
        }
        
        if strategy_name not in self.performance_history:
            self.performance_history[strategy_name] = []
        self.performance_history[strategy_name].append(performance)
        
        self.logger.success(f"Best model for {strategy_name}: F1={best_score:.3f}")
        return best_model, best_params
    
    def _calculate_optimal_thresholds(self, 
                                    model: Any,
                                    X: np.ndarray, 
                                    y: np.ndarray,
                                    feature_names: List[str],
                                    strategy_name: str) -> Dict[str, float]:
        """Calculate optimal thresholds using model predictions"""
        
        # Scale features
        scaler = self.scalers.get(strategy_name)
        if scaler:
            X_scaled = scaler.transform(X)
        else:
            X_scaled = X
        
        # Get prediction probabilities
        try:
            probabilities = model.predict_proba(X_scaled)[:, 1]
        except:
            # Fallback to decision function for models without predict_proba
            decision_scores = model.decision_function(X_scaled)
            probabilities = 1 / (1 + np.exp(-decision_scores))  # Sigmoid
        
        # Find optimal threshold based on F1 score
        thresholds = np.arange(0.1, 1.0, 0.05)
        best_threshold = 0.5
        best_f1 = 0
        
        for threshold in thresholds:
            predictions = (probabilities >= threshold).astype(int)
            if len(np.unique(predictions)) > 1:  # Avoid single class predictions
                f1 = f1_score(y, predictions)
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = threshold
        
        # Calculate feature-based thresholds
        feature_thresholds = {}
        
        # Get feature importance and optimize key features
        importance = model.feature_importances_
        important_features = [
            feature_names[i] for i in range(len(feature_names))
            if importance[i] > 0.05  # Only features with >5% importance
        ]
        
        for feature_name in important_features:
            if 'threshold' in feature_name:
                continue  # Skip threshold features
                
            feature_idx = feature_names.index(feature_name)
            feature_values = X[:, feature_idx]
            
            # Find optimal threshold for this feature
            feature_threshold = self._optimize_feature_threshold(
                feature_values, y, probabilities
            )
            
            if feature_threshold is not None:
                feature_thresholds[feature_name] = feature_threshold
        
        # Add general confidence threshold
        feature_thresholds['min_confidence'] = best_threshold
        
        return feature_thresholds
    
    def _optimize_feature_threshold(self, 
                                  feature_values: np.ndarray,
                                  labels: np.ndarray,
                                  probabilities: np.ndarray) -> Optional[float]:
        """Optimize threshold for a specific feature"""
        
        if len(np.unique(feature_values)) < 3:
            return None
        
        # Test different percentiles as thresholds
        percentiles = [50, 60, 70, 75, 80, 85, 90]
        best_score = 0
        best_threshold = None
        
        for percentile in percentiles:
            threshold = np.percentile(feature_values, percentile)
            
            # Calculate performance when feature is above threshold
            mask = feature_values >= threshold
            if np.sum(mask) < 5:  # Need minimum samples
                continue
            
            # Use probabilities to make final predictions
            subset_probs = probabilities[mask]
            subset_labels = labels[mask]
            
            if len(np.unique(subset_labels)) > 1:
                # Calculate precision for signals above this threshold
                predictions = (subset_probs >= 0.5).astype(int)
                if np.sum(predictions) > 0:
                    precision = precision_score(subset_labels, predictions)
                    if precision > best_score:
                        best_score = precision
                        best_threshold = threshold
        
        return best_threshold
    
    def predict_signal_success(self, 
                             strategy_name: str,
                             trigger_metrics: Dict[str, float],
                             confidence: float,
                             minute: int,
                             threshold: float) -> Tuple[float, str]:
        """Predict probability of signal success"""
        
        model = self.models.get(strategy_name)
        scaler = self.scalers.get(strategy_name)
        
        if not model or not scaler:
            return confidence, "No ML model available"
        
        try:
            # Prepare feature vector
            feature_vector = np.array([[
                trigger_metrics.get('total_dxg', 0.0),
                trigger_metrics.get('dxg_imbalance', 0.0),
                trigger_metrics.get('momentum_home', 0.0),
                trigger_metrics.get('momentum_away', 0.0),
                trigger_metrics.get('momentum_diff', 0.0),
                trigger_metrics.get('tiredness_home', 0.0),
                trigger_metrics.get('tiredness_away', 0.0),
                trigger_metrics.get('tiredness_diff', 0.0),
                trigger_metrics.get('gradient_home', 0.0),
                trigger_metrics.get('gradient_away', 0.0),
                trigger_metrics.get('wave_amplitude', 0.0),
                trigger_metrics.get('stability_home', 0.0),
                trigger_metrics.get('stability_away', 0.0),
                trigger_metrics.get('spa_home', 0.0),
                trigger_metrics.get('spa_away', 0.0),
                confidence,
                minute,
                threshold
            ]])
            
            # Scale and predict
            feature_vector_scaled = scaler.transform(feature_vector)
            
            try:
                ml_probability = model.predict_proba(feature_vector_scaled)[0, 1]
            except:
                decision_score = model.decision_function(feature_vector_scaled)[0]
                ml_probability = 1 / (1 + np.exp(-decision_score))
            
            # Combine with original confidence (weighted average)
            combined_confidence = 0.7 * ml_probability + 0.3 * confidence
            
            explanation = f"ML prediction: {ml_probability:.3f}, Combined: {combined_confidence:.3f}"
            
            return combined_confidence, explanation
            
        except Exception as e:
            self.logger.error(f"Error in ML prediction for {strategy_name}: {str(e)}")
            return confidence, f"ML prediction failed: {str(e)}"
    
    def get_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """Get performance metrics for a strategy"""
        
        history = self.performance_history.get(strategy_name, [])
        if not history:
            return {}
        
        latest = history[-1]
        
        # Calculate improvement over time
        if len(history) > 1:
            first = history[0]
            improvement = {
                'f1_improvement': latest['f1'] - first['f1'],
                'accuracy_improvement': latest['accuracy'] - first['accuracy']
            }
        else:
            improvement = {'f1_improvement': 0, 'accuracy_improvement': 0}
        
        return {
            'latest_performance': latest,
            'improvement': improvement,
            'model_available': strategy_name in self.models,
            'feature_importance': self.feature_importance.get(strategy_name, {}),
            'training_history_length': len(history)
        }
    
    def save_models(self, filepath: str):
        """Save trained models to file"""
        try:
            model_data = {
                'models': {},
                'scalers': {},
                'feature_importance': self.feature_importance,
                'performance_history': self.performance_history,
                'timestamp': datetime.now().isoformat()
            }
            
            # Serialize models
            for name, model in self.models.items():
                model_data['models'][name] = pickle.dumps(model).hex()
            
            # Serialize scalers
            for name, scaler in self.scalers.items():
                model_data['scalers'][name] = pickle.dumps(scaler).hex()
            
            with open(filepath, 'w') as f:
                json.dump(model_data, f, indent=2)
            
            self.logger.success(f"Models saved to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error saving models: {str(e)}")
    
    def load_models(self, filepath: str):
        """Load trained models from file"""
        try:
            with open(filepath, 'r') as f:
                model_data = json.load(f)
            
            # Deserialize models
            for name, model_hex in model_data.get('models', {}).items():
                self.models[name] = pickle.loads(bytes.fromhex(model_hex))
            
            # Deserialize scalers
            for name, scaler_hex in model_data.get('scalers', {}).items():
                self.scalers[name] = pickle.loads(bytes.fromhex(scaler_hex))
            
            self.feature_importance = model_data.get('feature_importance', {})
            self.performance_history = model_data.get('performance_history', {})
            
            self.logger.success(f"Models loaded from {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error loading models: {str(e)}")
