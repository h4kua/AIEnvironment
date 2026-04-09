# 🚀 Jakarta Flood Prediction System - Running Instructions

## Quick Start

### 1. Environment Setup

```bash
# Navigate to project directory
cd "d:\Buat Lomba"

# Activate virtual environment (if using flood_env)
flood_env\Scripts\activate

# Install required packages
pip install pandas numpy matplotlib seaborn scikit-learn xgboost shap joblib requests ipykernel
```

### 2. Set Environment Variables (Optional - for real weather data)

```bash
# Windows PowerShell
$env:OPENWEATHER_API_KEY = "your_api_key_here"

# Windows Command Prompt
set OPENWEATHER_API_KEY=your_api_key_here

# Or add to .env file
OPENWEATHER_API_KEY=your_api_key_here
```

Get API key from: https://openweathermap.org/api (free tier: 1000 calls/day)

### 3. Run the Notebook

```bash
# Option A: VS Code - Open and run all cells
# File: app/models/jakarta_flood_prediction.ipynb

# Option B: Jupyter Lab
jupyter lab

# Option C: Jupyter Notebook
jupyter notebook
```

### 4. Expected Execution Time

- **Full Pipeline**: 12-20 minutes
  - Data Processing: 1-2 minutes
  - Model Training: 5-10 minutes
  - SHAP Analysis: 4-8 minutes (compute-intensive)
  - Threshold Optimization: 1-2 minutes
  - Report Generation: 1 minute

## What Gets Generated

### Models & Configuration (3 files)
- `models/flood_model_jakarta.pkl` - Production model
- `models/scaler_jakarta.pkl` - Feature scaler
- `models/optimal_threshold.json` - Threshold config

### Visualizations (6 files)
```
models/
├── shap_summary_plot.png
├── shap_feature_importance.png
├── shap_waterfall_plot.png
├── threshold_optimization.png
├── advanced_dashboard.png
└── early_warning_zones.png
```

### Data & Analysis (3 files)
```
data/processed/
├── threshold_optimization.csv
├── shap_feature_importance.csv
└── openweather_current.json
```

### Reports (2 files)
```
reports/
├── advanced_model_report.txt
└── project_summary.json
```

## Notebook Structure

```
STEP 1:  Import Libraries
STEP 2:  Setup Directories
STEP 3:  Load & Merge Raw Data
STEP 4:  Filter Data for Jakarta Only
STEP 5:  Region Mapping & Distribution
STEP 6:  Data Cleansing
STEP 7:  Feature Engineering
STEP 8:  Save Cleaned Data
STEP 9:  Model Preparation
STEP 10: Model Training & Tuning
STEP 11: Model Evaluation
STEP 12: Visualizations
STEP 13: Risk Classification
STEP 14: Save Model Artifacts
STEP 15: Generate Reports
STEP 16: SHAP Explainability ⭐ NEW
STEP 17: Threshold Optimization ⭐ NEW
STEP 18: OpenWeather Integration ⭐ NEW
STEP 19: Advanced Visualizations ⭐ NEW
STEP 20: Comprehensive Report ⭐ NEW
```

## Key Features Added

### 🔍 SHAP Explainability (STEP 16)
- TreeExplainer for model interpretation
- Summary plots showing feature impact
- Feature importance rankings
- Waterfall plots for individual predictions

### 📊 Threshold Optimization (STEP 17)
- Tests 81 different thresholds (0.10 to 0.90)
- Optimizes F1-Score for balanced performance
- Generates precision-recall curves
- Produces optimal_threshold.json

### 🌐 Real-Time Weather API (STEP 18)
- Integrates OpenWeather API
- Fetches current Jakarta weather
- Transforms weather to model features
- Provides real-time risk predictions
- Generates action recommendations

### 📈 Advanced Visualizations (STEP 19)
- Comprehensive performance dashboard
- Early warning system zones
- SHAP-based explainability plots
- Competition-ready graphics

### 📋 Comprehensive Report (STEP 20)
- Executive summary
- Model architecture details
- Performance analysis
- Responsible AI assessment
- Environmental & social impact
- Deployment recommendations

## Project Deliverables

✅ **Interpretability**: SHAP analysis + feature importance
✅ **Robustness**: Threshold optimization for early warning  
✅ **Real-time**: OpenWeather API integration
✅ **Responsible AI**: Transparent, explainable predictions
✅ **Competition Ready**: All visualizations and reports
✅ **Production Ready**: Model persistence and reproducibility

## Troubleshooting

### Common Issues

**"SHAP not installed"**
- Solution: Auto-installs on first run, or `pip install shap`

**"API timeout"**
- Solution: System uses demo data if API fails

**"Memory error"**
- Solution: Close other apps or reduce dataset size

**"Import errors"**
- Solution: `pip install -r requirements.txt`

**"Model not found"**
- Solution: Ensure Step 14 executed successfully

## Advanced Usage

### Making Predictions on New Data

```python
# In Python after running notebook:
import pandas as pd
import joblib
from datetime import datetime

# Load model and scaler
model = joblib.load('models/flood_model_jakarta.pkl')
scaler = joblib.load('models/scaler_jakarta.pkl')
features = ['avg_rainfall', 'max_rainfall', ...]  # From feature_list

# Prepare your data
X_new = pd.DataFrame({...})  # Your new data

# Predict
probability = model.predict_proba(scaler.transform(X_new))[0, 1]
risk_level = 'DANGER' if probability > 0.67 else 'WARNING' if probability > 0.33 else 'SAFE'
print(f"Flood Risk: {risk_level} ({probability:.2%})")
```

### Batch Predictions

```python
# Predict for multiple locations
def batch_predict(data_list):
    results = []
    for data in data_list:
        weather_data = fetch_weather_data(data['lat'], data['lon'])
        prediction = predict_flood_risk_realtime(
            weather_data, model, scaler, features, 0.67
        )
        results.append(prediction)
    return results
```

## Performance Expectations

### Test Set Metrics
- **Accuracy**: ~0.75-0.85 (depending on data distribution)
- **Precision**: ~0.70-0.80 (minimize false alarms)
- **Recall**: ~0.80+ (catch flood events)
- **F1-Score**: ~0.75-0.82 (balanced score)
- **ROC-AUC**: ~0.80-0.90 (model discrimination)

### Real-Time Performance
- **Inference time**: <100ms per prediction
- **API response**: 1-2 seconds (with network)
- **Memory**: <500MB for loaded model

## Project Structure Expected

```
d:\Buat Lomba\
├── app/
│   ├── models/
│   │   └── jakarta_flood_prediction.ipynb ⭐
│   ├── agents/
│   ├── services/
│   └── utils/
├── data/
│   ├── raw/
│   └── processed/
├── flood_env/
├── models/
│   ├── flood_model_jakarta.pkl
│   ├── scaler_jakarta.pkl
│   ├── shap_*.png (3 files)
│   ├── *_optimization.png
│   ├── advanced_dashboard.png
│   ├── early_warning_zones.png
│   └── *.json (configs)
├── reports/
│   ├── advanced_model_report.txt
│   └── project_summary.json
├── visualizations/
└── RUNNING_INSTRUCTIONS.md ⭐
```

## Next Steps After Running

1. **Review Reports**: Check `advanced_model_report.txt` for insights
2. **Examine Visualizations**: View PNG files in `models/` directory
3. **Check Metrics**: Review performance in `project_summary.json`
4. **Integration**: Use functions for deployment
5. **Customization**: Modify thresholds based on use case
6. **Documentation**: Share report with stakeholders

## Support & Questions

- Check notebook cells 1-3 for setup validation
- Review STEP 15 for model artifacts details
- See STEP 16-20 for new functionality
- Check RUNNING_INSTRUCTIONS.md for this guide

---

**Status**: Production Ready ✅  
**Version**: 1.0  
**Last Updated**: April 2026  
**Competition**: AI for Environmental & Social Impact
