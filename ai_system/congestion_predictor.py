#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prédicteur de congestion IA - VERSION CORRIGÉE
Utilise les VRAIES données du collecteur
"""

import numpy as np
import pandas as pd
import joblib
import json
import os
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import logging
import warnings
warnings.filterwarnings('ignore')

class CongestionPredictor:
    """
    Système de prédiction de congestion basé sur l'IA
    Utilise les données RÉELLES collectées par SDNDataCollector
    """
    
    def __init__(self, model_type='random_forest'):
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        
        # Configuration
        self.prediction_threshold = 0.7
        self.retrain_interval_hours = 24
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"🧠 Prédicteur de congestion initialisé (modèle: {model_type})")
        
        # Charger ou créer le modèle
        self._load_or_create_model()
    
    def _load_or_create_model(self):
        """Charge un modèle existant ou en crée un nouveau"""
        model_filename = f"congestion_model_{self.model_type}.pkl"
        scaler_filename = "congestion_scaler.pkl"
        
        try:
            if os.path.exists(model_filename) and os.path.exists(scaler_filename):
                self.model = joblib.load(model_filename)
                self.scaler = joblib.load(scaler_filename)
                self.logger.info("✅ Modèle IA chargé depuis fichiers")
                
                # Charger les noms de features
                feature_file = "model_features.json"
                if os.path.exists(feature_file):
                    with open(feature_file, 'r') as f:
                        data = json.load(f)
                        self.feature_names = data.get('feature_names', [])
                
            else:
                self.logger.warning("⚠️ Modèle non trouvé. Création d'un nouveau modèle...")
                self._create_and_train_initial_model()
                
        except Exception as e:
            self.logger.error(f"❌ Erreur chargement modèle: {e}")
            self._create_and_train_initial_model()
    
    def _create_and_train_initial_model(self):
        """Crée et entraîne un modèle initial"""
        self.logger.info("🎓 Entraînement du modèle initial...")
        
        # Générer des données d'entraînement réalistes
        X_train, y_train = self._generate_realistic_training_data()
        
        if len(X_train) == 0:
            self.logger.error("❌ Pas assez de données pour l'entraînement")
            return
        
        # Normaliser les données
        X_train_scaled = self.scaler.fit_transform(X_train)
        
        # Créer le modèle
        if self.model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            )
        elif self.model_type == 'gradient_boosting':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
        elif self.model_type == 'neural_network':
            self.model = MLPClassifier(
                hidden_layer_sizes=(50, 25),
                activation='relu',
                max_iter=1000,
                random_state=42
            )
        else:
            self.model = RandomForestClassifier(n_estimators=50, random_state=42)
        
        # Entraîner le modèle
        self.model.fit(X_train_scaled, y_train)
        
        # Sauvegarder
        self._save_model()
        
        # Générer les noms de features
        self.feature_names = self._generate_feature_names(X_train.shape[1])
        
        # Sauvegarder les noms de features
        with open("model_features.json", 'w') as f:
            json.dump({'feature_names': self.feature_names}, f)
        
        # Évaluer
        accuracy = self.model.score(X_train_scaled, y_train)
        self.logger.info(f"✅ Modèle entraîné - Accuracy: {accuracy:.2%}")
        self.logger.info(f"✅ Features: {len(self.feature_names)} ({', '.join(self.feature_names[:3])}...)")
    
    def _generate_realistic_training_data(self, n_samples=1000):
        """Génère des données d'entraînement réalistes"""
        np.random.seed(42)
        
        # 10 features réalistes (comme dans l'extraction réelle)
        n_features = 10
        
        X = np.zeros((n_samples, n_features))
        
        # Simuler différents patterns de trafic
        for i in range(n_samples):
            # Pattern aléatoire pour chaque échantillon
            pattern_type = np.random.choice(['low', 'normal', 'high', 'burst'])
            
            if pattern_type == 'low':
                # Faible trafic
                X[i, 0] = np.random.uniform(0.0, 0.2)   # bw_util
                X[i, 1] = np.random.uniform(0.0, 0.3)   # packet_rate
                X[i, 2] = np.random.uniform(0.0, 0.2)   # flow_count
                X[i, 3] = np.random.uniform(0.1, 0.3)   # latency
                X[i, 4] = np.random.uniform(0.0, 0.1)   # queue_occ
            
            elif pattern_type == 'normal':
                # Trafic normal
                X[i, 0] = np.random.uniform(0.3, 0.6)
                X[i, 1] = np.random.uniform(0.4, 0.7)
                X[i, 2] = np.random.uniform(0.3, 0.5)
                X[i, 3] = np.random.uniform(0.2, 0.4)
                X[i, 4] = np.random.uniform(0.1, 0.3)
            
            elif pattern_type == 'high':
                # Trafic élevé
                X[i, 0] = np.random.uniform(0.7, 0.9)
                X[i, 1] = np.random.uniform(0.8, 1.0)
                X[i, 2] = np.random.uniform(0.6, 0.9)
                X[i, 3] = np.random.uniform(0.5, 0.8)
                X[i, 4] = np.random.uniform(0.4, 0.7)
            
            elif pattern_type == 'burst':
                # Trafic en rafale
                X[i, 0] = np.random.uniform(0.8, 1.0)
                X[i, 1] = np.random.uniform(0.9, 1.0)
                X[i, 2] = np.random.uniform(0.2, 0.4)  # Peu de flows mais beaucoup de packets
                X[i, 3] = np.random.uniform(0.7, 1.0)
                X[i, 4] = np.random.uniform(0.6, 0.9)
            
            # Features dérivées
            X[i, 5] = X[i, 1] / max(X[i, 2], 0.1)  # packets/flow ratio
            X[i, 6] = np.random.uniform(0.0, 0.05)  # error rate
            X[i, 7] = X[i, 0] * 0.4 + X[i, 4] * 0.3 + np.random.uniform(0.0, 0.3)  # composite
            X[i, 8] = 1.0 if np.random.random() > 0.5 else 0.0  # peak hour
            X[i, 9] = np.random.random()  # minute factor
        
        # Labels: congestion si certaines combinaisons
        y = np.zeros(n_samples)
        
        # Règles de congestion réalistes
        congestion_rules = [
            (X[:, 0] > 0.8) & (X[:, 3] > 0.6),                    # Haute utilisation + haute latence
            (X[:, 0] > 0.7) & (X[:, 4] > 0.5),                    # Haute utilisation + queue pleine
            (X[:, 5] > 2.0) & (X[:, 0] > 0.6),                    # Ratio packets/flow élevé + utilisation
            (X[:, 0] > 0.85) | (X[:, 1] > 0.9) | (X[:, 3] > 0.8), # Très haute sur une métrique
        ]
        
        for rule in congestion_rules:
            y[rule] = 1
        
        # Ajouter du bruit
        noise = np.random.rand(n_samples) < 0.02
        y[noise] = 1 - y[noise]
        
        # Normaliser les features
        for col in range(n_features):
            if X[:, col].std() > 0:
                X[:, col] = (X[:, col] - X[:, col].mean()) / X[:, col].std()
        
        return X, y
    
    def _generate_feature_names(self, n_features):
        """Génère des noms de features descriptifs"""
        base_names = [
            'bw_utilization',
            'packet_rate', 
            'flow_count',
            'latency_ms',
            'queue_occupancy',
            'packets_per_flow',
            'error_rate',
            'composite_util',
            'peak_hour',
            'time_factor'
        ]
        
        return base_names[:n_features]
    
    def _save_model(self):
        """Sauvegarde le modèle et le scaler"""
        try:
            model_filename = f"congestion_model_{self.model_type}.pkl"
            scaler_filename = "congestion_scaler.pkl"
            
            joblib.dump(self.model, model_filename)
            joblib.dump(self.scaler, scaler_filename)
            
            self.logger.info(f"💾 Modèle sauvegardé: {model_filename}")
            
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde modèle: {e}")
    
    def _extract_features_from_data(self, data):
        """
        Extrait les VRAIES features à partir des données du collecteur
        """
        try:
            if not data or not isinstance(data, dict):
                self.logger.warning("⚠️ Données invalides pour extraction features")
                return None
            
            features = []
            
            # 1. Métriques principales depuis données réelles
            real_metrics = [
                ('bandwidth_utilization', 1.0),      # 0: bw_utilization
                ('packet_count', 1000000),          # 1: packet_rate (normalisé)
                ('flow_count', 100),                # 2: flow_count
                ('latency', 100),                   # 3: latency_ms
                ('queue_occupancy', 1.0),           # 4: queue_occupancy
            ]
            
            for i, (metric_name, max_val) in enumerate(real_metrics):
                value = data.get(metric_name, 0)
                normalized = min(value / max_val, 1.0) if max_val > 0 else 0
                features.append(normalized)
                
                # Log pour debug
                if i == 0:  # Pour bw_utilization
                    self.logger.debug(f"Feature {metric_name}: {value} → {normalized:.3f}")
            
            # 2. Features dérivées
            # packets_per_flow (ratio)
            packet_count = max(data.get('packet_count', 0), 0)
            flow_count = max(data.get('flow_count', 1), 1)
            packets_per_flow = min(packet_count / flow_count / 1000, 2.0)
            features.append(packets_per_flow)
            
            # error_rate
            error_rate = min(data.get('error_rate', 0), 0.1)
            features.append(error_rate * 10)  # Normalisé
            
            # composite_util (moyenne pondérée)
            bw_util = data.get('bandwidth_utilization', 0)
            port_util = data.get('port_utilization', 0)
            queue_occ = data.get('queue_occupancy', 0)
            composite = (bw_util * 0.5 + port_util * 0.3 + queue_occ * 0.2)
            features.append(composite)
            
            # 3. Features temporelles
            now = datetime.now()
            # peak_hour (9h-17h = 1.0, sinon 0.0)
            peak_hour = 1.0 if 9 <= now.hour <= 17 else 0.0
            features.append(peak_hour)
            
            # time_factor (minute dans l'heure)
            time_factor = now.minute / 60.0
            features.append(time_factor)
            
            # Log complet des features
            self.logger.debug(f"📊 Features extraites pour switch: {features}")
            
            # Vérification
            if len(features) != 10:
                self.logger.warning(f"⚠️ Nombre de features incorrect: {len(features)}")
                # Compléter avec des zéros si nécessaire
                while len(features) < 10:
                    features.append(0.0)
                features = features[:10]
            
            return np.array(features).reshape(1, -1)
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction features: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def predict_congestion(self, features):
        """
        Prédit la probabilité de congestion pour des features données
        """
        try:
            # Convertir en array numpy
            if isinstance(features, list):
                features = np.array(features).reshape(1, -1)
            
            # Vérifier la forme
            if features.ndim == 1:
                features = features.reshape(1, -1)
            
            # Vérifier les dimensions
            if features.shape[1] != 10:
                self.logger.warning(f"⚠️ Dimensions features: {features.shape}, attendu 10")
                # Ajuster si possible
                if features.shape[1] < 10:
                    padding = np.zeros((1, 10 - features.shape[1]))
                    features = np.hstack([features, padding])
                else:
                    features = features[:, :10]
            
            # Vérifier si le scaler est initialisé
            if not hasattr(self.scaler, 'n_features_in_'):
                self.logger.warning("⚠️ Scaler non initialisé, création d'un nouveau")
                dummy_data = np.random.randn(10, 10)
                self.scaler.fit(dummy_data)
            
            # Normaliser
            features_scaled = self.scaler.transform(features)
            
            # Prédiction
            if hasattr(self.model, 'predict_proba'):
                probability = self.model.predict_proba(features_scaled)[0][1]
            else:
                prediction = self.model.predict(features_scaled)[0]
                probability = 1.0 if prediction == 1 else 0.0
            
            # Déterminer le niveau de risque
            if probability > 0.8:
                risk_level = "CRITICAL"
            elif probability > 0.6:
                risk_level = "HIGH"
            elif probability > 0.4:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"
            
            # Prédiction binaire
            prediction_binary = probability > self.prediction_threshold
            
            result = {
                'probability': float(probability),
                'prediction': bool(prediction_binary),
                'risk_level': risk_level,
                'timestamp': datetime.now().isoformat(),
                'features_used': features[0].tolist() if features.shape[0] > 0 else []
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur prédiction: {e}")
            import traceback
            traceback.print_exc()
            return self._default_prediction()
    
    def _default_prediction(self):
        """Retourne une prédiction par défaut"""
        return {
            'probability': 0.0,
            'prediction': False,
            'risk_level': 'UNKNOWN',
            'timestamp': datetime.now().isoformat(),
            'features_used': []
        }
    
    def predict_from_collector_data(self, data_collector, dpid):
        """
        Prédit la congestion à partir des données RÉELLES d'un collecteur
        """
        try:
            # Récupérer les dernières données RÉELLES
            latest_data = data_collector.get_latest_data(dpid)
            
            if not latest_data:
                self.logger.warning(f"⚠️ Pas de données RÉELLES pour le switch {dpid}")
                return self._default_prediction()
            
            # DEBUG: Afficher les données réelles
            self.logger.info(f"🔍 Switch {dpid} - Données RÉELLES: "
                           f"BW={latest_data.get('bandwidth_utilization', 0):.2%}, "
                           f"Packets={latest_data.get('packet_count', 0):,}, "
                           f"Flows={latest_data.get('flow_count', 0)}")
            
            # Extraire les VRAIES features
            features = self._extract_features_from_data(latest_data)
            
            if features is None:
                self.logger.warning(f"⚠️ Impossible d'extraire features pour switch {dpid}")
                return self._default_prediction()
            
            # Faire la prédiction
            prediction = self.predict_congestion(features)
            
            if prediction:
                prediction['switch_id'] = dpid
                prediction['data_timestamp'] = latest_data.get('timestamp', '')
                prediction['real_metrics'] = {
                    'bandwidth_utilization': latest_data.get('bandwidth_utilization', 0),
                    'packet_count': latest_data.get('packet_count', 0),
                    'flow_count': latest_data.get('flow_count', 0),
                    'latency': latest_data.get('latency', 0),
                    'queue_occupancy': latest_data.get('queue_occupancy', 0)
                }
            
            self.logger.info(f"🎯 Switch {dpid}: {prediction['probability']:.1%} ({prediction['risk_level']})")
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"❌ Erreur prédiction switch {dpid}: {e}")
            import traceback
            traceback.print_exc()
            return self._default_prediction()
    
    def get_model_info(self):
        """Retourne des informations sur le modèle"""
        info = {
            'model_type': self.model_type,
            'n_features': getattr(self.scaler, 'n_features_in_', 'Unknown'),
            'feature_names': self.feature_names,
            'prediction_threshold': self.prediction_threshold,
            'last_trained': self._get_last_training_time()
        }
        
        if hasattr(self.model, 'n_estimators'):
            info['n_estimators'] = self.model.n_estimators
        
        return info
    
    def _get_last_training_time(self):
        """Récupère la date du dernier entraînement"""
        try:
            model_file = f"congestion_model_{self.model_type}.pkl"
            if os.path.exists(model_file):
                return datetime.fromtimestamp(os.path.getmtime(model_file)).isoformat()
        except:
            pass
        
        return "Never"

# Test amélioré
if __name__ == "__main__":
    print("="*70)
    print("   🧪 TEST PRÉDICTEUR AVEC DONNÉES VARIÉES")
    print("="*70)
    
    predictor = CongestionPredictor(model_type='random_forest')
    
    # Données de test RÉALISTES et DIFFÉRENTES
    test_switches = [
        {"dpid": 11, "name": "Switch chargé", "bw": 0.85, "packets": 800000, "flows": 25},
        {"dpid": 16, "name": "Switch normal", "bw": 0.45, "packets": 300000, "flows": 12},
        {"dpid": 19, "name": "Switch léger", "bw": 0.12, "packets": 50000, "flows": 4},
        {"dpid": 1, "name": "Switch congestionné", "bw": 0.95, "packets": 1200000, "flows": 40},
    ]
    
    print("\n📊 SIMULATION DE PRÉDICTIONS DIFFÉRENTES:")
    print("-"*70)
    
    for switch in test_switches:
        # Simuler les données du collecteur
        test_data = {
            'bandwidth_utilization': switch['bw'],
            'packet_count': switch['packets'],
            'flow_count': switch['flows'],
            'latency': switch['bw'] * 20 + 5,
            'queue_occupancy': switch['bw'] * 0.8,
            'error_rate': 0.01,
            'port_utilization': switch['bw'],
            'byte_count': switch['packets'] * 1000,
            'timestamp': datetime.now().isoformat()
        }
        
        # Extraire features
        features = predictor._extract_features_from_data(test_data)
        
        # Prédire
        if features is not None:
            result = predictor.predict_congestion(features)
            
            # Afficher
            print(f"\n🔹 {switch['name']} (s{switch['dpid']}):")
            print(f"   BW: {switch['bw']:.1%}, Packets: {switch['packets']:,}, Flows: {switch['flows']}")
            print(f"   → Probabilité: {result['probability']:.1%}")
            print(f"   → Risque: {result['risk_level']}")
            print(f"   → Prédiction: {'🚨 CONGESTION' if result['prediction'] else '✅ NORMAL'}")
    
    print("\n" + "="*70)
    print("   ✅ TEST TERMINÉ - Prédictions DEVRAIENT être différentes")
    print("="*70)
