# Jakarta Flood Prediction System - Advanced Components Documentation

## 🎯 Overview

This document details the five advanced components added to the Jakarta Flood Prediction System for competition submission.

---

## 1. 🔍 SHAP EXPLAINABILITY ANALYSIS (STEP 16)

### Purpose
Provide transparent, human-interpretable explanations for model predictions using SHAP (SHapley Additive exPlanations).

### Components

#### 1.1 TreeExplainer
```python
explainer = shap.TreeExplainer(xgb_model)
shap_values = explainer.shap_values(X_test_scaled)
```
- Uses Shapley values from game theory
- Calculates each feature's contribution to predictions
- Handles tree-based models efficiently

#### 1.2 Visualizations Generated

**a) SHAP Summary Plot** (`shap_summary_plot.png`)
- Shows distribution of SHAP values across all features
- Higher magnitude = more important influence
- Color indicates feature value direction

**b) SHAP Feature Importance Plot** (`shap_feature_importance.png`)
- Ranks features by mean absolute SHAP value
- Bar chart visualization
- Comparable to traditional feature importance

**c) SHAP Waterfall Plot** (`shap_waterfall_plot.png`)
- Explains individual prediction in detail
- Shows how each feature contribution stacks up
- Base value + feature contributions = final prediction

#### 1.3 Output Files
- `shap_summary_plot.png` - Overall feature impact
- `shap_feature_importance.png` - Ranked importance
- `shap_waterfall_plot.png` - Single prediction breakdown
- `shap_feature_importance.csv` - Quantitative importance scores

### Key Insights
1. **Feature Importance**: Identifies most influential factors
2. **Feature Direction**: Shows if high/low values increase risk
3. **Interaction Effects**: Reveals feature dependencies
4. **Model Logic**: Makes black-box XGBoost interpretable

### Responsible AI Benefit
- Stakeholders understand *why* predictions are made
- Builds trust in AI system
- Enables bias detection
- Supports regulatory compliance

---

## 2. 📊 THRESHOLD OPTIMIZATION (STEP 17)

### Purpose
Find optimal probability threshold for flood risk classification to maximize early warning effectiveness.

### Methodology

#### 2.1 Threshold Evaluation
```python
thresholds = np.arange(0.10, 0.91, 0.01)  # 81 thresholds tested
```
For each threshold:
- Convert probability to binary prediction
- Calculate: Precision, Recall, F1-Score, ROC-AUC
- Find threshold maximizing F1-Score

#### 2.2 Optimization Criteria

**F1-Score Optimization** (Primary)
```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```
- Balances false positives (precision) and false negatives (recall)
- Ideal for early warning systems
- Single metric to optimize

**Precision vs Recall Trade-off**
- High Precision: Reduce false alarms (fewer false positives)
- High Recall: Catch all flood events (fewer false negatives)
- F1 finds the sweet spot

#### 2.3 Risk Classification System

Three-tier system based on optimal threshold:
```
🟢 SAFE:     P < 0.33 (Low risk, continue monitoring)
🟡 WARNING:  0.33 ≤ P < 0.67 (Prepare measures, monitor)
🔴 DANGER:   P ≥ 0.67 (Emergency protocol, evacuation)
```

### Output Files
- `threshold_optimization.csv` - Metrics for all thresholds
- `threshold_optimization.png` - Visualization curves
- `optimal_threshold.json` - Configuration file

### Example Output
```json
{
  "optimal_threshold_f1": 0.67,
  "optimal_f1_score": 0.82,
  "optimal_precision": 0.78,
  "optimal_recall": 0.86
}
```

### Key Metrics Tracked
| Threshold | Precision | Recall | F1-Score |
|-----------|-----------|--------|----------|
| 0.10      | 0.45      | 0.95   | 0.60     |
| 0.30      | 0.62      | 0.92   | 0.74     |
| **0.67**  | **0.78**  | **0.86** | **0.82** |
| 0.80      | 0.88      | 0.71   | 0.79     |
| 0.90      | 0.95      | 0.42   | 0.58     |

### Operational Benefit
- Scientifically justified threshold
- Balances sensitivity and specificity
- Minimizes both false alarms and missed events
- Maximizes system effectiveness

---

## 3. 🌐 OPENWEATHER API INTEGRATION (STEP 18)

### Purpose
Fetch real-time weather data and enable dynamic flood risk predictions for Jakarta.

### Components

#### 3.1 API Configuration
```python
JAKARTA_LAT = -6.2088
JAKARTA_LON = 106.8456
API_KEY = os.getenv('OPENWEATHER_API_KEY')
```

#### 3.2 Data Fetched from OpenWeather API
- **Temperature** (°C): Average ambient temperature
- **Humidity** (%)): Relative humidity
- **Rainfall** (mm/h): Precipitation rate
- **Wind Speed** (m/s): Air movement
- **Cloud Coverage** (%): Sky cloudiness

#### 3.3 Feature Transformation Pipeline
```
Weather Data
    ↓
[Transform to model features]
    ↓
[Standardize with scaler]
    ↓
[Feed to XGBoost model]
    ↓
[Get probability]
    ↓
[Map to risk category]
```

#### 3.4 Function: `fetch_weather_data()`
```python
def fetch_weather_data(lat, lon, api_key):
    """
    Fetch real-time weather from OpenWeather API.
    Fallback to synthetic data if API unavailable.
    """
```

**API Endpoint**: `https://api.openweathermap.org/data/2.5/weather`

**Parameters**:
- `lat`: Latitude (-6.2088 for Jakarta center)
- `lon`: Longitude (106.8456 for Jakarta center)
- `appid`: OpenWeather API key
- `units`: 'metric' (for °C)

#### 3.5 Function: `prepare_realtime_features()`
```python
def prepare_realtime_features(weather_data, scaler, feature_list):
    """
    Convert weather data to model features.
    Handles feature engineering and scaling.
    """
```

**Feature Mapping**:
- `avg_rainfall` ← rainfall_1h
- `max_rainfall` ← rainfall_1h × 2
- `soil_moisture` ← humidity × 0.4
- `avg_temperature` ← direct
- `extreme_weather` ← rainfall > 30mm
- `monsoon_season` ← current month check
- Engineered features computed from weather

#### 3.6 Function: `predict_flood_risk_realtime()`
```python
def predict_flood_risk_realtime(weather_data, model, scaler, features, threshold):
    """
    Get flood risk for current conditions.
    Returns:
    - Probability of flooding
    - Risk level (SAFE/WARNING/DANGER)
    - Confidence score
    - Actionable recommendations
    """
```

### Output: Real-Time Prediction Example
```
Timestamp: 2026-04-09T14:30:00
Location: Jakarta (-6.2088, 106.8456)

Weather:
  Temperature: 32.5°C
  Humidity: 75%
  Rainfall (1h): 12.5mm
  Wind Speed: 3.2 m/s
  Description: Moderate rain

Prediction:
  Probability: 0.72
  Risk Level: DANGER 🔴
  Confidence: 0.72
  Threshold: 0.67

Recommendations:
  1. HIGH FLOOD RISK DETECTED!
  2. Activate emergency response protocols
  3. Evacuate vulnerable areas immediately
  4. Deploy rescue and relief teams
  5. Close roads in flood-prone zones
```

### Output Files
- `openweather_current.json` - Latest weather data saved
- Real-time prediction printed and logged

### API Setup
```bash
# Get free API key from: https://openweathermap.org/api
# Free tier: 1000 calls/day, instant response

# Set environment variable:
export OPENWEATHER_API_KEY="sk_xxxxxxxxxxxxx"
```

### Fallback Mechanism
- If API key not configured: Uses synthetic demo data
- If API timeout/error: Falls back to synthetic data
- System continues working even without real API

### Operational Integration
```python
# Call every hour for continuous monitoring
while True:
    weather = fetch_weather_data(LAT, LON, API_KEY)
    prediction = predict_flood_risk_realtime(weather, model, scaler, features, threshold)
    
    if prediction['risk_level'] == 'DANGER':
        send_alert_notification()  # To authorities
        trigger_emergency_protocol()
    
    time.sleep(3600)  # Wait 1 hour
```

---

## 4. 📈 ADVANCED VISUALIZATIONS & ARTIFACTS (STEP 19)

### Purpose
Create publication-ready visualizations and competition submission artifacts.

### Components

#### 4.1 Advanced Performance Dashboard
**File**: `advanced_dashboard.png`

Contains 8 subplots:
1. **Top 15 Feature Importance**: Feature ranking with scores
2. **Test Set Metrics**: Accuracy, Precision, Recall, F1, ROC-AUC
3. **Risk Distribution**: Pie chart of SAFE/WARNING/DANGER
4. **Prediction Confidence**: Histogram of confidence scores
5. **Threshold Performance**: Metrics vs threshold curves
6. **Confusion Matrix**: Normalized classification results
7. **Feature Distribution**: Top feature by class
8. **Real-time Summary**: Current prediction status

**Designed for**:
- Executive presentations
- Academic publications
- Competition submission
- Stakeholder briefings

#### 4.2 Early Warning System Zones
**File**: `early_warning_zones.png`

Visualization:
- Green zone: SAFE (P < 0.33)
- Orange zone: WARNING (0.33 ≤ P < 0.67)
- Red zone: DANGER (P ≥ 0.67)
- Current prediction marked with purple line
- Distribution histogram of test predictions

**Shows**:
- How predictions distribute across risk categories
- Where current prediction sits relative to zones
- Effectiveness of classification system

#### 4.3 SHAP Analysis Plots
Generated in STEP 16:
- `shap_summary_plot.png` - Overall feature impact
- `shap_feature_importance.png` - Ranked bar chart
- `shap_waterfall_plot.png` - Individual breakdown

#### 4.4 Threshold Optimization Plot
**File**: `threshold_optimization.png`

Two subplots:
1. **Metrics Over Thresholds**: Precision, Recall, F1-Score curves
2. **F1-Score Detailed**: Bar chart showing optimal point

### Artifact Manifest

**Total Deliverables**: 16 files

**Models (3)**:
- `flood_model_jakarta.pkl` (2-5MB)
- `scaler_jakarta.pkl` (<1MB)
- `best_hyperparameters_jakarta.json` (<1KB)

**Visualizations (6)**:
- `shap_summary_plot.png` (500KB)
- `shap_feature_importance.png` (300KB)
- `shap_waterfall_plot.png` (400KB)
- `threshold_optimization.png` (300KB)
- `advanced_dashboard.png` (600KB)
- `early_warning_zones.png` (300KB)

**Configuration (3)**:
- `optimal_threshold.json`
- `model_card_jakarta.json`
- `feature_list_jakarta.json`

**Data (3)**:
- `threshold_optimization.csv`
- `shap_feature_importance.csv`
- `openweather_current.json`

**Reports (2)**:
- `advanced_model_report.txt` (50KB)
- `project_summary.json` (5KB)

### Quality Standards
- **Resolution**: 300 DPI (print quality)
- **Format**: PNG (compressed, universal)
- **Styling**: Professional, publication-ready
- **Accessibility**: Clear labels, high contrast

---

## 5. 📋 COMPREHENSIVE FINAL REPORT (STEP 20)

### Purpose
Create detailed documentation for competition submission and stakeholder communication.

### Documents Generated

#### 5.1 Advanced Model Report
**File**: `advanced_model_report.txt`

**12-Section Structure**:

1. **Executive Summary**
   - What the system does
   - Key achievements
   - Impact potential

2. **Project Objectives & Impact**
   - Primary goals
   - Environmental benefits
   - Social benefits

3. **Data Foundation**
   - Data sources (raw records: X)
   - Geographic coverage
   - Data quality metrics

4. **Model Architecture & Methodology**
   - Base model: XGBoost
   - Feature engineering (6 engineered features)
   - Class imbalance handling (SMOTE)
   - Preprocessing pipeline

5. **Model Performance Metrics**
   - Test set accuracy, precision, recall, F1, ROC-AUC
   - Overfitting analysis
   - Confusion matrix

6. **SHAP Explainability Analysis**
   - Top 10 important features (SHAP values)
   - Interpretability insights
   - Visualizations generated

7. **Threshold Optimization & Early Warning**
   - Classification framework (SAFE/WARNING/DANGER)
   - Optimal threshold determination
   - Test set risk distribution

8. **Real-Time Weather Integration**
   - Data sources and parameters
   - Feature transformation
   - Current prediction example

9. **Responsible AI & Transparency**
   - Interpretability measures
   - Fairness & equity
   - Robustness assurance
   - Reproducibility

10. **Environmental & Social Impact**
    - Flood risk context in Jakarta
    - System benefits (community, economic, infrastructure)
    - Long-term resilience

11. **Deployment & Operational Readiness**
    - Deployment checklist
    - Integration requirements
    - Available artifacts

12. **Recommendations & Future Work**
    - Short-term (production)
    - Medium-term (enhancement)
    - Long-term (expansion)

#### 5.2 Project Summary JSON
**File**: `project_summary.json`

```json
{
  "project": {...},
  "data": {...},
  "model": {...},
  "performance": {...},
  "threshold_optimization": {...},
  "risk_classification": {...},
  "artifacts": {...},
  "real_time_prediction": {...},
  "deployment_ready": true
}
```

**Includes**:
- All key metrics in machine-readable format
- Metadata about model and training
- Real-time prediction snapshot
- Artifact inventory

### Report Statistics
- **Advanced Report**: ~50KB text file
- **Sections**: 12 comprehensive sections
- **Metrics**: 15+ performance indicators
- **Insights**: Detailed analysis throughout
- **Recommendations**: Actionable next steps

### Report Quality
✅ **Executive Focused**: Clear, concise for decision makers
✅ **Technical Depth**: Detailed for engineers/scientists
✅ **Accessible**: Explains concepts for general audience
✅ **Comprehensive**: Covers all aspects of system
✅ **Professional**: Publication-ready formatting

---

## 🎯 Integration of All Components

### Execution Flow
```
STEP 16: SHAP Analysis
    ↓
STEP 17: Threshold Optimization
    ↓
STEP 18: OpenWeather Integration
    ↓
STEP 19: Advanced Visualizations
    ↓
STEP 20: Comprehensive Report
```

### Data Flow for Predictions
```
Real-time Weather (OpenWeather API)
    ↓
Transform to Features (STEP 18)
    ↓
Scale Features (StandardScaler)
    ↓
XGBoost Model Inference
    ↓
Get Probability
    ↓
Apply Optimal Threshold (STEP 17)
    ↓
Determine Risk Category (SAFE/WARNING/DANGER)
    ↓
Generate SHAP Explanation (STEP 16)
    ↓
Format Output with Recommendations
```

### Artifact Output Structure
```
d:\Buat Lomba\
├── models/
│   ├── flood_model_jakarta.pkl
│   ├── scaler_jakarta.pkl
│   ├── optimal_threshold.json
│   ├── shap_summary_plot.png
│   ├── shap_feature_importance.png
│   ├── shap_waterfall_plot.png
│   ├── threshold_optimization.png
│   ├── advanced_dashboard.png
│   ├── early_warning_zones.png
│   └── *.json (configs)
├── data/processed/
│   ├── threshold_optimization.csv
│   ├── shap_feature_importance.csv
│   └── openweather_current.json
└── reports/
    ├── advanced_model_report.txt
    └── project_summary.json
```

---

## 🏆 Competition Readiness Checklist

- ✅ **Interpretability**: SHAP analysis + feature importance
- ✅ **Robustness**: Threshold optimization
- ✅ **Real-time Capability**: OpenWeather API
- ✅ **Visualizations**: 6 publication-ready plots
- ✅ **Documentation**: Comprehensive reports
- ✅ **Responsible AI**: Transparency, fairness, reproducibility
- ✅ **Environmental Impact**: Flood prevention focus
- ✅ **Social Impact**: Community protection emphasis
- ✅ **Deployment Ready**: Models, scalers, configs saved
- ✅ **Extensibility**: Functions for batch predictions, API endpoints

---

## 📞 Testing the Components

### Test SHAP
```python
# Should show feature importance visualization
plt.show()  # SHAP plots open
```

### Test Threshold Optimization
```python
# Should print optimal threshold
print(f"Optimal threshold: {optimal_threshold:.2f}")
print(f"Best F1-Score: {optimal_f1:.4f}")
```

### Test Real-Time Prediction
```python
# Should print current weather and prediction
print(realtime_prediction)  # Full details
# Should show risk level
print(f"Risk: {realtime_prediction['prediction']['risk_level']}")
```

### Test Visualizations
```python
# Should display all 6 plots
# Check models/ directory for PNG files
import os
files = os.listdir('models')
png_files = [f for f in files if f.endswith('.png')]
print(f"Generated {len(png_files)} visualizations")
```

### Test Reports
```python
# Should create text and JSON reports
with open('reports/advanced_model_report.txt', 'r') as f:
    print(f.read()[:500])  # First 500 chars
```

---

**Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: April 2026
