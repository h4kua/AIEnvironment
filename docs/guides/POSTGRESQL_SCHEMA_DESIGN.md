# PostgreSQL Schema Design for Agentic Flood Prediction System

**System:** Multi-Agent Flood AI (Jakarta Flood Prediction)  
**Designed:** 27 April 2026  
**Architect:** Senior Database Engineer

---

## 1. Executive Summary

This document provides a complete PostgreSQL schema design for persisting all data structures used across the agentic flood prediction pipeline. The schema covers:

- **Input data storage** — Raw snapshots from data sources
- **Agent outputs** — Intermediate representations from all 5 stages
- **Reasoning traces** — Full audit trails for explainability
- **Failure logs** — Systematic failure mode tracking
- **Evaluation metrics** — Trust breakdowns and calibration data
- **Outcome tracking** — Ground truth vs prediction comparison
- **Calibration parameters** — Model performance metrics
- **Replay scenarios** — Historical scenario storage for testing

---

## 2. Data Architecture Overview

### 2.1 Pipeline Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW DIAGRAM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────┐ │
│  │  SOURCE  │───▶│PERCEPTION│───▶│ REASONING │───▶│EVALUATION│───▶│ACTION│ │
│  │  DATA    │    │  Agent   │    │   Agent   │    │   Agent  │    │Agent │ │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────┘ │
│       │               │               │               │               │      │
│       ▼               ▼               ▼               ▼               ▼      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ snapshots│    │perception│   │ reasoning│   │evaluation│   │ decisions│  │
│  │         │    │_results  │    │_results  │    │_results  │    │         │  │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘  │
│       │               │               │               │               │      │
│       ▼               ▼               ▼               ▼               ▼      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PERSISTED TABLES                                   │   │
│  │  snapshots → perception_results → reasoning_results → evaluation   │   │
│  │  → decisions → failure_logs → trust_breakdowns → calibration       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Entity Relationship Overview

| Domain | Tables | Purpose |
|--------|--------|---------|
| **Input** | `snapshots`, `snapshot_sources` | Raw data ingestion |
| **Agents** | `perception_results`, `reasoning_results`, `evaluation_results`, `decisions` | Agent outputs |
| **Trust** | `trust_breakdowns`, `failure_logs` | Reliability tracking |
| **Evaluation** | `calibration_metrics`, `ground_truth_outcomes` | Model performance |
| **Replay** | `replay_scenarios`, `scenario_runs` | Historical testing |

---

## 3. Complete PostgreSQL Schema

### 3.1 Input Data Tables

#### 3.1.1 snapshots — Raw Input Data Storage

```sql
-- filepath: schema/01_snapshots.sql
CREATE TABLE snapshots (
    -- Primary key
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_hash   VARCHAR(64) NOT NULL,  -- SHA-256 for deduplication
    
    -- Temporal metadata
    fetched_at_utc  TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- Location data
    location        VARCHAR(100),  -- District name (e.g., "Jakarta Timur")
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    
    -- Source data (JSONB for flexibility)
    openweather     JSONB,  -- OpenWeatherMap API response
    poskobanjir     JSONB, -- Posko Banjir station data (array)
    bmkg_alerts     JSONB, -- BMKG weather alerts (array)
    
    -- Data quality indicators
    data_freshness_minutes  DECIMAL(8, 2),  -- Computed freshness
    snapshot_completeness   DECIMAL(5, 4),  -- Fraction of sections present
    
    -- Processing status
    processing_status       VARCHAR(20) DEFAULT 'pending',
    -- pending | processing | completed | failed
    
    -- Constraints
    CONSTRAINT snapshots_hash_unique UNIQUE (snapshot_hash)
);

-- Indexes for common query patterns
CREATE INDEX idx_snapshots_fetched_at ON snapshots(fetched_at_utc DESC);
CREATE INDEX idx_snapshots_location ON snapshots(location);
CREATE INDEX idx_snapshots_status ON snapshots(processing_status);
CREATE INDEX idx_snapshots_hash ON snapshots(snapshot_hash);

-- Comment for documentation
COMMENT ON TABLE snapshots IS 'Raw input snapshots from data sources (OpenWeatherMap, Posko Banjir, BMKG)';
```

#### 3.1.2 snapshot_sources — Source Tracking

```sql
-- filepath: schema/02_snapshot_sources.sql
CREATE TABLE snapshot_sources (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    
    -- Source identification
    source_name         VARCHAR(50) NOT NULL,  -- openweather | poskobanjir | bmkg
    source_type         VARCHAR(20),           -- api | scrape | manual
    
    -- Source-specific metadata
    source_response_id  VARCHAR(100),  -- External reference (API ID, etc.)
    response_status     INTEGER,       -- HTTP status code
    response_time_ms    INTEGER,      -- Latency in milliseconds
    
    -- Data quality from source
    data_completeness   DECIMAL(5, 4),
    data_freshness      DECIMAL(8, 2),
    
    -- Timestamps
    fetched_at          TIMESTAMPTZ DEFAULT NOW(),
    
    -- Foreign key constraint
    CONSTRAINT fk_snapshot_sources_snapshot 
        FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX idx_snapshot_sources_snapshot ON snapshot_sources(snapshot_id);
CREATE INDEX idx_snapshot_sources_name ON snapshot_sources(source_name);

COMMENT ON TABLE snapshot_sources IS 'Track individual source responses for each snapshot';
```

---

### 3.2 Agent Output Tables

#### 3.2.1 perception_results — Stage 1: PerceptionAgent Output

```sql
-- filepath: schema/10_perception_results.sql
CREATE TABLE perception_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id             UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    
    -- Pipeline execution metadata
    pipeline_run_id         UUID,  -- Links to full pipeline execution
    agent_name              VARCHAR(20) DEFAULT 'PerceptionAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- Perception output fields (from PerceptionResult dataclass)
    data_freshness_minutes  DECIMAL(8, 2) NOT NULL,
    snapshot_completeness   DECIMAL(5, 4) NOT NULL,
    
    -- Signal presence (which categories detected)
    signal_presence         JSONB NOT NULL,  -- {
    --   "rainfall": bool, "hydrology": bool, "bmkg": bool
    -- }
    
    -- Raw features extracted
    raw_features            JSONB,  -- Direct scalars from snapshot
    
    -- Plausibility assessment
    plausibility_score      DECIMAL(5, 4),
    plausibility_details    JSONB,  -- Full plausibility dict
    
    -- Hydrology assessment
    hydrology_assessment    JSONB,  -- HydrologyAssessment dataclass
    
    -- Warnings generated
    perception_warnings     JSONB,  -- list[str]
    
    -- Vulnerability context (BNPB InaRISK)
    vulnerability_context   JSONB,  -- VulnerabilityContext or null
    mapping_info            JSONB,  -- District mapping audit trail
    
    -- Full snapshot for replay
    processed_snapshot      JSONB,  -- Normalized snapshot dict
    
    -- Constraints
    CONSTRAINT fk_perception_snapshot 
        FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX idx_perception_snapshot ON perception_results(snapshot_id);
CREATE INDEX idx_perception_run ON perception_results(pipeline_run_id);
CREATE INDEX idx_perception_executed ON perception_results(executed_at DESC);

COMMENT ON TABLE perception_results IS 'Stage 1 output: parsed and validated snapshot with signal detection';
```

#### 3.2.2 reasoning_results — Stage 2: ReasoningAgent Output

```sql
-- filepath: schema/20_reasoning_results.sql
CREATE TABLE reasoning_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID,
    
    agent_name              VARCHAR(20) DEFAULT 'ReasoningAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- ML model output
    model_variant           VARCHAR(30),  -- 'realtime_native'
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- Out-of-distribution detection
    ood_detection           JSONB,  -- {
    --   "method": "IsolationForest",
    --   "score": float,
    --   "is_outlier": bool
    -- }
    
    -- Feature engineering output
    features                JSONB,  -- Engineered feature dict
    diagnostics             JSONB,  -- Feature diagnostics
    
    -- Signal extraction
    signals                 JSONB,  -- Multi-condition risk signals
    dominant_driver         VARCHAR(50),  -- Primary risk driver
    
    -- Context and interpretation
    context_summary         JSONB,
    risk_interpretation     TEXT,
    
    -- Failure modes detected
    failure_modes           JSONB,  -- list[dict] from failure_handling
    
    -- Baseline comparison
    baseline_result         JSONB,  -- Rule-based baseline comparison
    
    -- Model metadata
    model_name              VARCHAR(100),
    
    CONSTRAINT fk_reasoning_perception 
        FOREIGN KEY (perception_id) REFERENCES perception_results(id) ON DELETE CASCADE
);

CREATE INDEX idx_reasoning_perception ON reasoning_results(perception_id);
CREATE INDEX idx_reasoning_run ON reasoning_results(pipeline_run_id);
CREATE INDEX idx_reasoning_probability ON reasoning_results(probability);
CREATE INDEX idx_reasoning_driver ON reasoning_results(dominant_driver);

COMMENT ON TABLE reasoning_results IS 'Stage 2 output: ML inference, baseline comparison, failure detection';
```

#### 3.2.3 evaluation_results — Stage 3: EvaluationAgent Output

```sql
-- filepath: schema/30_evaluation_results.sql
CREATE TABLE evaluation_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reasoning_id            UUID NOT NULL REFERENCES reasoning_results(id) ON DELETE CASCADE,
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID,
    
    agent_name              VARCHAR(20) DEFAULT 'EvaluationAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- Core evaluation fields
    system_status           VARCHAR(20) NOT NULL,  -- OK | DEGRADED | CONFLICT | LOW_TRUST
    risk_level              VARCHAR(20) NOT NULL,  -- SAFE | WARNING | DANGER | UNKNOWN
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- Data quality
    data_freshness_minutes  DECIMAL(8, 2),
    
    -- Risk assessment
    dominant_risk_driver    VARCHAR(50),
    risk_interpretation     TEXT,
    recommended_action      JSONB,  -- list[str]
    
    -- Failure tracking
    failure_modes           JSONB,  -- list[dict] with penalties
    
    -- Baseline check
    baseline_check          JSONB,
    
    -- Manual review decision
    requires_manual_review     BOOLEAN NOT NULL,
    requires_manual_review_reason VARCHAR(500),
    requires_manual_review_meta JSONB,
    
    -- Trust breakdown (Task 5)
    trust_breakdown         JSONB,  -- TrustBreakdown dataclass
    
    -- Decision engine output
    decision                JSONB,  -- DecisionResult
    
    -- BNPB InaRISK integration
    bnpb_active             BOOLEAN,
    bnpb_status             JSONB,  -- Gate decision
    bnpb_influence          JSONB,
    bnpb_attribution        JSONB,
    bnpb_trace              JSONB,  -- list[str]
    
    -- Hydrology carried forward
    hydrology_assessment    JSONB,
    
    -- Vulnerability context
    vulnerability_context   JSONB,
    mapping_info            JSONB,
    
    -- Novelty detection
    novelty_advisory        VARCHAR(200),
    
    -- Risk state from DecisionCore
    risk_state              JSONB,  -- RiskState dataclass
    
    -- Plausibility summary
    plausibility            JSONB,
    
    CONSTRAINT fk_evaluation_reasoning 
        FOREIGN KEY (reasoning_id) REFERENCES reasoning_results(id) ON DELETE CASCADE
);

CREATE INDEX idx_evaluation_reasoning ON evaluation_results(reasoning_id);
CREATE INDEX idx_evaluation_run ON evaluation_results(pipeline_run_id);
CREATE INDEX idx_evaluation_status ON evaluation_results(system_status);
CREATE INDEX idx_evaluation_risk ON evaluation_results(risk_level);
CREATE INDEX idx_evaluation_confidence ON evaluation_results(confidence_score);

COMMENT ON TABLE evaluation_results IS 'Stage 3 output: trust-weighted assessment with failure penalties';
```

#### 3.2.4 decisions — Stage 4: ActionAgent Output (Final Decision)

```sql
-- filepath: schema/40_decisions.sql
CREATE TABLE decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id           UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID,
    
    -- Decision authority
    _decision_authority     VARCHAR(20),  -- 'EvaluationAgent'
    _authoritative_fields   JSONB,  -- ["risk_level", "confidence_score", "requires_manual_review"]
    
    -- System health
    system_status           VARCHAR(20) NOT NULL,
    requires_manual_review  BOOLEAN NOT NULL,
    
    -- Disambiguation layer
    decision_reason         VARCHAR(20) NOT NULL,  -- RISK | INVALID_INPUT | FALLBACK
    data_validity           VARCHAR(20) NOT NULL,  -- VALID | INVALID
    ml_execution_mode       VARCHAR(20) NOT NULL,  -- FULL | SHADOW_ONLY
    
    -- Core decision
    risk_level              VARCHAR(20) NOT NULL,
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- Explainability
    trace                   TEXT,
    explanation             TEXT,
    decision_explanation    TEXT,
    
    -- Failure modes
    failure_modes           JSONB,  -- list[dict]
    
    -- Routing (if provided)
    safe_route              JSONB,
    tma_data                JSONB,
    
    -- Trend analysis
    trend_analysis          JSONB,
    
    -- BNPB context
    bnpb_advisory           JSONB,
    bnpb_active              BOOLEAN,
    
    -- Additional metadata
    is_safe_for_automation   BOOLEAN NOT NULL,
    requires_manual_review   BOOLEAN NOT NULL,
    
    -- Timestamps
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    decision_timestamp      TIMESTAMPTZ,
    
    CONSTRAINT fk_decisions_evaluation 
        FOREIGN KEY (evaluation_id) REFERENCES evaluation_results(id) ON DELETE CASCADE
);

CREATE INDEX idx_decisions_evaluation ON decisions(evaluation_id);
CREATE INDEX idx_decisions_run ON decisions(pipeline_run_id);
CREATE INDEX idx_decisions_risk ON decisions(risk_level);
CREATE INDEX idx_decisions_status ON decisions(system_status);
CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX idx_decisions_reason ON decisions(decision_reason);

COMMENT ON TABLE decisions IS 'Stage 4 output: final canonical decision report returned to API consumers';
```

---

### 3.3 Trust and Failure Tracking

#### 3.3.1 trust_breakdowns — Three-Factor Trust Scores

```sql
-- filepath: schema/50_trust_breakdowns.sql
CREATE TABLE trust_breakdowns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id           UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    
    -- Three-factor trust decomposition (all 0.0-1.0)
    model_confidence_factor   DECIMAL(5, 4) NOT NULL,
    data_quality_factor       DECIMAL(5, 4) NOT NULL,
    signal_agreement_factor  DECIMAL(5, 4) NOT NULL,
    
    -- Composite score
    composite_trust          DECIMAL(5, 4) NOT NULL,
    is_low_trust             BOOLEAN NOT NULL,
    
    -- Diagnostic
    dominant_trust_issue     VARCHAR(30),  -- weakest factor key
    
    -- Factor weights used (for audit)
    factor_weights           JSONB,  -- {
    --   "model_confidence": 0.45,
    --   "data_quality": 0.35,
    --   "signal_agreement": 0.20
    -- }
    
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT fk_trust_evaluation 
        FOREIGN KEY (evaluation_id) REFERENCES evaluation_results(id) ON DELETE CASCADE
);

CREATE INDEX idx_trust_evaluation ON trust_breakdowns(evaluation_id);
CREATE INDEX idx_trust_composite ON trust_breakdowns(composite_trust);
CREATE INDEX idx_trust_low ON trust_breakdowns(is_low_trust);

COMMENT ON TABLE trust_breakdowns IS 'Three-factor trust decomposition for explainability';
```

#### 3.3.2 failure_logs — Systematic Failure Tracking

```sql
-- filepath: schema/51_failure_logs.sql
CREATE TABLE failure_logs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id         UUID NOT NULL,
    
    -- Failure identification
    failure_type            VARCHAR(50) NOT NULL,  -- missing_data | stale_data | ood | conflict
    severity                VARCHAR(20) NOT NULL,  -- low | medium | high
    
    -- Failure details
    message                 TEXT NOT NULL,
    detail                  JSONB,  -- Flexible detail dict
    
    -- Impact assessment
    confidence_penalty      DECIMAL(5, 4) NOT NULL,
    risk_escalation         BOOLEAN NOT NULL,
    
    -- Source tracking
    detection_stage         VARCHAR(30),  -- perception | reasoning | evaluation
    detection_agent         VARCHAR(30),
    
    -- Temporal data
    detected_at             TIMESTAMPTZ DEFAULT NOW(),
    snapshot_fetched_at     TIMESTAMPTZ,
    
    -- Context
    snapshot_id             UUID REFERENCES snapshots(id),
    
    CONSTRAINT fk_failure_run 
        FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE
);

CREATE INDEX idx_failure_run ON failure_logs(pipeline_run_id);
CREATE INDEX idx_failure_type ON failure_logs(failure_type);
CREATE INDEX idx_failure_severity ON failure_logs(severity);
CREATE INDEX idx_failure_detected ON failure_logs(detected_at DESC);

COMMENT ON TABLE failure_logs IS 'All failures detected across pipeline stages with impact metrics';
```

---

### 3.4 Pipeline Execution Tracking

#### 3.4.1 pipeline_runs — Full Pipeline Execution Log

```sql
-- filepath: schema/60_pipeline_runs.sql
CREATE TABLE pipeline_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Execution metadata
    execution_mode          VARCHAR(20) DEFAULT 'production',  -- production | replay | test
    started_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ,
    execution_time_ms       INTEGER,
    
    -- Input reference
    snapshot_id             UUID REFERENCES snapshots(id),
    
    -- Routing parameters (if provided)
    origin                  VARCHAR(200),
    destination             VARCHAR(200),
    
    -- Output summary
    final_decision          JSONB,  -- Final decision dict
    system_status           VARCHAR(20),
    risk_level              VARCHAR(20),
    confidence_score        DECIMAL(5, 4),
    
    -- Error tracking
    error_stage             VARCHAR(30),
    error_message           TEXT,
    is_emergency_output    BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    api_version             VARCHAR(20),
    pipeline_version        VARCHAR(20),
    
    CONSTRAINT pipeline_runs_completed_check 
        CHECK (completed_at IS NULL OR completed_at > started_at)
);

CREATE INDEX idx_pipeline_runs_started ON pipeline_runs(started_at DESC);
CREATE INDEX idx_pipeline_runs_snapshot ON pipeline_runs(snapshot_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(system_status);
CREATE INDEX idx_pipeline_runs_risk ON pipeline_runs(risk_level);
CREATE INDEX idx_pipeline_runs_execution ON pipeline_runs(execution_mode);

COMMENT ON TABLE pipeline_runs IS 'Complete pipeline execution log for auditing and replay';
```

---

### 3.5 Evaluation and Calibration

#### 3.5.1 calibration_metrics — Model Calibration Tracking

```sql
-- filepath: schema/70_calibration_metrics.sql
CREATE TABLE calibration_metrics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Metric computation context
    computation_period      VARCHAR(20),  -- daily | weekly | monthly
    period_start            DATE NOT NULL,
    period_end              DATE NOT NULL,
    
    -- Sample counts
    total_predictions      INTEGER NOT NULL,
    valid_ground_truth     INTEGER,
    
    -- Calibration scores
    brier_score             DECIMAL(6, 4),
    ece                     DECIMAL(6, 4),  -- Expected Calibration Error
    mce                     DECIMAL(6, 4),  -- Maximum Calibration Error
    
    -- Interpretation
    brier_interpretation    VARCHAR(20),  -- excellent | good | fair | poor
    ece_interpretation      VARCHAR(20),
    
    -- Calibration bins (detailed)
    calibration_bins        JSONB,  -- list[dict] with per-bin metrics
    
    -- Model version
    model_variant           VARCHAR(30),
    model_version_hash      VARCHAR(64),
    
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT calibration_period_unique 
        UNIQUE (computation_period, period_start, model_variant)
);

CREATE INDEX idx_calibration_period ON calibration_metrics(period_start DESC);
CREATE INDEX idx_calibration_model ON calibration_metrics(model_variant);

COMMENT ON TABLE calibration_metrics IS 'Brier score, ECE, MCE tracking over time for model reliability';
```

#### 3.5.2 ground_truth_outcomes — Prediction vs Actual Comparison

```sql
-- filepath: schema/71_ground_truth_outcomes.sql
CREATE TABLE ground_truth_outcomes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Prediction reference
    decision_id             UUID NOT NULL REFERENCES decisions(id),
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id),
    
    -- Ground truth (from historical data)
    event_date              DATE NOT NULL,
    district                VARCHAR(100) NOT NULL,
    
    -- Ground truth labels
    is_known_event          BOOLEAN NOT NULL,
    historical_severity      DECIMAL(5, 4),  -- 0.0-1.0
    severity_class          VARCHAR(20),     -- LOW | MEDIUM | HIGH | EXTREME
    event_count             INTEGER,         -- kelurahan-level sub-events
    
    -- Prediction labels
    predicted_risk          VARCHAR(20),
    predicted_probability   DECIMAL(5, 4),
    actual_outcome          INTEGER,         -- 0 = no flood, 1 = flood
    
    -- Comparison metrics
    prediction_correct      BOOLEAN,  -- Did prediction match actual?
    probability_error       DECIMAL(5, 4),  -- |predicted_probability - actual|
    
    -- Data source
    ground_truth_source     VARCHAR(20),  -- post_event | no_record
    
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT fk_outcome_decision 
        FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
);

CREATE INDEX idx_outcome_decision ON ground_truth_outcomes(decision_id);
CREATE INDEX idx_outcome_event ON ground_truth_outcomes(event_date DESC);
CREATE INDEX idx_outcome_district ON ground_truth_outcomes(district);
CREATE INDEX idx_outcome_prediction ON ground_truth_outcomes(predicted_risk);

COMMENT ON TABLE ground_truth_outcomes IS 'Ground truth vs prediction comparison for model evaluation';
```

---

### 3.6 Replay and Testing

#### 3.6.1 replay_scenarios — Historical Scenario Storage

```sql
-- filepath: schema/80_replay_scenarios.sql
CREATE TABLE replay_scenarios (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Scenario identification
    scenario_name           VARCHAR(200) NOT NULL,
    scenario_description    TEXT,
    scenario_type           VARCHAR(30),  -- historical | synthetic | edge_case
    
    -- Temporal context
    scenario_date           DATE,
    district                VARCHAR(100),
    
    -- Input data
    input_snapshot         JSONB NOT NULL,
    input_hash              VARCHAR(64) NOT NULL,
    
    -- Expected output (for comparison)
    expected_risk           VARCHAR(20),
    expected_probability    DECIMAL(5, 4),
    expected_status         VARCHAR(20),
    
    -- Metadata
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    created_by              VARCHAR(100),
    tags                    JSONB,  -- list[str] for categorization
    
    CONSTRAINT replay_scenarios_hash_unique UNIQUE (input_hash)
);

CREATE INDEX idx_replay_scenarios_name ON replay_scenarios(scenario_name);
CREATE INDEX idx_replay_scenarios_date ON replay_scenarios(scenario_date);
CREATE INDEX idx_replay_scenarios_type ON replay_scenarios(scenario_type);
CREATE INDEX idx_replay_scenarios_hash ON replay_scenarios(input_hash);

COMMENT ON TABLE replay_scenarios IS 'Historical and synthetic scenarios for replay testing';
```

#### 3.6.2 scenario_runs — Replay Execution Results

```sql
-- filepath: schema/81_scenario_runs.sql
CREATE TABLE scenario_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Scenario reference
    scenario_id             UUID NOT NULL REFERENCES replay_scenarios(id) ON DELETE CASCADE,
    
    -- Execution metadata
    run_timestamp           TIMESTAMPTZ NOT NULL,
    execution_time_ms       INTEGER,
    
    -- Actual output
    actual_decision         JSONB NOT NULL,
    actual_risk             VARCHAR(20),
    actual_probability      DECIMAL(5, 4),
    actual_status           VARCHAR(20),
    
    -- Comparison with expected
    risk_match              BOOLEAN,
    probability_error       DECIMAL(5, 4),
    status_match            BOOLEAN,
    
    -- Pass/fail determination
    test_passed             BOOLEAN NOT NULL,
    failure_reason         TEXT,
    
    -- Pipeline version used
    pipeline_version        VARCHAR(20),
    
    CONSTRAINT fk_scenario_run_scenario 
        FOREIGN KEY (scenario_id) REFERENCES replay_scenarios(id) ON DELETE CASCADE
);

CREATE INDEX idx_scenario_run_scenario ON scenario_runs(scenario_id);
CREATE INDEX idx_scenario_run_timestamp ON scenario_runs(run_timestamp DESC);
CREATE INDEX idx_scenario_run_passed ON scenario_runs(test_passed);

COMMENT ON TABLE scenario_runs IS 'Replay test execution results for regression testing';
```

---

### 3.7 Supporting Tables

#### 3.7.1 enums_reference — Enum Value Tracking

```sql
-- filepath: schema/90_enums_reference.sql
CREATE TABLE enums_reference (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Enum category
    enum_type               VARCHAR(30) NOT NULL,  -- risk_level | system_status | etc
    enum_value              VARCHAR(30) NOT NULL,
    enum_description        TEXT,
    
    -- Usage tracking
    first_seen              TIMESTAMPTZ DEFAULT NOW(),
    last_seen               TIMESTAMPTZ DEFAULT NOW(),
    usage_count             INTEGER DEFAULT 1,
    
    CONSTRAINT enums_reference_unique 
        UNIQUE (enum_type, enum_value)
);

CREATE INDEX idx_enums_type ON enums_reference(enum_type);
CREATE INDEX idx_enums_value ON enums_reference(enum_value);

COMMENT ON TABLE enums_reference IS 'Track all enum values used in decisions for validation';
```

#### 3.7.2 api_logs — API Access Tracking

```sql
-- filepath: schema/91_api_logs.sql
CREATE TABLE api_logs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Request identification
    request_id              VARCHAR(100) NOT NULL,
    endpoint                VARCHAR(100) NOT NULL,
    
    -- Request details
    method                  VARCHAR(10),
    request_payload         JSONB,
    
    -- Response details
    response_status         INTEGER,
    response_payload        JSONB,
    response_time_ms        INTEGER,
    
    -- Client information
    client_ip               VARCHAR(45),
    user_agent              TEXT,
    
    -- Pipeline reference
    pipeline_run_id         UUID REFERENCES pipeline_runs(id),
    
    -- Timestamps
    request_timestamp       TIMESTAMPTZ NOT NULL,
    
    CONSTRAINT api_logs_request_unique UNIQUE (request_id)
);

CREATE INDEX idx_api_logs_timestamp ON api_logs(request_timestamp DESC);
CREATE INDEX idx_api_logs_endpoint ON api_logs(endpoint);
CREATE INDEX idx_api_logs_status ON api_logs(response_status);
CREATE INDEX idx_api_logs_pipeline ON api_logs(pipeline_run_id);

COMMENT ON TABLE api_logs IS 'API access log for auditing and performance analysis';
```

---

## 4. Entity Relationship Diagram

### 4.1 ERD (Textual Representation)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              ENTITY RELATIONSHIP DIAGRAM                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  snapshots ─────┬────────────────────┬────────────────────┬────────────────────   │
│  (id, hash)     ││                    ││                    ││                      │
│                 ││                    ││                    ││                      │
│                 ▼▼                    ▼▼                    ▼▼                      │
│  snapshot_sources    perception_results      reasoning_results                     │
│  (snapshot_id)        (snapshot_id)            (perception_id)                      │
│       │                      │                       │                              │
│       │                      ▼                       │                              │
│       │               perception_results            │                              │
│       │                      │                       │                              │
│       │                      ▼                       ▼                              │
│       │               evaluation_results ◄────────────┘                              │
│       │                      │                                                      │
│       │                      ▼                                                      │
│       │               decisions ◄──────────────────────────────────────────        │
│       │                      │                                                      │
│       │                      ▼                                                      │
│       │               trust_breakdowns                                              │
│       │                      │                                                      │
│       │               failure_logs                                                  │
│       │                      │                                                      │
│       ▼                      ▼                                                      │
│  pipeline_runs ◄─────────────┘                                                      │
│       │                                                                           │
│       ▼                                                                           │
│  calibration_metrics ◄────────────────────────────────────────────────             │
│       │                                                                           │
│       ▼                                                                           │
│  ground_truth_outcomes ◄────────────────────────────────────────────                │
│                                                                                      │
│  replay_scenarios ──────► scenario_runs                                             │
│                                                                                      │
│  api_logs ──────────────► pipeline_runs                                             │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Relationship Details

| Parent Table | Child Table | Relationship | On Delete |
|--------------|-------------|--------------|-----------|
| `snapshots` | `snapshot_sources` | 1:N | CASCADE |
| `snapshots` | `perception_results` | 1:N | CASCADE |
| `perception_results` | `reasoning_results` | 1:1 | CASCADE |
| `reasoning_results` | `evaluation_results` | 1:1 | CASCADE |
| `evaluation_results` | `decisions` | 1:1 | CASCADE |
| `evaluation_results` | `trust_breakdowns` | 1:1 | CASCADE |
| `decisions` | `ground_truth_outcomes` | 1:1 | CASCADE |
| `pipeline_runs` | `failure_logs` | 1:N | CASCADE |
| `replay_scenarios` | `scenario_runs` | 1:N | CASCADE |

---

## 5. Gap Analysis: Code vs Database

### 5.1 Data Structures Identified from Code

#### Input Structures (Snapshot)

| Field | Type | Source | Persisted? |
|-------|------|--------|------------|
| `fetched_at_utc` | datetime | Snapshot | ✅ `snapshots.fetched_at_utc` |
| `location` | str | Snapshot | ✅ `snapshots.location` |
| `openweather` | dict | Snapshot | ✅ `snapshots.openweather` |
| `poskobanjir` | list | Snapshot | ✅ `snapshots.poskobanjir` |
| `bmkg_alerts` | list | Snapshot | ✅ `snapshots.bmkg_alerts` |

#### PerceptionResult (PerceptionAgent)

| Field | Type | Persisted? |
|-------|------|------------|
| `snapshot` | dict | ✅ `processed_snapshot` |
| `data_freshness_minutes` | float | ✅ |
| `snapshot_completeness` | float | ✅ |
| `signal_presence` | dict | ✅ |
| `raw_features` | dict | ✅ |
| `plausibility_score` | float | ✅ |
| `plausibility` | dict | ✅ |
| `hydrology_assessment` | HydrologyAssessment | ✅ |
| `perception_warnings` | list | ✅ |
| `vulnerability_context` | VulnerabilityContext | ✅ |
| `mapping_info` | dict | ✅ |

#### ReasoningResult (ReasoningAgent)

| Field | Type | Persisted? |
|-------|------|------------|
| `features` | dict | ✅ |
| `diagnostics` | dict | ✅ |
| `prediction` | dict | ✅ |
| `signals` | dict | ✅ |
| `dominant_driver` | str | ✅ |
| `context_summary` | dict | ✅ |
| `risk_interpretation` | str | ✅ |
| `failure_modes` | list | ✅ |
| `baseline_result` | dict | ✅ |

#### EvaluationResult (EvaluationAgent)

| Field | Type | Persisted? |
|-------|------|------------|
| `system_status` | str | ✅ |
| `risk_level` | str | ✅ |
| `probability` | float | ✅ |
| `confidence_score` | float | ✅ |
| `failure_modes` | list | ✅ |
| `requires_manual_review` | bool | ✅ |
| `trust_breakdown` | TrustBreakdown | ✅ |
| `decision` | DecisionResult | ✅ |
| `bnpb_status` | dict | ✅ |
| `bnpb_influence` | dict | ✅ |
| `risk_state` | RiskState | ✅ |

#### Decision Output (ActionAgent)

| Field | Type | Persisted? |
|-------|------|------------|
| `decision` | str | ✅ |
| `confidence_score` | float | ✅ |
| `system_status` | str | ✅ |
| `trace` | str | ✅ |
| `explanation` | str | ✅ |
| `failure_modes` | list | ✅ |
| `safe_route` | dict | ✅ |
| `tma_data` | dict | ✅ |
| `trend_analysis` | dict | ✅ |

### 5.2 Missing Persistence Points

| # | Data Structure | Current State | Recommendation |
|---|----------------|----------------|-----------------|
| 1 | **Trend analysis data** | Stored in-memory only | Add `trend_history` table |
| 2 | **Adaptive threshold state** | Not persisted | Add `threshold_history` table |
| 3 | **Model calibration cache** | JSON file only | Already in `calibration_metrics` |
| 4 | **Feature baselines** | JSON file only | Add `feature_baselines` table |
| 5 | **Routing cache** | In-memory only | Add `routing_cache` table |

### 5.3 Redundant Data Duplication

| # | Issue | Location | Recommendation |
|---|-------|----------|-----------------|
| 1 | Full snapshot stored in both `snapshots` and `perception_results` | `processed_snapshot` | Consider storing only hash reference |
| 2 | Decision fields duplicated in `pipeline_runs.final_decision` | Denormalization for quick queries | Acceptable for read performance |

### 5.4 Fields That Should Be Normalized

| # | Field | Current | Recommended |
|---|-------|---------|-------------|
| 1 | `enum values` (risk_level, system_status, etc.) | Inline strings | Use foreign key to `enums_reference` |
| 2 | `failure_modes` | JSONB array | Normalize to `failure_logs` table |
| 3 | `signal_presence` | JSONB | Could be separate table for querying |

---

## 6. Performance Optimizations

### 6.1 Recommended Indexes

```sql
-- Composite indexes for common query patterns
CREATE INDEX idx_decisions_risk_time ON decisions(risk_level, created_at DESC);
CREATE INDEX idx_evaluation_trust_time ON evaluation_results(confidence_score, executed_at DESC);
CREATE INDEX idx_pipeline_status_time ON pipeline_runs(system_status, started_at DESC);

-- Partial indexes for specific statuses
CREATE INDEX idx_decisions_danger ON decisions(risk_level) WHERE risk_level = 'DANGER';
CREATE INDEX idx_pipeline_failures ON pipeline_runs(id) WHERE error_message IS NOT NULL;

-- Covering indexes for frequently joined queries
CREATE INDEX idx_perception_run_include ON perception_results(pipeline_run_id) 
    INCLUDE (snapshot_id, data_freshness_minutes, risk_level);
```

### 6.2 Partitioning Strategy

```sql
-- Time-based partitioning for large tables
CREATE TABLE pipeline_runs (
    -- ... columns ...
) PARTITION BY RANGE (started_at);

-- Monthly partitions
CREATE TABLE pipeline_runs_2026_04 PARTITION OF pipeline_runs
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE pipeline_runs_2026_05 PARTITION OF pipeline_runs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

### 6.3 Materialized Views for Common Queries

```sql
-- Daily decision summary
CREATE MATERIALIZED VIEW daily_decision_summary AS
SELECT 
    DATE(created_at) as decision_date,
    risk_level,
    COUNT(*) as decision_count,
    AVG(confidence_score) as avg_confidence,
    SUM(CASE WHEN requires_manual_review THEN 1 ELSE 0 END) as manual_review_count
FROM decisions
GROUP BY DATE(created_at), risk_level
WITH DATA;

-- Refresh strategy
CREATE UNIQUE INDEX idx_daily_summary_date ON daily_decision_summary(decision_date);

-- Auto-refresh (optional)
-- ALTER MATERIALIZED VIEW daily_decision_summary 
--     REFRESH MATERIALIZED VIEW CONCURRENTLY;
```

---

## 7. Audit and Compliance

### 7.1 Audit Trail Implementation

```sql
-- Audit trigger for sensitive tables
CREATE OR REPLACE FUNCTION audit_decisions()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_by)
    VALUES (
        'decisions',
        NEW.id,
        TG_OP,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD ELSE NULL END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW ELSE NULL END,
        current_user
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_decisions
    AFTER INSERT OR UPDATE ON decisions
    FOR EACH ROW EXECUTE FUNCTION audit_decisions();
```

### 7.2 Data Retention Policy

```sql
-- Retention policy (example: 2 years)
CREATE POLICY retention_policy ON pipeline_runs
    USING (started_at > NOW() - INTERVAL '2 years');

-- Archive old data to cold storage
-- SELECT * FROM pipeline_runs 
-- WHERE started_at < NOW() - INTERVAL '2 years'
-- ORDER BY archival TO 's3://cold-storage/pipeline_runs/';
```

---

## 8. Summary

### 8.1 Tables Created

| # | Table Name | Purpose | Rows (Est.) |
|---|------------|---------|-------------|
| 1 | `snapshots` | Raw input data | ~1M/year |
| 2 | `snapshot_sources` | Source tracking | ~3M/year |
| 3 | `perception_results` | Stage 1 output | ~1M/year |
| 4 | `reasoning_results` | Stage 2 output | ~1M/year |
| 5 | `evaluation_results` | Stage 3 output | ~1M/year |
| 6 | `decisions` | Final output | ~1M/year |
| 7 | `trust_breakdowns` | Trust scores | ~1M/year |
| 8 | `failure_logs` | Failure tracking | ~100K/year |
| 9 | `pipeline_runs` | Execution log | ~1M/year |
| 10 | `calibration_metrics` | Model metrics | ~365/year |
| 11 | `ground_truth_outcomes` | Outcome tracking | ~100/year |
| 12 | `replay_scenarios` | Test scenarios | ~1000 |
| 13 | `scenario_runs` | Test results | ~10K/year |
| 14 | `enums_reference` | Enum tracking | ~50 |
| 15 | `api_logs` | API access log | ~10M/year |

### 8.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **UUID primary keys** | Distributed system, no central ID server |
| **JSONB for flexible fields** | Schema evolution, nested structures |
| **Time-based partitioning** | Data lifecycle management, query performance |
| **Foreign key constraints** | Data integrity, cascade deletes |
| **Materialized views** | Common aggregations, reduced query load |

### 8.3 Implementation Priority

| Priority | Tables | Reason |
|----------|--------|--------|
| **P0 (Must)** | `snapshots`, `decisions`, `pipeline_runs` | Core traceability |
| **P1 (Should)** | `perception_results`, `reasoning_results`, `evaluation_results` | Full audit trail |
| **P2 (Could)** | `calibration_metrics`, `ground_truth_outcomes` | Model improvement |
| **P3 (Nice)** | `replay_scenarios`, `scenario_runs` | Testing automation |

---

*Schema design completed by Senior Database Engineer*  
*27 April 2026*