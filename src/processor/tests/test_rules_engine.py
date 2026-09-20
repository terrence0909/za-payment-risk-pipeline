"""
Unit tests for the SARB FinSurv compliance rules engine.
Run with: pytest src/processor/tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rules_engine import ComplianceRulesEngine, Severity

engine = ComplianceRulesEngine()


def base_txn(**overrides):
    """Clean passing transaction — override fields to trigger specific rules."""
    txn = {
        "transaction_id":    "TXN-TEST-001",
        "amount_zar":        50_000.0,
        "currency":          "GBP",
        "bop_category_code": "101",
        "beneficiary_country": "GBR",
        "swift_bic":         "BARCGB22",
        "ada_ytd_used":      100_000.0,
        "ada_limit":         1_000_000.0,
        "entity_type":       "INDIVIDUAL",
        "is_resident":       True,
    }
    txn.update(overrides)
    return txn


# ── ADA limit breach ───────────────────────────────────────────────

def test_ada_limit_breach_triggers():
    txn    = base_txn(ada_ytd_used=950_000, amount_zar=100_000)
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "ADA_LIMIT_BREACH" in ids
    assert result.risk_band == "CRITICAL"
    assert result.requires_sar is True

def test_ada_limit_breach_company_exempt():
    txn    = base_txn(ada_ytd_used=950_000, amount_zar=100_000, entity_type="COMPANY")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "ADA_LIMIT_BREACH" not in ids

def test_ada_within_limit_passes():
    txn    = base_txn(ada_ytd_used=100_000, amount_zar=50_000)
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "ADA_LIMIT_BREACH" not in ids


# ── ADA approach warning ───────────────────────────────────────────

def test_ada_approach_warning_triggers():
    txn    = base_txn(ada_ytd_used=870_000, amount_zar=50_000)
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "ADA_APPROACH_WARNING" in ids


# ── BOP code ──────────────────────────────────────────────────────

def test_invalid_bop_code_triggers():
    txn    = base_txn(bop_category_code="999")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "INVALID_BOP_CODE" in ids

def test_valid_bop_code_passes():
    for code in ["101", "201", "301", "502", "601"]:
        txn    = base_txn(bop_category_code=code)
        result = engine.evaluate(txn)
        ids    = [v.rule_id for v in result.violations]
        assert "INVALID_BOP_CODE" not in ids, f"Code {code} should be valid"


# ── Currency ──────────────────────────────────────────────────────

def test_invalid_currency_triggers():
    txn    = base_txn(currency="XYZ")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "INVALID_CURRENCY" in ids

def test_valid_currency_passes():
    txn    = base_txn(currency="USD")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "INVALID_CURRENCY" not in ids


# ── Sanctioned corridor ────────────────────────────────────────────

def test_sanctioned_corridor_triggers():
    txn    = base_txn(beneficiary_country="IRN")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "SANCTIONED_CORRIDOR" in ids
    assert result.requires_sar is True

def test_safe_corridor_passes():
    txn    = base_txn(beneficiary_country="GBR")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "SANCTIONED_CORRIDOR" not in ids


# ── FATF grey list ────────────────────────────────────────────────

def test_fatf_grey_list_warning():
    txn     = base_txn(beneficiary_country="NGA")
    result  = engine.evaluate(txn)
    warn_ids = [w.rule_id for w in result.warnings]
    assert "FATF_GREY_LIST" in warn_ids


# ── Large individual transfer ──────────────────────────────────────

def test_large_individual_transfer_triggers():
    txn    = base_txn(amount_zar=600_000, entity_type="INDIVIDUAL")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "LARGE_INDIVIDUAL_TRANSFER" in ids

def test_large_company_transfer_exempt():
    txn    = base_txn(amount_zar=600_000, entity_type="COMPANY")
    result = engine.evaluate(txn)
    ids    = [v.rule_id for v in result.violations]
    assert "LARGE_INDIVIDUAL_TRANSFER" not in ids


# ── Round amount pattern ──────────────────────────────────────────

def test_round_amount_triggers():
    txn     = base_txn(amount_zar=200_000)
    result  = engine.evaluate(txn)
    warn_ids = [w.rule_id for w in result.warnings]
    assert "ROUND_AMOUNT_PATTERN" in warn_ids

def test_non_round_amount_passes():
    txn     = base_txn(amount_zar=123_456)
    result  = engine.evaluate(txn)
    warn_ids = [w.rule_id for w in result.warnings]
    assert "ROUND_AMOUNT_PATTERN" not in warn_ids


# ── SWIFT BIC ────────────────────────────────────────────────────

def test_malformed_bic_triggers():
    txn     = base_txn(swift_bic="BADCODE")
    result  = engine.evaluate(txn)
    warn_ids = [w.rule_id for w in result.warnings]
    assert "MALFORMED_SWIFT_BIC" in warn_ids

def test_valid_bic_passes():
    for bic in ["BARCGB22", "ABSAZAJJ", "CHASUS33"]:
        txn     = base_txn(swift_bic=bic)
        result  = engine.evaluate(txn)
        warn_ids = [w.rule_id for w in result.warnings]
        assert "MALFORMED_SWIFT_BIC" not in warn_ids, f"BIC {bic} should be valid"


# ── Company/individual BOP mismatch ──────────────────────────────

def test_company_individual_bop_mismatch():
    txn     = base_txn(entity_type="COMPANY", bop_category_code="101")
    result  = engine.evaluate(txn)
    warn_ids = [w.rule_id for w in result.warnings]
    assert "COMPANY_INDIVIDUAL_BOP_MISMATCH" in warn_ids


# ── Risk scoring ──────────────────────────────────────────────────

def test_clean_transaction_scores_low():
    txn    = base_txn()
    result = engine.evaluate(txn)
    assert result.risk_score <= 25
    assert result.risk_band == "LOW"
    assert result.passed is True

def test_multiple_violations_score_critical():
    txn    = base_txn(
        ada_ytd_used=950_000,
        amount_zar=100_000,
        beneficiary_country="IRN",
        bop_category_code="999",
    )
    result = engine.evaluate(txn)
    assert result.risk_score == 100
    assert result.risk_band == "CRITICAL"
    assert result.requires_sar is True
