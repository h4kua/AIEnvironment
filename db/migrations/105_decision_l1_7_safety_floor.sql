-- ============================================================================
-- 105_decision_l1_7_safety_floor.sql
--
-- Extends the vocabulary CHECK constraints on the ``decisions`` table so the
-- new L1.7 BMKG_SAFETY_FLOOR layer can be persisted:
--
--   * decision_reason  gains  'SAFETY_FLOOR'
--   * _decision_authority gains  'L1_7_BMKG_SAFETY_FLOOR'
--
-- Pure constraint widenings: no row data is rewritten, no existing values
-- become invalid. Safe to apply on a live database.
--
-- See app/contracts/vocabulary.py for the canonical enum definitions and
-- app/domain/decision.py for the L1.7 layer that emits these values.
-- ============================================================================

BEGIN;

DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_reason_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_reason_chk
        CHECK (decision_reason IN
               ('RISK','INVALID_INPUT','FALLBACK','PHYSICAL_GATE',
                'MULTI_SIGNAL','TREND_EXTENSION','SAFETY_FLOOR'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_authority_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_authority_chk
        CHECK (_decision_authority IS NULL OR _decision_authority IN
               ('L0_PHYSICAL','L1_SIAGA','L1_5_MULTI','L1_7_BMKG_SAFETY_FLOOR',
                'L2_INTEGRITY','L3_ML','L4_TREND'));
EXCEPTION WHEN others THEN NULL; END $$;

COMMIT;
