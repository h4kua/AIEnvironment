-- Migration: 100_vocabulary_sync.sql
-- Description: Aligns ALL DB CHECK constraints with the canonical vocabulary
--              defined in app/contracts/vocabulary.py. Replaces the narrower
--              CHECKs from 003/006/007/019/020/021 with the unified 6-value
--              SystemStatus and 5-value RiskLevel enums (adds LOW_TRUST,
--              CONFLICT, PIPELINE_FAILURE, PRE_ALERT, UNKNOWN where missing)
--              and aligns dominant_driver with the canonical Driver enum.
-- Created: 2026-05-04
-- Idempotent (DROP IF EXISTS + ADD inside DO/EXCEPTION).
-- Numbered 100 to leave gap 023..099 for any further structural migrations.
-- Hand-edited until scripts/generate_check_constraints.py is created; then
-- this file becomes auto-generated.

BEGIN;

-- ===========================================================================
-- system_status — canonical 6 values: OK, DEGRADED, LOW_TRUST, CONFLICT,
--                                     FAIL, PIPELINE_FAILURE
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS eval_status_chk;
    ALTER TABLE evaluation_results ADD CONSTRAINT eval_status_chk
        CHECK (system_status IN ('OK','DEGRADED','LOW_TRUST','CONFLICT','FAIL','PIPELINE_FAILURE'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_status_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_status_chk
        CHECK (system_status IN ('OK','DEGRADED','LOW_TRUST','CONFLICT','FAIL','PIPELINE_FAILURE'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_status_chk;
    ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_status_chk
        CHECK (system_status IS NULL OR system_status IN
               ('OK','DEGRADED','LOW_TRUST','CONFLICT','FAIL','PIPELINE_FAILURE'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- risk_level — canonical 5 values: SAFE, PRE_ALERT, WARNING, DANGER, UNKNOWN
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS eval_risk_chk;
    ALTER TABLE evaluation_results ADD CONSTRAINT eval_risk_chk
        CHECK (risk_level IN ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_risk_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_risk_chk
        CHECK (risk_level IN ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_risk_chk;
    ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_risk_chk
        CHECK (risk_level IS NULL OR risk_level IN
               ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- dominant_driver / dominant_risk_driver — canonical 12-value Driver enum
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE reasoning_results DROP CONSTRAINT IF EXISTS reasoning_driver_chk;
    ALTER TABLE reasoning_results ADD CONSTRAINT reasoning_driver_chk
        CHECK (dominant_driver IS NULL OR dominant_driver IN (
            'extreme_rainfall','sustained_heavy_rainfall','high_rainfall',
            'atmospheric_buildup','bmkg_confirmed_alert','bmkg_forecast_alert',
            'critical_hydrology','hydrology_stress','hydrology_unverified',
            'compound_event','low_background_risk','pipeline_error'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS evaluation_driver_chk;
    ALTER TABLE evaluation_results ADD CONSTRAINT evaluation_driver_chk
        CHECK (dominant_risk_driver IS NULL OR dominant_risk_driver IN (
            'extreme_rainfall','sustained_heavy_rainfall','high_rainfall',
            'atmospheric_buildup','bmkg_confirmed_alert','bmkg_forecast_alert',
            'critical_hydrology','hydrology_stress','hydrology_unverified',
            'compound_event','low_background_risk','pipeline_error'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- decision_reason — canonical 6 values
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_reason_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_reason_chk
        CHECK (decision_reason IN
               ('RISK','INVALID_INPUT','FALLBACK','PHYSICAL_GATE','MULTI_SIGNAL','TREND_EXTENSION'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- _decision_authority — canonical 6 L-levels
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_authority_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_authority_chk
        CHECK (_decision_authority IS NULL OR _decision_authority IN
               ('L0_PHYSICAL','L1_SIAGA','L1_5_MULTI','L2_INTEGRITY','L3_ML','L4_TREND'));
EXCEPTION WHEN others THEN NULL; END $$;

COMMIT;
