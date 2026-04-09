"""
Jakarta Flood Prediction System - API Reference Guide

This guide shows how to use the trained model for predictions
after running the main notebook (jakarta_flood_prediction.ipynb).
"""

# =============================================================================
# SECTION 1: LOADING THE MODEL
# =============================================================================

import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path

# Define paths
MODELS_DIR = Path('d:/Buat Lomba/models')
PROCESSED_DATA_DIR = Path('d:/Buat Lomba/data/processed')

# Load model components
print("Loading model components...")
model = joblib.load(MODELS_DIR / 'flood_model_jakarta.pkl')
scaler = joblib.load(MODELS_DIR / 'scaler_jakarta.pkl')

with open(MODELS_DIR / 'feature_list_jakarta.json', 'r') as f:
    feature_cols = json.load(f)

with open(MODELS_DIR / 'optimal_threshold.json', 'r') as f:
    threshold_config = json.load(f)

optimal_threshold = threshold_config['optimal_threshold_f1']

print("✅ Model loaded successfully!")
print(f"   Features: {len(feature_cols)}")
print(f"   Threshold: {optimal_threshold:.2f}")


# =============================================================================
# SECTION 2: SINGLE PREDICTION
# =============================================================================

def predict_single(rainfall, temperature, humidity, 
                  elevation=5.0, ndvi=0.30, slope=0.08):
    """
    Predict flood risk for single location.
    
    Parameters:
    -----------
    rainfall : float
        Max rainfall in mm
    temperature : float
        Average temperature in °C
    humidity : float
        Relative humidity in %
    elevation : float, default=5.0
        Elevation in meters (typical Jakarta: 5m)
    ndvi : float, default=0.30
        Vegetation index (0-1, typical urban Jakarta: 0.30)
    slope : float, default=0.08
        Terrain slope (typical Jakarta: 0.08)
    
    Returns:
    --------
    dict : Prediction results with risk level and recommendations
    """
    from datetime import datetime
    
    # Create feature vector
    month = datetime.now().month
    year = datetime.now().year
    
    features = pd.DataFrame({
        'avg_rainfall': [rainfall * 0.5],
        'max_rainfall': [rainfall],
        'avg_temperature': [temperature],
        'elevation': [elevation],
        'ndvi': [ndvi],
        'slope': [slope],
        'soil_moisture': [humidity * 0.4],
        'year': [year],
        'month': [month],
        'lat': [-6.2088],
        'long': [106.8456],
        # Engineered features
        'rainfall_soil_interaction': [rainfall * humidity * 0.4],
        'elevation_risk': [1 / (elevation + 1)],
        'vegetation_elevation_risk': [(1 - ndvi) * (1 / (elevation + 1))],
        'extreme_weather': [int(rainfall > 30)],
        'monsoon_season': [int(month in [11, 12, 1, 2, 3])],
        'urban_density_risk': [(1 - ndvi) / (slope + 0.1)]
    })
    
    # Select required features
    features_subset = features[feature_cols]
    
    # Scale and predict
    features_scaled = scaler.transform(features_subset)
    probability = model.predict_proba(features_scaled)[0, 1]
    
    # Classify risk
    if probability < optimal_threshold * 0.5:
        risk_level = 'SAFE'
        emoji = '🟢'
    elif probability < optimal_threshold:
        risk_level = 'WARNING'
        emoji = '🟡'
    else:
        risk_level = 'DANGER'
        emoji = '🔴'
    
    return {
        'probability': float(probability),
        'risk_level': risk_level,
        'emoji': emoji,
        'confidence': float(max(probability, 1 - probability))
    }

# Example usage:
result = predict_single(rainfall=50, temperature=32, humidity=80)
print(f"\n{result['emoji']} Prediction: {result['risk_level']}")
print(f"   Probability: {result['probability']:.4f}")
print(f"   Confidence: {result['confidence']:.4f}")


# =============================================================================
# SECTION 3: BATCH PREDICTIONS
# =============================================================================

def predict_batch(data_list):
    """
    Predict flood risk for multiple locations.
    
    Parameters:
    -----------
    data_list : list of dict
        Each dict contains: rainfall, temperature, humidity, etc.
    
    Returns:
    --------
    list : List of prediction results
    """
    results = []
    for i, data in enumerate(data_list):
        result = predict_single(
            rainfall=data.get('rainfall', 25),
            temperature=data.get('temperature', 32),
            humidity=data.get('humidity', 75),
            elevation=data.get('elevation', 5.0),
            ndvi=data.get('ndvi', 0.30),
            slope=data.get('slope', 0.08)
        )
        result['location_id'] = i
        results.append(result)
    
    return results

# Example batch prediction:
locations = [
    {'rainfall': 40, 'temperature': 32, 'humidity': 80},
    {'rainfall': 60, 'temperature': 30, 'humidity': 85},
    {'rainfall': 20, 'temperature': 34, 'humidity': 70},
]

batch_results = predict_batch(locations)
print("\n🔍 Batch Predictions:")
for result in batch_results:
    print(f"  Location {result['location_id']}: {result['risk_level']} - {result['probability']:.4f}")


# =============================================================================
# SECTION 4: OPENWEATHER API INTEGRATION
# =============================================================================

import requests
import os

def fetch_real_time_weather():
    """
    Fetch current weather from OpenWeather API and make prediction.
    """
    api_key = os.getenv('OPENWEATHER_API_KEY', 'demo')
    lat, lon = -6.2088, 106.8456
    
    if api_key != 'demo':
        try:
            url = 'https://api.openweathermap.org/data/2.5/weather'
            params = {'lat': lat, 'lon': lon, 'appid': api_key, 'units': 'metric'}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            rainfall = data.get('rain', {}).get('1h', 0)
            temperature = data['main']['temp']
            humidity = data['main']['humidity']
        except:
            print("⚠️  API error, using demo data")
            rainfall, temperature, humidity = 10, 32, 75
    else:
        # Demo data
        rainfall, temperature, humidity = 10, 32, 75
    
    # Make prediction
    result = predict_single(rainfall, temperature, humidity)
    result['weather'] = {
        'rainfall': rainfall,
        'temperature': temperature,
        'humidity': humidity
    }
    
    return result

# Example:
weather_result = fetch_real_time_weather()
print(f"\n🌤️  Current Weather Prediction")
print(f"   Temperature: {weather_result['weather']['temperature']}°C")
print(f"   Humidity: {weather_result['weather']['humidity']}%")
print(f"   Rainfall (1h): {weather_result['weather']['rainfall']}mm")
print(f"   🔴 Risk: {weather_result['risk_level']}")


# =============================================================================
# SECTION 5: PREDICTIONS FROM DATAFRAME
# =============================================================================

def predict_dataframe(df):
    """
    Predict flood risk for all rows in DataFrame.
    
    DataFrame columns required:
    avg_rainfall, max_rainfall, avg_temperature, elevation,
    ndvi, slope, soil_moisture, month, year, lat, long,
    [and other features from feature_list_jakarta.json]
    """
    # Select required features
    if not all(col in df.columns for col in feature_cols):
        raise ValueError(f"Missing required columns. Need: {feature_cols}")
    
    features_subset = df[feature_cols]
    features_scaled = scaler.transform(features_subset)
    probabilities = model.predict_proba(features_scaled)[:, 1]
    
    # Classify
    risk_levels = []
    for prob in probabilities:
        if prob < optimal_threshold * 0.5:
            risk_levels.append('SAFE')
        elif prob < optimal_threshold:
            risk_levels.append('WARNING')
        else:
            risk_levels.append('DANGER')
    
    # Add to DataFrame
    df['flood_probability'] = probabilities
    df['flood_risk_level'] = risk_levels
    
    return df

# Example: Load and predict
df = pd.read_csv(PROCESSED_DATA_DIR / 'cleaned_flood_data_jakarta.csv')
sample_df = df.head(100).copy()
predictions_df = predict_dataframe(sample_df)

print(f"\n📊 DataFrame Predictions (first 5 rows):")
print(predictions_df[['avg_rainfall', 'flood_probability', 'flood_risk_level']].head())


# =============================================================================
# SECTION 6: SHAP EXPLANATIONS FOR PREDICTIONS
# =============================================================================

def explain_prediction_shap(rainfall, temperature, humidity):
    """
    Get SHAP explanation for a prediction.
    """
    try:
        import shap
        
        # Create feature vector
        from datetime import datetime
        month = datetime.now().month
        
        features = pd.DataFrame({
            'avg_rainfall': [rainfall * 0.5],
            'max_rainfall': [rainfall],
            'avg_temperature': [temperature],
            'elevation': [5.0],
            'ndvi': [0.30],
            'slope': [0.08],
            'soil_moisture': [humidity * 0.4],
            'year': [2026],
            'month': [month],
            'lat': [-6.2088],
            'long': [106.8456],
            'rainfall_soil_interaction': [rainfall * humidity * 0.4],
            'elevation_risk': [1/6],
            'vegetation_elevation_risk': [0.7/6],
            'extreme_weather': [int(rainfall > 30)],
            'monsoon_season': [int(month in [11,12,1,2,3])],
            'urban_density_risk': [0.7/0.08]
        })
        
        features_subset = features[feature_cols]
        features_scaled = scaler.transform(features_subset)
        
        # Get base model for SHAP
        xgb_model = model.base_estimator_
        explainer = shap.TreeExplainer(xgb_model)
        shap_values = explainer.shap_values(features_scaled)
        
        # Extract feature contributions
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        
        contributions = pd.DataFrame({
            'Feature': feature_cols,
            'SHAP_Value': shap_values[0],
            'Feature_Value': features_subset.iloc[0].values
        })
        
        contributions['Abs_SHAP'] = np.abs(contributions['SHAP_Value'])
        contributions = contributions.sort_values('Abs_SHAP', ascending=False)
        
        return contributions
    
    except ImportError:
        print("⚠️  SHAP not installed. Please: pip install shap")
        return None

# Example:
explanations = explain_prediction_shap(rainfall=50, temperature=32, humidity=80)
if explanations is not None:
    print("\n🔍 SHAP Explanations (Top 10 Contributors):")
    print(explanations.head(10)[['Feature', 'SHAP_Value', 'Feature_Value']].to_string(index=False))


# =============================================================================
# SECTION 7: THRESHOLD ADJUSTMENT
# =============================================================================

def get_risk_level_custom(probability, safe_threshold=0.33, danger_threshold=0.67):
    """
    Classify risk with custom thresholds.
    
    Parameters:
    -----------
    probability : float
        Flood probability (0-1)
    safe_threshold : float
        Threshold between SAFE and WARNING (default: 0.33)
    danger_threshold : float
        Threshold between WARNING and DANGER (default: 0.67)
    
    Returns:
    --------
    str : Risk level (SAFE, WARNING, DANGER)
    """
    if probability < safe_threshold:
        return 'SAFE'
    elif probability < danger_threshold:
        return 'WARNING'
    else:
        return 'DANGER'

# Example: More conservative (more warnings)
conservative_level = get_risk_level_custom(0.55, 0.25, 0.50)
print(f"\n🎚️  Custom Threshold Example")
print(f"   Probability: 0.55")
print(f"   Standard classification: WARNING")
print(f"   Conservative (0.25/0.50): {conservative_level}")


# =============================================================================
# SECTION 8: MODEL DIAGNOSTICS
# =============================================================================

def get_model_info():
    """Get information about loaded model."""
    print("\n📊 Model Information:")
    print(f"  Model Type: XGBoost (with Calibration)")
    print(f"  Number of Features: {len(feature_cols)}")
    print(f"  Optimal Threshold: {optimal_threshold:.2f}")
    print(f"  Features: {feature_cols[:5]}... (+{len(feature_cols)-5} more)")
    print(f"  Random State: 42")
    print(f"  Status: Production Ready")

get_model_info()


# =============================================================================
# SECTION 9: SAVING PREDICTIONS
# =============================================================================

def save_predictions(predictions_df, filename='flood_predictions.csv'):
    """Save predictions to CSV."""
    output_path = PROCESSED_DATA_DIR / filename
    predictions_df.to_csv(output_path, index=False)
    print(f"✅ Predictions saved: {output_path}")

# Example:
# save_predictions(predictions_df)


# =============================================================================
# SECTION 10: QUICK START TEMPLATE
# =============================================================================

"""
QUICK START - Copy and adapt this template:

# 1. Load model
import joblib
from pathlib import Path

model = joblib.load(Path('d:/Buat Lomba/models/flood_model_jakarta.pkl'))
scaler = joblib.load(Path('d:/Buat Lomba/models/scaler_jakarta.pkl'))

# 2. Make prediction on new data
new_data = pd.DataFrame({
    'avg_rainfall': [25],
    'max_rainfall': [50],
    'avg_temperature': [32],
    # ... add all other features
})

features_scaled = scaler.transform(new_data)
probability = model.predict_proba(features_scaled)[0, 1]
risk = 'DANGER' if probability > 0.67 else 'WARNING' if probability > 0.33 else 'SAFE'

print(f"Probability: {probability:.4f}")
print(f"Risk Level: {risk}")

# 3. Save results
new_data['prediction'] = probability
new_data['risk_level'] = risk
new_data.to_csv('results.csv', index=False)
"""


# =============================================================================
# DEPLOYMENT EXAMPLE - Flask API
# =============================================================================

"""
DEPLOYMENT EXAMPLE - Flask REST API:

from flask import Flask, request, jsonify
import joblib

app = Flask(__name__)

# Load model at startup
model = joblib.load('models/flood_model_jakarta.pkl')
scaler = joblib.load('models/scaler_jakarta.pkl')

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json
    
    # Create feature vector
    features = pd.DataFrame([data])
    features_scaled = scaler.transform(features)
    
    # Predict
    probability = model.predict_proba(features_scaled)[0, 1]
    risk = 'DANGER' if probability > 0.67 else 'WARNING' if probability > 0.33 else 'SAFE'
    
    return jsonify({
        'probability': float(probability),
        'risk_level': risk,
        'confidence': float(max(probability, 1-probability))
    })

if __name__ == '__main__':
    app.run(debug=False, port=5000)

# Usage:
# curl -X POST http://localhost:5000/predict -H "Content-Type: application/json" \\
#   -d '{"avg_rainfall":50, "avg_temperature":32, ...}'
"""

print("\n" + "="*70)
print("✅ API Reference loaded successfully!")
print("   Use functions above for predictions and analysis")
print("="*70)
