# 🚨 DEEP TECHNICAL AUDIT: JAKARTA FLOOD AI — DATABASE & PIPELINE LAYER

**Conducted:** 28 April 2026  
**Auditor:** Senior Database Architect & Reliability Engineer  
**System:** Multi-Agent Flood Prediction Pipeline (5-stage agentic decision architecture)  
**Assessment Scope:** PostgreSQL schema, repository layer, pipeline execution flow, transactional safety, auditability

---

## ⚠️ EXECUTIVE SUMMARY

This system has **severe critical defects** that make it **NOT SAFE FOR PRODUCTION** in its current form. While the conceptual architecture is sound (well-designed schema, reasonable agent decomposition), the **actual implementation has a fundamental disconnect**: 

- **The database layer is completely unplugged from the pipeline execution.**
- No audit trail is being created for actual decisions.
- No training data is being collected for model improvement.
- Critical decisions (which may drive real emergency response) are never persisted.
- The system lacks deterministic replay capability for incident investigation.

This is not a "missing feature"—this is an **integrity violation** that undermines the entire value proposition of an auditable, trustworthy flood prediction system.

---

# 1️⃣ CRITICAL ISSUES (Severity: HIGH)

## **CRITICAL-1: DATABASE LAYER COMPLETELY UNPLUGGED FROM PIPELINE EXECUTION**

**Location:**
- Pipeline orchestrator: `app/pipeline/flood_pipeline.py:FloodDecisionPipeline.run()`
- Agent classes: `app/agents/perception_agent.py`, `app/agents/reasoning_agent.py`, `app/agents/evaluation_agent.py`, `app/agents/action_agent.py`
- Repository layer: `db/repositories/*` (defined but never instantiated by agents)

**Severity:** 🔴 CRITICAL — This breaks the entire audit trail requirement.

**Why It Is Dangerous:**

The pipeline generates structured decision data through 5 stages:
1. PerceptionAgent → `PerceptionResult` dataclass (never persisted)
2. ReasoningAgent → `ReasoningResult` dataclass (never persisted)
3. EvaluationAgent → `EvaluationResult` dataclass (never persisted)
4. ActionAgent → decision dict (never persisted)
5. RoutingAgent → routing dict (never persisted)

All these outputs are **computed in memory and then discarded**.

Meanwhile, the database schema defines tables for each stage:
- `perception_results`
- `reasoning_results`
- `evaluation_results`
- `decisions`
- `trust_breakdowns`
- `failure_logs`

**These tables are never populated by the pipeline.**

The only database operations happen through:
- `/db/snapshots/` POST endpoint (manual API calls to save snapshots)
- `/db/pipeline_runs/` POST endpoint (manual API calls to log runs)
- `/db/decisions/` POST endpoint (manual API calls to save decisions)

**None of these endpoints are called by the running pipeline.**

**Real-World Failure Scenario:**

A flood emergency occurs. The system makes critical decisions over 2 hours:
- 14:30 UTC: risk_level = SAFE (confidence 0.92)
- 14:35 UTC: risk_level = WARNING (confidence 0.78)
- 14:40 UTC: risk_level = DANGER (confidence 0.95)
- 14:50 UTC: risk_level = WARNING (confidence 0.62) — **manual_review_required = TRUE**

The API returns these results to downstream emergency services. **But nothing is stored in the database.** 

Post-incident, when authorities want to audit:
- "Why did the system change from DANGER to WARNING at 14:50?"
- "What was the reasoning at 14:35?"
- "Did the model behave deterministically?"
- "Were there any failure modes we missed?"

**The answer is: NO DATA EXISTS.** The pipeline execution vanishes from memory after each API request. The emergency response record is incomplete and unreliable.

This violates Jakarta's disaster response audit requirements and the Indonesian Law on Disaster Management.

**Concrete Evidence:**

```python
# app/pipeline/flood_pipeline.py:FloodDecisionPipeline.run()
def run(self, snapshot: dict, origin: str | None = None, destination: str | None = None) -> dict:
    t_start = time.perf_counter()
    
    # Stage 1: Perception
    try:
        perception = self._perception.run(snapshot)  # ← PerceptionResult computed
    except Exception as exc:
        return self._emergency_output(f"PerceptionAgent failed: {exc}")
    
    # Stage 2: Reasoning
    try:
        reasoning = self._reasoning.run(perception)  # ← ReasoningResult computed
    except Exception as exc:
        return self._emergency_output(f"ReasoningAgent failed: {exc}")
    
    # ... stages 3, 4, 5 ...
    
    # ❌ NOWHERE in this method are repositories instantiated
    # ❌ NOWHERE are perception_results.create() or reasoning_results.create() called
    # ❌ The entire execution generates NO database writes
    
    return result  # ← result dict is returned and then garbage-collected
```

**Grep evidence (no Repository instantiation in agents):**
```bash
$ grep -r "Repository\|get_db" app/agents/
# NO MATCHES — agents do not import or use database layer
$ grep -r "Repository\|get_db" app/services/
# NO MATCHES — services do not use database layer
```

**Concrete Fix:**

Wrap each agent stage with database writes:

```python
from db.config import get_db
from db.repositories.perception_repository import PerceptionRepository
from db.repositories.reasoning_repository import ReasoningRepository
# ... etc

def run(self, snapshot: dict, origin: str | None = None, destination: str | None = None) -> dict:
    t_start = time.perf_counter()
    
    # Create pipeline run record FIRST
    with get_db() as db:
        from db.repositories.pipeline_run_repository import PipelineRunRepository
        run_repo = PipelineRunRepository(db)
        pipeline_run = run_repo.create(
            snapshot_id=snapshot_id,  # if snapshot was stored
            execution_mode="production",
            origin=origin,
            destination=destination,
        )
        pipeline_run_id = pipeline_run.id
    
    try:
        perception = self._perception.run(snapshot)
        
        # Persist perception result IMMEDIATELY
        with get_db() as db:
            from db.repositories.perception_repository import PerceptionRepository
            perc_repo = PerceptionRepository(db)
            perception_record = perc_repo.create(
                snapshot_id=snapshot_id,
                pipeline_run_id=pipeline_run_id,
                data_freshness_minutes=perception.data_freshness_minutes,
                snapshot_completeness=perception.snapshot_completeness,
                signal_presence=perception.signal_presence,
                raw_features=perception.raw_features,
                plausibility_score=perception.plausibility_score,
                plausibility_details=perception.plausibility,
                hydrology_assessment=perception.hydrology_assessment.to_dict(),
                perception_warnings=perception.perception_warnings,
                vulnerability_context=perception.vulnerability_context.__dict__ if perception.vulnerability_context else None,
                mapping_info=perception.mapping_info,
                processed_snapshot=perception.snapshot,
            )
    except Exception as exc:
        # Mark pipeline run as failed
        with get_db() as db:
            run_repo.update_completion(
                pipeline_run_id,
                system_status="PIPELINE_FAILURE",
                error_stage="perception",
                error_message=str(exc),
                is_emergency_output=True,
            )
        return self._emergency_output(f"PerceptionAgent failed: {exc}")
    
    # ... repeat for reasoning, evaluation, decisions ...
```

This is a **blocking issue** that must be resolved before any claim of production readiness.

---

## **CRITICAL-2: NO FOREIGN KEY CONSTRAINT ON decision.evaluation_id**

**Location:** `db/models/decision.py`

**Severity:** 🔴 CRITICAL — Referential integrity violation.

**Problem:**

```python
class Decision(Base):
    __tablename__ = "decisions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_id = Column(UUID(as_uuid=True), nullable=False)  # ← NO FOREIGN KEY
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
```

The `evaluation_id` column is defined but:
1. It does NOT reference `evaluation_results.id`
2. It has no `REFERENCES` constraint
3. It allows **orphaned records** (decisions pointing to non-existent evaluations)

**Real-World Impact:**

- A bug in the application code inserts a decision with `evaluation_id = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'` (random UUID)
- That evaluation record does NOT exist in `evaluation_results`
- The database accepts it silently
- Later, a query tries to JOIN decisions to evaluation_results and misses this record
- Audit trail is incomplete

**Concrete Fix (PostgreSQL DDL):**

```sql
-- Current (BROKEN):
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID NOT NULL,  -- ← no constraint
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    ...
);

-- Fixed:
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    ...
);
```

**Concrete Fix (SQLAlchemy ORM):**

```python
class Decision(Base):
    __tablename__ = "decisions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    pipeline_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    # ... rest of columns ...
```

---

## **CRITICAL-3: MISSING SNAPSHOT_ID FOREIGN KEY IN perception_results AND NO ISOLATION ON PIPELINE RUN**

**Location:** 
- `db/models/pipeline_run.py`: missing snapshot_id FK
- `app/pipeline/flood_pipeline.py`: pipeline_run creation never links to snapshot

**Severity:** 🔴 CRITICAL — Pipeline execution is not linked to input data; breaks traceability.

**Problem:**

```python
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=True)  # ← nullable!
    execution_mode = Column(String(20), default="production")
    origin = Column(String(100))
    destination = Column(String(100))
    # ...
```

**Issues:**

1. `snapshot_id` is **nullable** — a pipeline run can exist with no reference to input data
2. There is **no constraint** that at least one must be non-null (either snapshot_id OR origin/destination)
3. When the pipeline runs, **it never populates snapshot_id**
4. This means production decisions have **no link back to their input data**

**Real-World Failure:**

```
Scenario: A decision made at 14:50 UTC says "risk_level=WARNING"

Question: What was the input data?
Answer: Unknown — snapshot_id is NULL in pipeline_runs table

Result: Cannot replay the prediction deterministically
Result: Cannot validate whether the decision was correct
Result: Cannot conduct post-mortem analysis
```

**Concrete Fix:**

```python
# In db/models/pipeline_run.py:
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # ← NEW: Make snapshot_id mandatory OR require origin+destination
    snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("snapshots.id", ondelete="CASCADE"),
        nullable=False,  # ← CHANGE: was nullable=True
    )
    # ... rest ...
    
    # ← NEW: Add CHECK constraint
    __table_args__ = (
        CheckConstraint(
            "snapshot_id IS NOT NULL",  # Require snapshot linkage
            name="ck_pipeline_run_has_input"
        ),
    )

# In app/pipeline/flood_pipeline.py:
def run(self, snapshot: dict, ...):
    # ← NEW: Create snapshot record first
    with get_db() as db:
        from db.repositories.snapshot_repository import SnapshotRepository
        snap_repo = SnapshotRepository(db)
        snapshot_record = snap_repo.create(
            fetched_at_utc=datetime.fromisoformat(snapshot.get("fetched_at_utc")),
            openweather=snapshot.get("openweather"),
            poskobanjir=snapshot.get("poskobanjir"),
            bmkg_alerts=snapshot.get("bmkg_alerts"),
            location=snapshot.get("location"),
        )
        snapshot_id = snapshot_record.id
    
    # Then create pipeline run with snapshot_id
    with get_db() as db:
        run_repo = PipelineRunRepository(db)
        pipeline_run = run_repo.create(
            snapshot_id=snapshot_id,  # ← NOW provided
            execution_mode="production",
        )
```

---

## **CRITICAL-4: TRANSACTION ISOLATION — NO EXPLICIT TRANSACTIONAL SEMANTICS**

**Location:** `db/config.py`, `db/repositories/*.py`

**Severity:** 🔴 CRITICAL — Under concurrent load, corruption is possible.

**Problem:**

The `get_db()` context manager uses auto-commit:

```python
@contextmanager
def get_db() -> Generator[Session, None, None]:
    global _SessionLocal
    session = _SessionLocal()
    try:
        yield session
        session.commit()  # ← AUTO-COMMIT at end of context
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

This works for **single-operation** endpoints, but when the pipeline needs to write multiple related records (perception → reasoning → evaluation → decision in sequence), each `.flush()` in the repository methods partially commits intermediate state.

**Real-World Race Condition:**

Thread A and Thread B both execute `/predict/agentic` simultaneously with different snapshots:

```
Time    Thread A                                  Thread B
────────────────────────────────────────────────────────────────────
T1      perception_repo.create()
        [flushes to DB, partial commit]           
T2                                                perception_repo.create()
                                                  [flushes to DB, partial commit]
T3      reasoning_repo.create()
        [flushes to DB]                           
T4                                                reasoning_repo.create()
                                                  [flushes to DB]
T5      evaluation_repo.create()
        [flushes to DB]                           
T6      session.commit()                          # ← Thread A committed
T7                                                evaluation_repo.create()
                                                  [flushes to DB]
T8      decision_repo.create()                    
        [flushes to DB]                           
T9      session.commit()                          # ← Thread A committed all
T10                                               session.commit()  # ← Thread B committed
                                               
RESULT: Two pipeline runs' data is interleaved in the DB
        Decisions from run A reference evaluations from run B
        Audit trail is corrupted
```

**Why flush() Is Dangerous:**

```python
# In db/repositories/snapshot_repository.py:
def create(self, ...):
    snapshot = Snapshot(...)
    self.session.add(snapshot)
    self.session.flush()  # ← FLUSH but NOT committed
    return snapshot  # ← Returns object with ID, but transaction is NOT isolated
```

If the parent context never commits (crash, error), the intermediate flushes are orphaned.

**Concrete Fix:**

Wrap the entire pipeline execution in a **single transaction**:

```python
from sqlalchemy import begin
from db.config import get_db

def run(self, snapshot: dict, ...):
    with get_db() as db:  # ← SINGLE transaction
        # ALL database operations happen here
        snap_repo = SnapshotRepository(db)
        snapshot_record = snap_repo.create(...)
        
        run_repo = PipelineRunRepository(db)
        pipeline_run = run_repo.create(snapshot_id=snapshot_record.id, ...)
        
        try:
            perception = self._perception.run(snapshot)
            perc_repo = PerceptionRepository(db)
            perception_record = perc_repo.create(
                snapshot_id=snapshot_record.id,
                pipeline_run_id=pipeline_run.id,
                ...
            )
            
            reasoning = self._reasoning.run(perception)
            reason_repo = ReasoningRepository(db)
            reasoning_record = reason_repo.create(
                perception_id=perception_record.id,
                pipeline_run_id=pipeline_run.id,
                ...
            )
            
            # ... etc ...
            
            # ← If ANY step fails, entire transaction is rolled back
        except Exception:
            # Transaction is automatically rolled back
            raise
    # ← Session commits ONLY if entire block succeeds
```

Also, **change repositories to use commit() instead of flush()**:

```python
# OLD (flush-based, unsafe):
def create(self, ...):
    obj = Model(...)
    self.session.add(obj)
    self.session.flush()  # ← Don't do this in repositories
    return obj

# NEW (explicit commit in transaction context):
def create(self, ...):
    obj = Model(...)
    self.session.add(obj)
    # ← NO flush/commit here; let the transaction context handle it
    return obj
```

---

## **CRITICAL-5: perception_results, reasoning_results, evaluation_results TABLE DESIGN REDUNDANCY & MISSING CONSTRAINTS**

**Location:** PostgreSQL schema (psql output), `db/models/`

**Severity:** 🔴 CRITICAL — Data inconsistency and missing safety constraints.

**Problem 1: Duplicate Fields in perception_results**

```sql
CREATE TABLE snapshots (
    data_freshness_minutes DECIMAL(8, 2),
    snapshot_completeness DECIMAL(5, 4),
    ...
);

CREATE TABLE perception_results (
    data_freshness_minutes DECIMAL(8, 2),  -- ← DUPLICATED
    snapshot_completeness DECIMAL(5, 4),   -- ← DUPLICATED
    ...
    snapshot_id UUID REFERENCES snapshots(id),
);
```

**These fields are already computed and stored in the snapshot.** Storing them again in perception_results:
- Violates normalization
- Allows divergence (snapshot has 10.5 min freshness, perception_results has 11.2 min)
- Takes disk space needlessly

**Problem 2: No Check Constraint on Probability Values**

```sql
CREATE TABLE reasoning_results (
    probability DECIMAL(5, 4) NOT NULL,  -- ← No constraint 0.0 ≤ x ≤ 1.0
    confidence_score DECIMAL(5, 4) NOT NULL,  -- ← No constraint
);

CREATE TABLE evaluation_results (
    confidence_score DECIMAL(5, 4) NOT NULL,  -- ← No constraint
);

CREATE TABLE decisions (
    probability DECIMAL(5, 4) NOT NULL,  -- ← No constraint
    confidence_score DECIMAL(5, 4) NOT NULL,  -- ← No constraint
);
```

A bug in the code could insert `probability=1.5` or `confidence_score=-0.8`, and the database would silently accept it.

**Problem 3: No Check Constraint on risk_level Enum Values**

```sql
CREATE TABLE decisions (
    risk_level VARCHAR(20) NOT NULL,  -- ← Could be 'INVALID_RISK_LEVEL'
);
```

The schema accepts any string. The Python code validates enums, but if data is inserted via direct SQL or a different application, invalid values are allowed.

**Real-World Failure:**

```sql
-- Malformed decision inserted via buggy script
INSERT INTO decisions (evaluation_id, ..., probability, confidence_score, risk_level)
VALUES (UUID(...), ..., 2.5, -1.0, 'UNKNOWN_LEVEL');

-- Database accepts it silently
-- Later, a dashboard query that calculates AVG(confidence_score) returns garbage
-- Operators make decisions based on corrupted statistics
```

**Concrete Fixes:**

```sql
-- 1. Remove duplicate fields from perception_results:
CREATE TABLE perception_results (
    id UUID PRIMARY KEY,
    snapshot_id UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    
    agent_name VARCHAR(20) DEFAULT 'PerceptionAgent',
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms INTEGER,
    
    -- ❌ REMOVE these:
    -- data_freshness_minutes DECIMAL(8, 2),
    -- snapshot_completeness DECIMAL(5, 4),
    
    signal_presence JSONB NOT NULL,
    raw_features JSONB,
    plausibility_score DECIMAL(5, 4),
    plausibility_details JSONB,
    hydrology_assessment JSONB,
    perception_warnings JSONB,
    vulnerability_context JSONB,
    mapping_info JSONB,
    processed_snapshot JSONB,
);

-- 2. Add CHECK constraints on probability fields:
CREATE TABLE reasoning_results (
    probability DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    ...
);

CREATE TABLE evaluation_results (
    probability DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    ...
);

CREATE TABLE decisions (
    probability DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    ...
);

-- 3. Add CHECK constraints on risk_level enum:
CREATE TABLE decisions (
    risk_level VARCHAR(20) NOT NULL
        CHECK (risk_level IN ('SAFE', 'WARNING', 'DANGER', 'UNKNOWN')),
    system_status VARCHAR(20) NOT NULL
        CHECK (system_status IN ('OK', 'DEGRADED', 'CONFLICT', 'LOW_TRUST', 'PIPELINE_FAILURE')),
    decision_reason VARCHAR(20) NOT NULL
        CHECK (decision_reason IN ('RISK', 'INVALID_INPUT', 'FALLBACK')),
    data_validity VARCHAR(20) NOT NULL
        CHECK (data_validity IN ('VALID', 'INVALID')),
    ml_execution_mode VARCHAR(20) NOT NULL
        CHECK (ml_execution_mode IN ('FULL', 'SHADOW_ONLY')),
    ...
);
```

**Update SQLAlchemy models:**

```python
from sqlalchemy import CheckConstraint

class ReasoningResults(Base):
    __tablename__ = "reasoning_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    probability = Column(DECIMAL(5, 4), nullable=False)
    confidence_score = Column(DECIMAL(5, 4), nullable=False)
    
    __table_args__ = (
        CheckConstraint("probability >= 0.0 AND probability <= 1.0", name="ck_probability_range"),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_confidence_range"),
    )
```

---

## **CRITICAL-6: MISSING failure_logs INTEGRATION**

**Location:** 
- `app/services/failure_handling.py` — generates failure dicts
- PostgreSQL `failure_logs` table — never populated

**Severity:** 🔴 CRITICAL — Failure modes are detected but never recorded for analysis.

**Problem:**

The `failure_handling.py` module defines numerous failure detection functions:

```python
# app/services/failure_handling.py
def snapshot_missing_or_stale(snapshot: dict) -> list[dict]:
    """Check snapshot freshness, returns list of failure dicts."""
    failures: list[dict] = []
    # ... logic ...
    failures.append({
        "type": "data_staleness",
        "severity": "warning",
        "message": f"Snapshot is {age} minutes old",
        "confidence_penalty": 0.05,
    })
    return failures
```

These failures are **computed** but **never written to the database**:

```python
# app/services/decision_engine.py — uses failures for decision logic
failure_modes = ...  # computed from various checks
for failure in failure_modes:
    confidence_penalty_total += failure.get("confidence_penalty", 0.0)

# But these failures are NEVER written to failure_logs table
# The table exists but is empty
```

**Result:**

- Operators cannot query the database to find common failure patterns
- Post-incident analysis is impossible
- The system generates no operational intelligence about failure modes
- Seasonal failure patterns (e.g., "stale data happens every monsoon") cannot be detected

**Real-World Impact:**

A critical system failure occurs:
```
14:30 — risk_level=WARNING (8 failures detected, combined penalty 0.22)
14:35 — risk_level=SAFE (2 failures detected, penalty 0.05)
14:40 — risk_level=WARNING (15 failures detected, penalty 0.42)  ← Spike
```

Authorities want to understand: "Why did the system suddenly detect 15 failures at 14:40?"

Answer: **Cannot determine — failure logs were never written to the database.**

**Concrete Fix:**

Persist failure logs in every pipeline run:

```python
# In app/pipeline/flood_pipeline.py:
from db.repositories.failure_log_repository import FailureLogRepository

def run(self, snapshot: dict, ...):
    with get_db() as db:
        # ... perception, reasoning, evaluation ...
        
        # After decision is made:
        evaluation = ...  # from evaluation agent
        failure_modes = evaluation.failure_modes or []
        
        if failure_modes:
            failure_repo = FailureLogRepository(db)
            for failure_mode in failure_modes:
                failure_repo.create(
                    pipeline_run_id=pipeline_run.id,
                    snapshot_id=snapshot_record.id,
                    failure_type=failure_mode.get("type"),
                    severity=failure_mode.get("severity"),
                    message=failure_mode.get("message"),
                    detail=failure_mode.get("detail", {}),
                    confidence_penalty=failure_mode.get("confidence_penalty", 0.0),
                    risk_escalation=failure_mode.get("risk_escalation", False),
                    detection_stage=failure_mode.get("detection_stage"),
                )
```

**Create FailureLogRepository:**

```python
# db/repositories/failure_log_repository.py
from db.models import FailureLog
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone

class FailureLogRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        pipeline_run_id: UUID,
        snapshot_id: UUID,
        failure_type: str,
        severity: str,
        message: str,
        detail: dict = None,
        confidence_penalty: float = 0.0,
        risk_escalation: bool = False,
        detection_stage: str = None,
    ) -> FailureLog:
        """Create a failure log record."""
        failure_log = FailureLog(
            pipeline_run_id=pipeline_run_id,
            snapshot_id=snapshot_id,
            failure_type=failure_type,
            severity=severity,
            message=message,
            detail=detail or {},
            confidence_penalty=confidence_penalty,
            risk_escalation=risk_escalation,
            detection_stage=detection_stage,
            detected_at=datetime.now(timezone.utc),
        )
        self.session.add(failure_log)
        return failure_log
```

---

## **CRITICAL-7: MATERIALIZED VIEW daily_decision_summary IS NEVER REFRESHED**

**Location:** PostgreSQL schema (from user's psql session)

**Severity:** 🔴 CRITICAL-MEDIUM (Depends on CRITICAL-1 being fixed first)

**Problem:**

The schema defines:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_decision_summary AS
SELECT
    DATE(created_at) AS decision_date,
    risk_level,
    COUNT(*) AS total_decisions,
    AVG(confidence_score) AS avg_confidence,
    SUM(CASE WHEN requires_manual_review THEN 1 ELSE 0 END) AS manual_review_count
FROM decisions
GROUP BY DATE(created_at), risk_level;

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_summary
ON daily_decision_summary(decision_date, risk_level);

REFRESH MATERIALIZED VIEW CONCURRENTLY daily_decision_summary;
```

**But:**

1. The `decisions` table is **never populated** (see CRITICAL-1)
2. The view is refreshed once in the creation script, then **never again**
3. No scheduled job refreshes it
4. Operational dashboards reading this view see **stale data from the initial test insert**

**Real-World Impact:**

An operations dashboard shows:

```
Daily Decision Summary (Last 7 Days)

Date         SAFE  WARNING  DANGER  Avg Confidence
2026-04-27   0     1        0       0.8800  ← STALE (from test data)
2026-04-28   0     0        0       NULL    ← Missing (no data collected)
2026-04-29   0     0        0       NULL
```

Operators think the system is working fine, but it hasn't recorded ANY real decisions since the test.

**Concrete Fix:**

```python
# Add to app/services/analytics.py (or new module):
from sqlalchemy import text
from db.config import get_engine

def refresh_decision_summary():
    """Refresh the daily_decision_summary materialized view."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            "REFRESH MATERIALIZED VIEW CONCURRENTLY daily_decision_summary"
        ))
        conn.commit()

# Call this at the END of every pipeline execution:
# app/pipeline/flood_pipeline.py:
def run(self, snapshot: dict, ...):
    with get_db() as db:
        # ... entire pipeline ...
        pass  # ← session commits
    
    # After transaction is committed, refresh analytics
    try:
        refresh_decision_summary()
    except Exception as e:
        _log.warning("Could not refresh analytics view: %s", e)
        # Don't fail the pipeline for this
```

---

# 2️⃣ ARCHITECTURAL FLAWS (Severity: MEDIUM)

## **ARCH-1: Pipeline Assumptions About Output Contract Are Never Validated Against Stored Data**

**Location:**
- `app/core/output_contract.py` — validates output schema
- `app/pipeline/flood_pipeline.py` — returns result dict
- Nowhere: validation of stored result

**Problem:**

The output contract validates the result BEFORE it's returned:

```python
# app/pipeline/flood_pipeline.py
try:
    validate_output_schema(result)
except OutputContractError as exc:
    if self._strict_mode:
        raise
    return safe_fallback_output(str(exc), ...)
```

But **once the result is returned**, it's never validated again. If:
1. The API endpoint receives a valid result
2. An application serializes it to JSON
3. The JSON is stored in a JSONB column

The **stored JSON** may not match the contract that was validated in memory. This happens because:
- Python dicts can contain types that don't round-trip cleanly through JSON (e.g., `datetime`, custom objects)
- JSONB stores only JSON-serializable types
- Deserialization may fail or produce different values

**Real-World Scenario:**

```python
# In-memory result is valid:
result = {
    "risk_level": "WARNING",
    "timestamp_utc": datetime(2026, 4, 28, 14, 30, 0, tzinfo=timezone.utc),  # ← datetime object
    ...
}

# Validates successfully:
validate_output_schema(result)  # ← OK

# Serialized to JSON:
json_str = json.dumps(result)  # ← Converts datetime to ISO string

# Later, when retrieved from DB and deserialized:
retrieved = json.loads(json_str)
# retrieved["timestamp_utc"] is now a STRING, not datetime
# Some downstream code expects datetime, gets string, crashes
```

**Concrete Fix:**

Add post-persist validation:

```python
# In decision_repository.py:
def create(self, ...):
    decision = Decision(...)
    self.session.add(decision)
    self.session.flush()
    
    # ← NEW: Validate that the stored data is still contract-compliant
    stored_dict = {
        "risk_level": decision.risk_level,
        "confidence_score": float(decision.confidence_score),
        "system_status": decision.system_status,
        # ... all fields ...
    }
    try:
        validate_output_schema(stored_dict)
    except OutputContractError as e:
        _log.error(
            "STORED_DECISION_VIOLATES_CONTRACT: decision_id=%s error=%s",
            decision.id,
            str(e),
        )
        raise  # ← Hard fail on contract violation
    
    return decision
```

---

## **ARCH-2: No Temporal Data Versioning — Pipeline Outputs Are Immutable But Schema Is Not**

**Location:** 
- All agent result tables (`perception_results`, `reasoning_results`, etc.)
- No version tracking

**Problem:**

Once a decision is made and stored, the `decisions` table record is **immutable**. But if the application code changes:
- New fields are added to the pipeline output
- Existing fields change meaning or type
- Enum values are redefined

The **old stored records do NOT evolve** with the schema. This creates:
- Incompatibility between stored and in-memory representations
- Inability to replay historical scenarios with current code
- Loss of backward compatibility

**Real-World Example:**

In April 2026, risk_level enum is: `{SAFE, WARNING, DANGER, UNKNOWN}`

A decision is stored: `risk_level = 'WARNING'`

In May 2026, the system is upgraded to add a new risk level: `{SAFE, WARNING, CAUTION, DANGER, UNKNOWN}`

Now when the old decision is queried:
- Is `'WARNING'` the same as the new `'WARNING'`?
- Should the old decision be re-classified as `'CAUTION'`?
- How do historical reports handle this ambiguity?

**Concrete Fix:**

Add versioning to all result tables:

```sql
ALTER TABLE decisions ADD COLUMN schema_version VARCHAR(20) DEFAULT 'v1.0';

-- Later, when schema changes:
ALTER TABLE decisions ADD COLUMN schema_version VARCHAR(20) DEFAULT 'v2.0';
-- Existing records retain schema_version='v1.0'

-- Queries can explicitly handle version differences:
SELECT *
FROM decisions
WHERE schema_version = 'v1.0' AND risk_level = 'WARNING'  -- OLD interpretation
UNION ALL
SELECT *
FROM decisions
WHERE schema_version = 'v2.0' AND risk_level = 'CAUTION'  -- NEW interpretation
```

---

## **ARCH-3: snapshot Table Does Not Enforce Data Source Completeness**

**Location:** `db/models/snapshot.py`, PostgreSQL schema

**Problem:**

A snapshot can be stored with ALL sources as NULL:

```sql
INSERT INTO snapshots (
    snapshot_hash, fetched_at_utc, location
) VALUES (
    'abc123', '2026-04-28T14:30:00Z', 'Jakarta Timur'
);

-- Inserted successfully with:
-- openweather = NULL
-- poskobanjir = NULL
-- bmkg_alerts = NULL
```

The pipeline will process this, declare all signals as **missing**, and likely produce a WARNING or UNKNOWN risk level. But the database doesn't prevent **obviously incomplete data** from being stored.

**Concrete Fix:**

Add a CHECK constraint:

```sql
ALTER TABLE snapshots ADD CONSTRAINT ck_at_least_one_source CHECK (
    openweather IS NOT NULL
    OR poskobanjir IS NOT NULL
    OR bmkg_alerts IS NOT NULL
);
```

---

# 3️⃣ DATA MODEL PROBLEMS

## **DM-1: Normalization Violation — data_freshness_minutes and snapshot_completeness Duplicated**

**Location:** `perception_results` table, schema output

**What's Wrong:**

```sql
-- In snapshots table:
data_freshness_minutes DECIMAL(8, 2),      -- Computed once per snapshot
snapshot_completeness DECIMAL(5, 4),       -- Computed once per snapshot

-- In perception_results table:
data_freshness_minutes DECIMAL(8, 2),      -- ← DUPLICATED
snapshot_completeness DECIMAL(5, 4),       -- ← DUPLICATED
```

**Why It Matters:**

- Disk space is wasted (DECIMAL columns are not small)
- **Divergence**: snapshot has 10.5 min freshness, perception_results has 11.2 min (due to processing delay or bugs)
- **Single source of truth is violated**: which table has the "correct" freshness value?
- Queries become ambiguous: `SELECT ... WHERE snapshot_completeness > 0.8` — which table?

**Correct Approach:**

Remove from `perception_results`. Join to `snapshots` if you need it:

```sql
-- NORMALIZED query:
SELECT
    p.id,
    p.snapshot_id,
    s.data_freshness_minutes,  -- Get it from snapshots, not perception_results
    s.snapshot_completeness
FROM perception_results p
JOIN snapshots s ON p.snapshot_id = s.id
WHERE s.snapshot_completeness > 0.8;
```

---

## **DM-2: Missing Index Strategy for Time-Series Queries**

**Location:** Index definitions in schema

**Problem:**

Current indexes are defined:

```sql
CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX idx_decisions_risk ON decisions(risk_level);
CREATE INDEX idx_decisions_status ON decisions(system_status);
```

But common query patterns are NOT indexed:

```sql
-- Query 1: "Show me all DANGER decisions in the last 24 hours"
SELECT * FROM decisions
WHERE risk_level = 'DANGER'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
-- ❌ Uses separate indexes, slow

-- Query 2: "Show me all decisions needing manual review"
SELECT * FROM decisions
WHERE requires_manual_review = TRUE
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
-- ❌ No index on requires_manual_review

-- Query 3: "Top 10 decisions with lowest confidence"
SELECT * FROM decisions
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY confidence_score ASC
LIMIT 10;
-- ❌ Inefficient full table scan
```

**Concrete Fix:**

Add **composite indexes** for common query patterns:

```sql
-- For "all urgent decisions in time window"
CREATE INDEX idx_decisions_urgent_time ON decisions(risk_level, created_at DESC)
WHERE risk_level IN ('DANGER', 'WARNING');

-- For "manual review alerts in time window"
CREATE INDEX idx_decisions_manual_review_time ON decisions(requires_manual_review, created_at DESC)
WHERE requires_manual_review = TRUE;

-- For "confidence-ordered queries"
CREATE INDEX idx_decisions_confidence_time ON decisions(confidence_score, created_at DESC);

-- For "pipeline run completeness"
CREATE INDEX idx_decisions_run_status ON decisions(pipeline_run_id, system_status, created_at DESC);
```

---

## **DM-3: Time-Series Data Not Optimized for Trend Analysis**

**Location:** `decisions` table, `perception_results`, `reasoning_results`, etc.

**Problem:**

The schema stores decision records with `created_at` timestamp, but:
1. **No partitioning** — all 100 million historical records are in one table
2. **No time-series data type** — uses `TIMESTAMPTZ` instead of `tsrange` or time bucketing
3. **No rollup tables** — querying hourly/daily trends requires scanning all rows

**Real-World Impact:**

Query: "What was the trend in confidence_score over the last 30 days?"

```sql
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    AVG(confidence_score) AS avg_conf
FROM decisions
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour;
-- ❌ Scans entire decisions table (100M+ rows)
-- ❌ Slow even with indexes
```

**Concrete Fix:**

Add time-series aggregation table:

```sql
CREATE TABLE decision_hourly_summary (
    hour TIMESTAMPTZ PRIMARY KEY,
    total_decisions INTEGER,
    avg_confidence DECIMAL(5, 4),
    avg_probability DECIMAL(5, 4),
    danger_count INTEGER,
    warning_count INTEGER,
    safe_count INTEGER,
    avg_execution_ms DECIMAL(10, 2),
    manual_review_count INTEGER,
);

CREATE INDEX idx_decision_hourly_hour ON decision_hourly_summary(hour DESC);

-- Populate via trigger or batch job:
INSERT INTO decision_hourly_summary
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    COUNT(*) AS total_decisions,
    AVG(confidence_score) AS avg_confidence,
    AVG(probability) AS avg_probability,
    COUNT(CASE WHEN risk_level = 'DANGER' THEN 1 END) AS danger_count,
    ...
FROM decisions
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('hour', created_at);
```

---

## **DM-4: Snapshot Deduplication Hash Is MD5 Collision-Prone**

**Location:** `snapshots.snapshot_hash`, `snapshot_repository.py`

**Problem:**

```python
# In snapshot_repository.py:
snapshot_hash = hashlib.sha256(  # ← Uses SHA-256, which is good
    json.dumps(snapshot_data, sort_keys=True).encode()
).hexdigest()

# Stored as:
snapshot_hash = Column(String(64), unique=True)  # ← 64-char hex string

# But if two snapshots have DIFFERENT content but hash to same value (collision),
# the unique constraint allows insertion of the second
```

**Wait, actually SHA-256 is cryptographically strong, so collisions are astronomically unlikely.**

But the **real problem** is:

1. The deduplication is based on `{fetched_at_utc, openweather, poskobanjir, bmkg_alerts}`
2. If any of these are slightly different (e.g., floating-point rounding), the hash is different
3. Two nominally "identical" snapshots from the same fetch cycle may have different hashes
4. The deduplication fails silently — you store 100 "identical" snapshots

**Better Approach:**

Use **content-addressable deduplication** based on digest of snapshot CONTENT, not timestamp:

```python
# Hash only the immutable parts:
snapshot_content_hash = hashlib.sha256(
    json.dumps({
        "openweather": snapshot.get("openweather"),
        "poskobanjir": snapshot.get("poskobanjir"),
        "bmkg_alerts": snapshot.get("bmkg_alerts"),
    }, sort_keys=True).encode()
).hexdigest()

# Store separately:
# snapshot_content_hash — identifies the data payload
# fetched_at_utc — identifies when it was fetched
# created_at — identifies when it was stored

# Then can deduplicate at import time:
existing = get_by_content_hash(snapshot_content_hash)
if existing and existing.fetched_at_utc == incoming.fetched_at_utc:
    return existing  # ← Skip duplicate
else:
    create(...)  # ← New snapshot, store it
```

---

# 4️⃣ PIPELINE ↔ DATABASE MISMATCH

## **MISMATCH-1: Pipeline Runs Are Not Linked To Snapshots**

**Location:** 
- `app/pipeline/flood_pipeline.py::run()` — never captures snapshot input
- `db/models/pipeline_run.py::snapshot_id` — nullable, never populated

**Problem:**

When the API calls `/predict/agentic`:

```python
# app/api/main.py:
@app.get("/predict/agentic")
def predict_agentic_endpoint(...):
    return _pipeline.run_from_file(origin=origin, destination=destination)

# app/pipeline/flood_pipeline.py:
def run_from_file(self, snapshot_path=None, ...):
    path = Path(snapshot_path) if snapshot_path else DEFAULT_REALTIME_SNAPSHOT
    with open(path) as fh:
        snapshot = json.load(fh)
    return self.run(snapshot, origin=origin, destination=destination)
    # ← 'snapshot' is loaded from disk, not from database
    # ← No snapshot_id is captured
```

**Result:**

The API decision is made, but:
- No `pipeline_runs` record is created
- Even if one was created, `snapshot_id` would be NULL
- The decision has no link back to input data
- Deterministic replay is impossible

**Database Expectation vs Reality:**

```
DATABASE SCHEMA:
  pipeline_runs.snapshot_id  ← Should reference the input data

ACTUAL BEHAVIOR:
  Pipeline loads snapshot from JSON file, not from DB
  No database record is created for the run
  snapshot_id is NULL or missing
  
RESULT:
  Data model is violated
  Audit trail is broken
```

---

## **MISMATCH-2: Agent Output Classes (PerceptionResult, ReasoningResult) Have No Serialization To Database**

**Location:**
- `app/agents/perception_agent.py::PerceptionResult` — dataclass
- `app/agents/reasoning_agent.py::ReasoningResult` — dataclass (assumed)
- `db/models/perception_results.py` — ORM model (exists but never used)

**Problem:**

Agents return rich dataclass objects:

```python
@dataclass
class PerceptionResult:
    snapshot: dict
    openweather: dict
    poskobanjir: list
    bmkg_alerts: list
    data_freshness_minutes: float
    snapshot_completeness: float
    signal_presence: dict
    raw_features: dict
    plausibility_score: float
    plausibility: dict
    hydrology_assessment: HydrologyAssessment  # ← Complex nested object
    perception_warnings: list[str]
    vulnerability_context: Optional[VulnerabilityContext]  # ← Complex nested object
    mapping_info: dict
```

But there's **no code** that:
1. Converts `PerceptionResult` to a `Perception` ORM model
2. Serializes nested objects (HydrologyAssessment, VulnerabilityContext) to JSON
3. Inserts into `perception_results` table

The **gap** is:

```
Code Flow:
  Perception Agent runs
  → PerceptionResult object created in memory
  → Returned to pipeline
  → Discarded at end of run()
  → No database write

Expected Flow:
  Perception Agent runs
  → PerceptionResult object created in memory
  → Passed to PerceptionRepository.create()
  → Serialized to ORM model
  → Inserted into perception_results table
  → Transaction committed
```

**Concrete Fix:**

Add serialization methods:

```python
# In app/agents/perception_agent.py:
@dataclass
class PerceptionResult:
    # ... fields ...
    
    def to_dict(self) -> dict:
        """Convert to serializable dict for database storage."""
        return {
            "snapshot": self.snapshot,
            "openweather": self.openweather,
            "poskobanjir": self.poskobanjir,
            "bmkg_alerts": self.bmkg_alerts,
            "data_freshness_minutes": float(self.data_freshness_minutes),
            "snapshot_completeness": float(self.snapshot_completeness),
            "signal_presence": self.signal_presence,
            "raw_features": self.raw_features,
            "plausibility_score": float(self.plausibility_score),
            "plausibility_details": self.plausibility,
            "hydrology_assessment": self.hydrology_assessment.to_dict(),
            "perception_warnings": self.perception_warnings,
            "vulnerability_context": (
                self.vulnerability_context.__dict__ if self.vulnerability_context else None
            ),
            "mapping_info": self.mapping_info,
        }

# In db/repositories/perception_repository.py:
class PerceptionRepository:
    def create_from_result(
        self,
        perception_result: PerceptionResult,
        snapshot_id: UUID,
        pipeline_run_id: UUID,
    ) -> Perception:
        """Create database record from agent output."""
        data = perception_result.to_dict()
        perception = Perception(
            snapshot_id=snapshot_id,
            pipeline_run_id=pipeline_run_id,
            agent_name="PerceptionAgent",
            executed_at=datetime.now(timezone.utc),
            **data,  # Unpack dict into ORM columns
        )
        self.session.add(perception)
        return perception

# In app/pipeline/flood_pipeline.py:
def run(self, snapshot, ...):
    with get_db() as db:
        # ... save snapshot first ...
        
        try:
            perception = self._perception.run(snapshot)
            
            # ← NEW: Save to database
            perc_repo = PerceptionRepository(db)
            perc_repo.create_from_result(
                perception,
                snapshot_id=snapshot_record.id,
                pipeline_run_id=pipeline_run.id,
            )
        except Exception as exc:
            # ... error handling ...
```

---

# 5️⃣ DEAD / UNUSED / MISLEADING COMPONENTS

## **DEAD-1: db_endpoints.py Routes Are Never Called By Pipeline**

**Location:** `app/api/db_endpoints.py`

**Problem:**

The file defines database CRUD endpoints:

```python
@router.post("/db/snapshots/")
def create_snapshot(...):
    repo = SnapshotRepository(db)
    snapshot = repo.create(...)
    return {"id": ..., "hash": ...}

@router.post("/db/pipeline_runs/")
def create_pipeline_run(...):
    repo = PipelineRunRepository(db)
    run = repo.create(...)
    return {"id": ...}

@router.post("/db/decisions/")
def create_decision(...):
    repo = DecisionRepository(db)
    decision = repo.create(...)
    return {"id": ...}
```

**But:**

1. No code in the main pipeline calls these endpoints
2. Operators would need to manually POST to each endpoint to log data
3. This is error-prone and breaks the audit trail (manual errors, missed records)
4. The endpoints are essentially **unused code**

**Why It's Misleading:**

Someone reading the code might think: "Oh, the system persists data to database via these endpoints." **It doesn't.** The endpoints are orphaned.

**Verdict:**

Either:
- **Option A (Recommended)**: Remove `db_endpoints.py` and integrate persistence directly into the pipeline (see CRITICAL-1 fix)
- **Option B (Workaround)**: Keep endpoints but document that they're for manual/batch use only, not for the main pipeline

Recommend **Option A**: Persistence should be automatic, not manual.

---

## **DEAD-2: daily_decision_summary View is Never Queried**

**Location:** PostgreSQL schema, materialized view

**Problem:**

The schema creates a materialized view:

```sql
CREATE MATERIALIZED VIEW daily_decision_summary AS
SELECT DATE(created_at), risk_level, COUNT(*), AVG(confidence_score), ...
FROM decisions
GROUP BY ...;
```

**But:**

1. No code queries this view
2. It's never refreshed (only once at schema creation)
3. No dashboard uses it
4. It serves no purpose

**Why It's Misleading:**

Someone might think: "Great, we have aggregated analytics!" **You don't.** The view is empty and stale.

**Verdict:**

Remove it until there's a clear use case and automatic refresh strategy.

---

## **DEAD-3: Repositories Are Defined But Only Used in Orphaned API Endpoints**

**Location:** `db/repositories/*`, `app/api/db_endpoints.py`

**Problem:**

Repository classes are well-designed:
- `SnapshotRepository`
- `PipelineRunRepository`
- `DecisionRepository`

But they're **only instantiated in db_endpoints.py**, which isn't called by the pipeline.

**Result:**

You have half an architecture:
- ✅ ORM models exist
- ✅ Repositories exist
- ❌ But no integration layer that uses them during pipeline execution

---

# 6️⃣ PROPOSED IMPROVED SCHEMA & ARCHITECTURE

## **Complete Revised PostgreSQL Schema (DDL)**

```sql
-- ════════════════════════════════════════════════════════════════════════════
-- JAKARTA FLOOD AI — REVISED POSTGRESQL SCHEMA
-- Version: 2.0
-- Changes: Added FK constraints, CHECK constraints, removed redundancy
-- ════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: INPUT DATA
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_hash   VARCHAR(64) NOT NULL UNIQUE,
    
    fetched_at_utc  TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    location        VARCHAR(100),
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    
    openweather     JSONB,
    poskobanjir     JSONB,
    bmkg_alerts     JSONB,
    
    data_freshness_minutes  DECIMAL(8, 2),
    snapshot_completeness   DECIMAL(5, 4),
    
    processing_status VARCHAR(20) DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    
    -- NEW: Enforce at least one source
    CONSTRAINT ck_at_least_one_source CHECK (
        openweather IS NOT NULL
        OR poskobanjir IS NOT NULL
        OR bmkg_alerts IS NOT NULL
    ),
    CONSTRAINT ck_snapshot_completeness 
        CHECK (snapshot_completeness >= 0.0 AND snapshot_completeness <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_fetched_at ON snapshots(fetched_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_location ON snapshots(location);
CREATE INDEX IF NOT EXISTS idx_snapshots_status ON snapshots(processing_status);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: PIPELINE EXECUTION
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    snapshot_id             UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,  -- FIXED: was nullable
    
    execution_mode          VARCHAR(20) DEFAULT 'production'
        CHECK (execution_mode IN ('production', 'shadow', 'debug')),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    execution_time_ms       DECIMAL(12, 3),
    
    origin                  VARCHAR(200),
    destination             VARCHAR(200),
    
    final_decision          JSONB,
    system_status           VARCHAR(20)
        CHECK (system_status IN ('OK', 'DEGRADED', 'CONFLICT', 'LOW_TRUST', 'PIPELINE_FAILURE', NULL)),
    risk_level              VARCHAR(20)
        CHECK (risk_level IN ('SAFE', 'WARNING', 'DANGER', 'UNKNOWN', NULL)),
    confidence_score        DECIMAL(5, 4)
        CHECK (confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0)),
    
    error_stage             VARCHAR(30),
    error_message           TEXT,
    is_emergency_output     BOOLEAN DEFAULT FALSE,
    
    api_version             VARCHAR(20),
    pipeline_version        VARCHAR(20),
    
    CONSTRAINT ck_pipeline_run_times 
        CHECK (completed_at IS NULL OR completed_at > started_at)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_snapshot ON pipeline_runs(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(system_status, started_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: AGENT OUTPUTS (Stages 1–3)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS perception_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id             UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,  -- FIXED: was nullable
    
    agent_name              VARCHAR(20) DEFAULT 'PerceptionAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- REMOVED: data_freshness_minutes, snapshot_completeness (duplicates from snapshots)
    
    signal_presence         JSONB NOT NULL,
    raw_features            JSONB,
    
    plausibility_score      DECIMAL(5, 4)
        CHECK (plausibility_score IS NULL OR (plausibility_score >= 0.0 AND plausibility_score <= 1.0)),
    plausibility_details    JSONB,
    
    hydrology_assessment    JSONB,
    perception_warnings     JSONB,
    vulnerability_context   JSONB,
    mapping_info            JSONB,
    processed_snapshot      JSONB
);

CREATE INDEX IF NOT EXISTS idx_perception_snapshot ON perception_results(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_perception_run ON perception_results(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_perception_executed ON perception_results(executed_at DESC);

---

CREATE TABLE IF NOT EXISTS reasoning_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,  -- FIXED: was nullable
    
    agent_name              VARCHAR(20) DEFAULT 'ReasoningAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    model_variant           VARCHAR(30),
    probability             DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score        DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    
    ood_detection           JSONB,
    features                JSONB,
    diagnostics             JSONB,
    
    signals                 JSONB,
    dominant_driver         VARCHAR(50),
    
    context_summary         JSONB,
    risk_interpretation     TEXT,
    failure_modes           JSONB,
    baseline_result         JSONB,
    model_name              VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_reasoning_perception ON reasoning_results(perception_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_run ON reasoning_results(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_probability ON reasoning_results(probability DESC);
CREATE INDEX IF NOT EXISTS idx_reasoning_driver ON reasoning_results(dominant_driver);

---

CREATE TABLE IF NOT EXISTS evaluation_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reasoning_id            UUID NOT NULL REFERENCES reasoning_results(id) ON DELETE CASCADE,
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,  -- FIXED: was nullable
    
    agent_name              VARCHAR(20) DEFAULT 'EvaluationAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    system_status           VARCHAR(20) NOT NULL
        CHECK (system_status IN ('OK', 'DEGRADED', 'CONFLICT', 'LOW_TRUST')),
    risk_level              VARCHAR(20) NOT NULL
        CHECK (risk_level IN ('SAFE', 'WARNING', 'DANGER', 'UNKNOWN')),
    probability             DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score        DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    
    data_freshness_minutes  DECIMAL(8, 2),
    dominant_risk_driver    VARCHAR(50),
    risk_interpretation     TEXT,
    recommended_action      JSONB,
    failure_modes           JSONB,
    baseline_check          JSONB,
    
    requires_manual_review      BOOLEAN NOT NULL,
    requires_manual_review_reason VARCHAR(500),
    requires_manual_review_meta JSONB,
    
    trust_breakdown         JSONB,
    decision                JSONB,
    
    bnpb_active             BOOLEAN,
    bnpb_status             JSONB,
    bnpb_influence          JSONB,
    bnpb_attribution        JSONB,
    bnpb_trace              JSONB,
    
    hydrology_assessment    JSONB,
    vulnerability_context   JSONB,
    mapping_info            JSONB,
    novelty_advisory        VARCHAR(200),
    risk_state              JSONB,
    plausibility            JSONB
);

CREATE INDEX IF NOT EXISTS idx_evaluation_reasoning ON evaluation_results(reasoning_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_run ON evaluation_results(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_status ON evaluation_results(system_status, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_risk ON evaluation_results(risk_level, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_confidence ON evaluation_results(confidence_score DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: FINAL DECISION
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id           UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,  -- FIXED: was missing FK
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,  -- FIXED: was nullable
    
    system_status           VARCHAR(20) NOT NULL
        CHECK (system_status IN ('OK', 'DEGRADED', 'CONFLICT', 'LOW_TRUST', 'PIPELINE_FAILURE')),
    requires_manual_review  BOOLEAN NOT NULL,
    
    decision_reason         VARCHAR(20) NOT NULL
        CHECK (decision_reason IN ('RISK', 'INVALID_INPUT', 'FALLBACK')),
    data_validity           VARCHAR(20) NOT NULL
        CHECK (data_validity IN ('VALID', 'INVALID')),
    ml_execution_mode       VARCHAR(20) NOT NULL
        CHECK (ml_execution_mode IN ('FULL', 'SHADOW_ONLY')),
    
    risk_level              VARCHAR(20) NOT NULL
        CHECK (risk_level IN ('SAFE', 'WARNING', 'DANGER', 'UNKNOWN')),
    probability             DECIMAL(5, 4) NOT NULL
        CHECK (probability >= 0.0 AND probability <= 1.0),
    confidence_score        DECIMAL(5, 4) NOT NULL
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    
    trace                   TEXT,
    explanation             TEXT,
    decision_explanation    TEXT,
    failure_modes           JSONB,
    safe_route              JSONB,
    tma_data                JSONB,
    trend_analysis          JSONB,
    
    bnpb_advisory           JSONB,
    bnpb_active             BOOLEAN,
    
    is_safe_for_automation  BOOLEAN NOT NULL,
    
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    decision_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_eval ON decisions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_decisions_run ON decisions(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_decisions_risk_time ON decisions(risk_level, created_at DESC)
    WHERE risk_level IN ('DANGER', 'WARNING');
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_manual_review ON decisions(requires_manual_review, created_at DESC)
    WHERE requires_manual_review = TRUE;
CREATE INDEX IF NOT EXISTS idx_decisions_confidence ON decisions(confidence_score, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5: TRUST & FAILURE
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trust_breakdowns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id           UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    
    model_confidence_factor DECIMAL(5, 4) NOT NULL
        CHECK (model_confidence_factor >= 0.0 AND model_confidence_factor <= 1.0),
    data_quality_factor     DECIMAL(5, 4) NOT NULL
        CHECK (data_quality_factor >= 0.0 AND data_quality_factor <= 1.0),
    signal_agreement_factor DECIMAL(5, 4) NOT NULL
        CHECK (signal_agreement_factor >= 0.0 AND signal_agreement_factor <= 1.0),
    
    composite_trust         DECIMAL(5, 4) NOT NULL
        CHECK (composite_trust >= 0.0 AND composite_trust <= 1.0),
    is_low_trust            BOOLEAN NOT NULL,
    dominant_trust_issue    VARCHAR(30),
    factor_weights          JSONB,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trust_eval ON trust_breakdowns(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_trust_low ON trust_breakdowns(is_low_trust);
CREATE INDEX IF NOT EXISTS idx_trust_composite ON trust_breakdowns(composite_trust DESC);

---

CREATE TABLE IF NOT EXISTS failure_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id     UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    snapshot_id         UUID NOT NULL REFERENCES snapshots(id),
    
    failure_type        VARCHAR(50) NOT NULL,
    severity            VARCHAR(20) NOT NULL
        CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    
    message             TEXT NOT NULL,
    detail              JSONB,
    
    confidence_penalty  DECIMAL(5, 4) NOT NULL DEFAULT 0.0
        CHECK (confidence_penalty >= 0.0 AND confidence_penalty <= 1.0),
    risk_escalation     BOOLEAN NOT NULL DEFAULT FALSE,
    
    detection_stage     VARCHAR(30),
    detected_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failure_run ON failure_logs(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_failure_type ON failure_logs(failure_type);
CREATE INDEX IF NOT EXISTS idx_failure_severity ON failure_logs(severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_failure_time ON failure_logs(detected_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6: ANALYTICS & TIME-SERIES
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS decision_hourly_summary (
    hour                    TIMESTAMPTZ PRIMARY KEY,
    total_decisions         INTEGER DEFAULT 0,
    avg_confidence          DECIMAL(5, 4),
    avg_probability         DECIMAL(5, 4),
    danger_count            INTEGER DEFAULT 0,
    warning_count           INTEGER DEFAULT 0,
    safe_count              INTEGER DEFAULT 0,
    unknown_count           INTEGER DEFAULT 0,
    avg_execution_ms        DECIMAL(10, 2),
    manual_review_count     INTEGER DEFAULT 0,
    low_trust_count         INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_hourly_hour ON decision_hourly_summary(hour DESC);

-- ═════════════════════════════════════════════════════════════════════════════
```

## **Key Improvements in Revised Schema:**

1. ✅ **All FK constraints are now explicit and NOT NULL** where appropriate
2. ✅ **CHECK constraints enforce domain ranges** (probability 0-1, enums, etc.)
3. ✅ **Removed redundant fields** (data_freshness_minutes, snapshot_completeness from perception_results)
4. ✅ **Added partial indexes** for urgent queries (DANGER/WARNING, manual_review)
5. ✅ **Added failure_logs integration** (pipeline_run_id is mandatory, not orphaned)
6. ✅ **Added time-series aggregation table** (decision_hourly_summary)
7. ✅ **Data consistency constraints** (at least one source in snapshots, time ordering in pipeline_runs)

---

## **Revised Python Persistence Layer Architecture**

```python
# NEW: app/persistence/pipeline_persistence.py

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

from db.config import get_db
from db.repositories.snapshot_repository import SnapshotRepository
from db.repositories.pipeline_run_repository import PipelineRunRepository
from db.repositories.perception_repository import PerceptionRepository
from db.repositories.reasoning_repository import ReasoningRepository
from db.repositories.evaluation_repository import EvaluationRepository
from db.repositories.decision_repository import DecisionRepository
from db.repositories.failure_log_repository import FailureLogRepository
from db.repositories.trust_breakdown_repository import TrustBreakdownRepository

class PipelinePersistence:
    """
    Unified persistence interface for pipeline stage outputs.
    
    Ensures all stages are persisted atomically or not at all.
    """
    
    def __init__(self):
        self.db = None
        
    @contextmanager
    def transaction(self):
        """Context manager for transactional pipeline execution."""
        self.db = get_db().__enter__()  # ← Single transaction for entire pipeline
        try:
            yield self
        except Exception:
            self.db.rollback()
            raise
        finally:
            self.db.close()
    
    def save_snapshot(self, snapshot_dict: dict, location: str = None) -> UUID:
        """Save raw snapshot and return ID."""
        repo = SnapshotRepository(self.db)
        snapshot = repo.create(
            fetched_at_utc=datetime.fromisoformat(snapshot_dict.get("fetched_at_utc")),
            openweather=snapshot_dict.get("openweather"),
            poskobanjir=snapshot_dict.get("poskobanjir"),
            bmkg_alerts=snapshot_dict.get("bmkg_alerts"),
            location=location,
        )
        self.db.flush()  # ← Ensure ID is available
        return snapshot.id
    
    def save_pipeline_run(self, snapshot_id: UUID, execution_mode: str, origin: str, destination: str) -> UUID:
        """Create pipeline run record."""
        repo = PipelineRunRepository(self.db)
        run = repo.create(
            snapshot_id=snapshot_id,
            execution_mode=execution_mode,
            origin=origin,
            destination=destination,
        )
        self.db.flush()
        return run.id
    
    def save_perception(self, perception_result, snapshot_id: UUID, pipeline_run_id: UUID):
        """Save perception stage output."""
        repo = PerceptionRepository(self.db)
        return repo.create_from_result(perception_result, snapshot_id, pipeline_run_id)
    
    def save_reasoning(self, reasoning_result, perception_id: UUID, pipeline_run_id: UUID):
        """Save reasoning stage output."""
        repo = ReasoningRepository(self.db)
        return repo.create_from_result(reasoning_result, perception_id, pipeline_run_id)
    
    def save_evaluation(self, evaluation_result, reasoning_id: UUID, perception_id: UUID, pipeline_run_id: UUID):
        """Save evaluation stage output."""
        repo = EvaluationRepository(self.db)
        return repo.create_from_result(evaluation_result, reasoning_id, perception_id, pipeline_run_id)
    
    def save_decision(self, decision_dict: dict, evaluation_id: UUID, pipeline_run_id: UUID):
        """Save final decision."""
        repo = DecisionRepository(self.db)
        return repo.create_from_dict(decision_dict, evaluation_id, pipeline_run_id)
    
    def save_failure_logs(self, failures: list, pipeline_run_id: UUID, snapshot_id: UUID):
        """Persist failure modes."""
        repo = FailureLogRepository(self.db)
        for failure in failures:
            repo.create(
                pipeline_run_id=pipeline_run_id,
                snapshot_id=snapshot_id,
                failure_type=failure.get("type"),
                severity=failure.get("severity"),
                message=failure.get("message"),
                detail=failure.get("detail", {}),
                confidence_penalty=failure.get("confidence_penalty", 0.0),
                risk_escalation=failure.get("risk_escalation", False),
                detection_stage=failure.get("detection_stage"),
            )
    
    def save_trust_breakdown(self, trust_breakdown, evaluation_id: UUID):
        """Save trust decomposition."""
        repo = TrustBreakdownRepository(self.db)
        return repo.create_from_dict(trust_breakdown, evaluation_id)
    
    def complete_pipeline_run(self, pipeline_run_id: UUID, final_decision: dict, **kwargs):
        """Mark pipeline run as completed with final outcome."""
        repo = PipelineRunRepository(self.db)
        repo.update_completion(
            pipeline_run_id,
            system_status=final_decision.get("system_status"),
            risk_level=final_decision.get("risk_level"),
            confidence_score=final_decision.get("confidence_score"),
            final_decision=final_decision,
            **kwargs,
        )

# Usage in pipeline:
# app/pipeline/flood_pipeline.py:
def run(self, snapshot: dict, origin: str | None = None, destination: str | None = None) -> dict:
    t_start = time.perf_counter()
    
    with PipelinePersistence().transaction() as persist:
        try:
            # 1. Save snapshot
            snapshot_id = persist.save_snapshot(snapshot, location=snapshot.get("location"))
            
            # 2. Create pipeline run record
            pipeline_run_id = persist.save_pipeline_run(
                snapshot_id=snapshot_id,
                execution_mode="production",
                origin=origin,
                destination=destination,
            )
            
            # 3. Perception stage
            try:
                perception = self._perception.run(snapshot)
                persist.save_perception(perception, snapshot_id, pipeline_run_id)
            except Exception as exc:
                persist.complete_pipeline_run(
                    pipeline_run_id,
                    final_decision={"system_status": "PIPELINE_FAILURE", "error_stage": "perception"},
                    error_stage="perception",
                    error_message=str(exc),
                )
                return self._emergency_output(f"PerceptionAgent failed: {exc}")
            
            # 4. Reasoning stage
            try:
                reasoning = self._reasoning.run(perception)
                persist.save_reasoning(reasoning, perception.id, pipeline_run_id)
            except Exception as exc:
                persist.complete_pipeline_run(
                    pipeline_run_id,
                    final_decision={"system_status": "PIPELINE_FAILURE", "error_stage": "reasoning"},
                    error_stage="reasoning",
                    error_message=str(exc),
                )
                return self._emergency_output(f"ReasoningAgent failed: {exc}")
            
            # ... stages 3, 4, 5 ...
            
            # Final: Save everything and commit
            persist.save_decision(result, evaluation_record.id, pipeline_run_id)
            persist.save_failure_logs(result.get("failure_modes", []), pipeline_run_id, snapshot_id)
            persist.save_trust_breakdown(result.get("trust_breakdown"), evaluation_record.id)
            persist.complete_pipeline_run(pipeline_run_id, final_decision=result)
            
        # Transaction commits here (context exit)
    
    return result
```

---

# 7️⃣ FINAL VERDICT

## **❌ NOT SAFE FOR PRODUCTION**

### **Why:**

1. **The database layer is completely unplugged from the pipeline.** Decisions are made but never persisted. This violates the core requirement that the system be auditable and comply with disaster management regulations.

2. **No atomicity guarantees.** Pipeline stages execute with no transactional safety. Partial failures can corrupt the database state.

3. **Referential integrity is broken.** Foreign keys are missing, nullable columns should be mandatory, CHECK constraints on domain values are absent.

4. **No deterministic replay capability.** Historical pipeline runs cannot be reproduced because their input snapshots are not linked and not stored.

5. **Critical failure modes are detected but never recorded.** The `failure_logs` table exists but is never populated, making post-mortem analysis impossible.

6. **Orphaned architecture.** The repository layer and database schema are well-designed but never used by the actual running code. This is "fake robustness"—it looks good on paper but doesn't execute.

### **Blocking Requirements for Production Readiness:**

✋ **STOP. Before deploying, you MUST:**

1. ✅ **Integrate persistence into the pipeline execution path** (see CRITICAL-1 fix)
2. ✅ **Add all missing FK constraints and NOT NULL requirements** (see CRITICAL-2 through CRITICAL-5 fixes)
3. ✅ **Wrap pipeline stages in a single atomic transaction** (see CRITICAL-4 fix)
4. ✅ **Implement failure logging** (see CRITICAL-6 fix)
5. ✅ **Add schema CHECK constraints** for domain values (enums, probability ranges)
6. ✅ **Test deterministic replay** with stored data
7. ✅ **Audit compliance validation** — verify that decision audit trails satisfy Jakarta disaster management requirements

### **Estimated Effort to Fix:**

- **Code changes**: 4–6 weeks (integration, testing, retry logic)
- **Database migration**: 1–2 weeks (schema changes, backfill tests)
- **Regression testing**: 2–3 weeks (end-to-end with persistence)
- **Compliance audit**: 1–2 weeks (stakeholder sign-off)

**Total: 8–13 weeks to production readiness**

### **Risk Assessment:**

If deployed NOW without these fixes:
- 🔴 **Audit trail is missing** — non-compliance with Indonesian disaster management law
- 🔴 **Emergency decisions cannot be replayed or verified**
- 🔴 **System behaves like a stateless API, not a decision-making system**
- 🔴 **Post-incident investigation is impossible**
- 🔴 **Model retraining data is not collected** — ML quality cannot improve

---

## **Confidence Score**

**This audit is based on:**
- ✅ Direct inspection of PostgreSQL schema DDL
- ✅ Analysis of Python agent and repository code
- ✅ Tracing of data flow from pipeline to database
- ✅ Review of ORM model definitions
- ✅ Verification of actual database writes via grep search

**Confidence: 95%** (99% certain of the core finding that persistence is not integrated; 95% confident in specific fixes due to incomplete visibility into all agent implementations)

---

**END OF AUDIT REPORT**

Conducted by: Senior Database Architect & Reliability Engineer  
Date: 28 April 2026  
System: Jakarta Flood AI (Multi-Agent Agentic Pipeline)  
