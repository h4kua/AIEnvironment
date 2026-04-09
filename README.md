# Jakarta Flood Prediction System

Advanced AI-Powered Flood Risk Prediction for Jakarta

## Project Overview

A production-ready machine learning solution for predicting flood risks in Jakarta. Combines advanced ML models, explainability analysis (SHAP), real-time weather integration, and threshold optimization.

## Key Features

- Advanced ML Model: XGBoost with calibration
- Explainability: SHAP analysis for interpretable predictions
- Real-Time Integration: OpenWeather API
- Threshold Optimization: F1-score optimized decision boundaries
- Multi-Agent Architecture: Modular agents for monitoring
- Production-Ready: Built for deployment

## Quick Start

### Prerequisites
- Python 3.8+
- pip or conda
- OpenWeather API key

### Installation

```bash
# Create virtual environment
python -m venv flood_env
source flood_env/bin/activate  # Windows: flood_env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenWeather API key
```

### Running the System

```bash
# Using Jupyter Notebook
jupyter notebook notebooks/production/jakarta_flood_prediction.ipynb

# Or use Python API
python -c "from app.agents.monitoring_agent import MonitoringAgent; m = MonitoringAgent(); print(m.predict_flood_risk())"
```

## Project Structure

```
JAKARTA-FLOOD-PREDICTION/
|
+-- app/                    Application code (agents, models, services)
+-- data/                   Data management (raw, processed, external)
+-- artifacts/              Production artifacts (models, configs, reports, visualizations)
+-- notebooks/              Jupyter notebooks (exploratory, production)
+-- deployment/             Deployment configs (docker, kubernetes)
+-- tests/                  Test suites (unit, integration)
+-- docs/                   Documentation (guides, architecture)
|
+-- .env.example            Environment variables template
+-- .gitignore              Git ignore rules
+-- requirements.txt        Python dependencies
+-- setup.py                Package setup
+-- pyproject.toml          Project metadata
+-- README.md               This file
```

## Model Performance

| Metric | Value |
|--------|-------|
| Accuracy | ~85%+ |
| Precision | ~83%+ |
| Recall | ~82%+ |
| F1-Score | ~0.82 |
| ROC-AUC | ~0.90+ |

## Components

### Data Pipeline
- Raw data ingestion
- Data cleaning & validation
- Feature engineering (6 domain-specific features)
- Processed data for training

### ML Model
- Base Model: XGBoost Classifier
- Calibration: CalibratedClassifierCV
- Optimization: GridSearchCV
- High accuracy with balanced metrics

### Explainability
- SHAP analysis for feature importance
- Model decision breakdown
- Transparent, interpretable predictions

### Real-Time Integration
- OpenWeather API for live weather data
- Dynamic feature transformation
- Live prediction updates

### Monitoring Agents
- Continuous flood risk monitoring
- Threshold-based alert system
- Risk classification (SAFE/WARNING/DANGER)

## Risk Classification

| Level | Probability | Action |
|-------|-------------|--------|
| SAFE | < threshold*0.5 | Normal operations |
| WARNING | threshold*0.5 - threshold | Prepare emergency measures |
| DANGER | >= threshold | Activate emergency protocol |

## Documentation

- `docs/guides/RUNNING_INSTRUCTIONS.md` - Setup & running
- `docs/guides/API_USAGE_GUIDE.py` - Python API examples
- `docs/guides/ADVANCED_COMPONENTS_GUIDE.md` - Advanced features
- `docs/architecture/` - System architecture

## Testing

```bash
# Run all tests
pytest

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=app tests/
```

## Docker Deployment

```bash
# Build image
docker build -f deployment/docker/Dockerfile -t jakarta-flood:latest .

# Run container
docker run -e OPENWEATHER_API_KEY=your_key -p 8000:8000 jakarta-flood:latest
```

## Kubernetes Deployment

```bash
# Deploy to Kubernetes
kubectl apply -f deployment/kubernetes/

# Check status
kubectl get pods
```

## License

MIT License - see LICENSE file for details

## Contact

For questions or support, please contact the team.

---

Status: Production Ready
Version: 1.0.0
Last Updated: 2026-04-09
