
import os
import sys
import joblib
import pandas as pd
import numpy as np

# V41.0: XGBoost Upgrade (replaces LogisticRegression)
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.ml.feature_generator import FeatureGenerator
from src.shared.system.logging import Logger

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODELS_DIR, "ml_filter.pkl")

def train_predictor():
    """
    V41.0: Train an XGBoost model to predict trade success.
    Success = Price rises > 0.3% in next 5 minutes.
    
    Upgrade from V36.0 LogisticRegression:
    - Better handling of non-linear feature interactions
    - Improved generalization with tree ensemble
    - Built-in regularization (subsample, colsample_bytree)
    """
    print("🧠 V41.0: Starting XGBoost Training...")
    
    # 1. Load Data
    gen = FeatureGenerator()
    raw_df = gen.load_raw_data(limit=50000)  # Load up to 50k ticks
    
    print(f"   📊 Loaded {len(raw_df)} raw ticks from DB.")
    
    if len(raw_df) < 200:
        print("   ⚠️ Insufficient data to train (Need > ~200 ticks for candles). Skipping.")
        return False

    # 2. Features
    df = gen.create_features(raw_df)
    print(f"   ✨ Generated {len(df)} samples after feature engineering.")
    
    if len(df) < 50:
        print("   ⚠️ Insufficient labeled samples (Need > 50). Skipping.")
        return False
        
    # 3. Train/Test Split
    # Features: RSI, Volatility, Liquidity (Log), Latency
    feature_cols = ['rsi', 'volatility_pct', 'log_liquidity', 'latency_smooth']
    X = df[feature_cols]
    y = df['target']
    
    # Check class balance
    pos_samples = y.sum()
    neg_samples = len(y) - pos_samples
    
    if pos_samples < 5 or neg_samples < 5:
        print(f"   ⚠️ Extreme class imbalance (Pos: {pos_samples}/{len(y)}). Skipping.")
        return False

    # Calculate scale_pos_weight for class imbalance (XGBoost equivalent of class_weight='balanced')
    scale_pos_weight = neg_samples / pos_samples if pos_samples > 0 else 1.0
    print(f"   ⚖️ Class balance: {pos_samples} positive / {neg_samples} negative (scale={scale_pos_weight:.2f})")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 4. Train XGBoost Model
    model = xgb.XGBClassifier(
        objective='binary:logistic',  # Binary classification
        n_estimators=100,             # Number of boosting rounds
        max_depth=5,                  # Max depth of trees (prevents overfitting)
        learning_rate=0.1,            # Step size shrinkage
        subsample=0.7,                # Subsample ratio of training instances
        colsample_bytree=0.7,         # Subsample ratio of columns per tree
        scale_pos_weight=scale_pos_weight,  # Handle class imbalance
        random_state=42,
        eval_metric='logloss',
        verbosity=0                   # Suppress XGBoost warnings
    )
    
    model.fit(X_train, y_train)
    
    # 5. Evaluate
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)
    
    print(f"\n   🎓 Training Complete. Accuracy: {acc:.2%}")
    print("   📈 Classification Report:\n" + report)
    
    # 5.1 Feature Importance (XGBoost advantage)
    print("   📊 Feature Importance:")
    for feat, imp in zip(feature_cols, model.feature_importances_):
        bar = "█" * int(imp * 20)
        print(f"      {feat:18s}: {imp:.3f} {bar}")
    
    # 6. Save
    joblib.dump(model, MODEL_PATH)
    print(f"\n   💾 Model saved to: {MODEL_PATH}")
    return True

if __name__ == "__main__":
    try:
        success = train_predictor()
        if not success:
            print("   ⚠️ Training deferred until more data accumulates.")
    except ImportError as e:
        print(f"   ❌ Missing dependency. Please run: pip install xgboost scikit-learn joblib")
        print(f"   Error: {e}")
    except Exception as e:
        print(f"   ❌ Training Error: {e}")
