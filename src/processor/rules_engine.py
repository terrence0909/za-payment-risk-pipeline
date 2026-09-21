"""
SARB FinSurv Compliance Rules Engine.

Evaluates cross-border payment transactions against South African
Reserve Bank FinSurv reporting obligations and FATF guidelines.

Builds directly on the validation logic from the SARB FinSurv
Blockchain Compliance Pipeline — extended with 7 additional rules
and a weighted risk scoring system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
import re


class Severity(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_WEIGHTS = {
    Severity.LOW:      10,
    Severity.MEDIUM:   25,
    Severity.HIGH:     50,
    Severity.CRITICAL: 100,
}


@dataclass
class RuleResult:
    rule_id:          str
    passed:           bool
    severity:         Severity
    score_contribution: int
    finding:          str
    field_ref:        str = ""


@dataclass
class EngineResult:
    transaction_id:    str
    risk_score:        int
    risk_band:         str
    passed:            bool
    violations:        list = field(default_factory=list)
    warnings:          list = field(default_factory=list)
    rule_count:        int  = 0
    requires_sar:      bool = False
    finsurvreportable: bool = False


# ── SARB-approved BOP category codes ──────────────────────────────
VALID_BOP_CODES = {
    "101", "102", "201", "202", "301", "302",
    "401", "501", "502", "601", "602", "701",
}

# ── SARB-approved currencies ───────────────────────────────────────
VALID_CURRENCIES = {
    "USD", "GBP", "EUR", "CHF", "JPY",
    "AUD", "CAD", "SGD", "AED", "MUR",
    "ZWL", "CNY", "INR",
}

# ── OFAC / UN sanctioned countries ────────────────────────────────
SANCTIONED_COUNTRIES = {"IRN", "PRK", "SYR", "CUB", "VEN"}

# ── FATF grey list ─────────────────────────────────────────────────
FATF_GREY_LIST = {"NGA", "ZWE", "PAK", "ETH", "TZA", "MOZ"}

ADA_LIMIT             = 1_000_000.0
ADA_WARNING_THRESHOLD = 0.85


class ComplianceRulesEngine:
    """
    Stateless rules engine. Pass a transaction dict, get an EngineResult.
    Each rule is an independent method — easy to test, extend, or disable.
    """

    def evaluate(self, txn: dict) -> EngineResult:
        rules: list[Callable[[dict], RuleResult]] = [
            self._rule_ada_limit_breach,
            self._rule_ada_approach_warning,
            self._rule_invalid_bop_code,
            self._rule_invalid_currency,
            self._rule_sanctioned_corridor,
            self._rule_fatf_grey_list,
            self._rule_large_individual_transfer,
            self._rule_round_amount_pattern,
            self._rule_malformed_swift_bic,
            self._rule_company_individual_bop_mismatch,
        ]

        violations = []
        warnings   = []

        for rule_fn in rules:
            result = rule_fn(txn)
            if not result.passed:
                if result.severity in (Severity.CRITICAL, Severity.HIGH):
                    violations.append(result)
                else:
                    warnings.append(result)

        raw_score  = sum(SEVERITY_WEIGHTS[v.severity] for v in violations)
        raw_score += sum(SEVERITY_WEIGHTS[w.severity] * 0.3 for w in warnings)
        risk_score = min(int(raw_score), 100)
        risk_band  = self._band(risk_score)

        return EngineResult(
            transaction_id    = txn.get("transaction_id", "UNKNOWN"),
            risk_score        = risk_score,
            risk_band         = risk_band,
            passed            = len(violations) == 0,
            violations        = violations,
            warnings          = warnings,
            rule_count        = len(rules),
            requires_sar      = any(v.severity == Severity.CRITICAL for v in violations),
            finsurvreportable = txn.get("amount_zar", 0) >= 50_000 or len(violations) > 0,
        )

    # ── Rules ──────────────────────────────────────────────────────

    def _rule_ada_limit_breach(self, txn: dict) -> RuleResult:
        ytd    = txn.get("ada_ytd_used", 0)
        amount = txn.get("amount_zar", 0)
        entity = txn.get("entity_type", "")
        breach = entity == "INDIVIDUAL" and (ytd + amount) > ADA_LIMIT
        return RuleResult(
            rule_id           = "ADA_LIMIT_BREACH",
            passed            = not breach,
            severity          = Severity.CRITICAL,
            score_contribution= SEVERITY_WEIGHTS[Severity.CRITICAL] if breach else 0,
            finding           = (
                f"ADA breach: cumulative R{ytd + amount:,.2f} exceeds "
                f"R1,000,000 annual discretionary allowance."
            ) if breach else "ADA within limit.",
            field_ref         = "ada_ytd_used,amount_zar",
        )

    def _rule_ada_approach_warning(self, txn: dict) -> RuleResult:
        ytd    = txn.get("ada_ytd_used", 0)
        amount = txn.get("amount_zar", 0)
        entity = txn.get("entity_type", "")
        util   = (ytd + amount) / ADA_LIMIT if ADA_LIMIT else 0
        flag   = entity == "INDIVIDUAL" and ADA_WARNING_THRESHOLD <= util <= 1.0
        return RuleResult(
            rule_id           = "ADA_APPROACH_WARNING",
            passed            = not flag,
            severity          = Severity.HIGH,
            score_contribution= SEVERITY_WEIGHTS[Severity.HIGH] if flag else 0,
            finding           = f"ADA utilisation at {util:.1%} — within 15% of limit." if flag else "ADA safe.",
            field_ref         = "ada_ytd_used",
        )

    def _rule_invalid_bop_code(self, txn: dict) -> RuleResult:
        code    = str(txn.get("bop_category_code", ""))
        invalid = code not in VALID_BOP_CODES
        return RuleResult(
            rule_id           = "INVALID_BOP_CODE",
            passed            = not invalid,
            severity          = Severity.HIGH,
            score_contribution= SEVERITY_WEIGHTS[Severity.HIGH] if invalid else 0,
            finding           = (
                f"BOP code '{code}' not in SARB-approved set. "
                f"FinSurv submission will be rejected."
            ) if invalid else f"BOP code '{code}' valid.",
            field_ref         = "bop_category_code",
        )

    def _rule_invalid_currency(self, txn: dict) -> RuleResult:
        currency = str(txn.get("currency", "")).upper()
        invalid  = currency not in VALID_CURRENCIES
        return RuleResult(
            rule_id           = "INVALID_CURRENCY",
            passed            = not invalid,
            severity          = Severity.HIGH,
            score_contribution= SEVERITY_WEIGHTS[Severity.HIGH] if invalid else 0,
            finding           = f"Currency '{currency}' not SARB-approved for FinSurv reporting." if invalid else f"Currency '{currency}' valid.",
            field_ref         = "currency",
        )

    def _rule_sanctioned_corridor(self, txn: dict) -> RuleResult:
        country    = txn.get("beneficiary_country", "")
        sanctioned = country in SANCTIONED_COUNTRIES
        return RuleResult(
            rule_id           = "SANCTIONED_CORRIDOR",
            passed            = not sanctioned,
            severity          = Severity.CRITICAL,
            score_contribution= SEVERITY_WEIGHTS[Severity.CRITICAL] if sanctioned else 0,
            finding           = (
                f"Destination '{country}' is on the OFAC/UN sanctions list. "
                f"Block transaction and file SAR immediately."
            ) if sanctioned else f"Corridor '{country}' not sanctioned.",
            field_ref         = "beneficiary_country",
        )

    def _rule_fatf_grey_list(self, txn: dict) -> RuleResult:
        country = txn.get("beneficiary_country", "")
        grey    = country in FATF_GREY_LIST
        return RuleResult(
            rule_id           = "FATF_GREY_LIST",
            passed            = not grey,
            severity          = Severity.MEDIUM,
            score_contribution= SEVERITY_WEIGHTS[Severity.MEDIUM] if grey else 0,
            finding           = f"Destination '{country}' on FATF grey list. Enhanced due diligence required." if grey else "Not grey-listed.",
            field_ref         = "beneficiary_country",
        )

    def _rule_large_individual_transfer(self, txn: dict) -> RuleResult:
        amount = txn.get("amount_zar", 0)
        entity = txn.get("entity_type", "")
        flag   = entity == "INDIVIDUAL" and amount > 500_000
        return RuleResult(
            rule_id           = "LARGE_INDIVIDUAL_TRANSFER",
            passed            = not flag,
            severity          = Severity.HIGH,
            score_contribution= SEVERITY_WEIGHTS[Severity.HIGH] if flag else 0,
            finding           = f"Individual transfer of R{amount:,.2f} exceeds R500,000. Source-of-funds docs required." if flag else "Within individual threshold.",
            field_ref         = "amount_zar,entity_type",
        )

    def _rule_round_amount_pattern(self, txn: dict) -> RuleResult:
        amount = txn.get("amount_zar", 0)
        flag   = amount % 10_000 == 0 and amount >= 100_000
        return RuleResult(
            rule_id           = "ROUND_AMOUNT_PATTERN",
            passed            = not flag,
            severity          = Severity.MEDIUM,
            score_contribution= SEVERITY_WEIGHTS[Severity.MEDIUM] if flag else 0,
            finding           = f"R{amount:,.0f} is a round number — possible structuring pattern." if flag else "No round-amount pattern.",
            field_ref         = "amount_zar",
        )

    def _rule_malformed_swift_bic(self, txn: dict) -> RuleResult:
        bic     = (txn.get("swift_bic") or "").strip()
        pattern = r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$"
        invalid = not re.match(pattern, bic)
        return RuleResult(
            rule_id           = "MALFORMED_SWIFT_BIC",
            passed            = not invalid,
            severity          = Severity.MEDIUM,
            score_contribution= SEVERITY_WEIGHTS[Severity.MEDIUM] if invalid else 0,
            finding           = f"SWIFT BIC '{bic}' is missing or malformed. FinSurv will reject." if invalid else f"BIC '{bic}' well-formed.",
            field_ref         = "swift_bic",
        )

    def _rule_company_individual_bop_mismatch(self, txn: dict) -> RuleResult:
        entity = txn.get("entity_type", "")
        code   = txn.get("bop_category_code", "")
        flag   = entity == "COMPANY" and code in {"101", "102", "401"}
        return RuleResult(
            rule_id           = "COMPANY_INDIVIDUAL_BOP_MISMATCH",
            passed            = not flag,
            severity          = Severity.MEDIUM,
            score_contribution= SEVERITY_WEIGHTS[Severity.MEDIUM] if flag else 0,
            finding           = f"COMPANY entity using individual BOP code '{code}'. Possible misclassification." if flag else "Entity/BOP consistent.",
            field_ref         = "entity_type,bop_category_code",
        )

    @staticmethod
    def _band(score: int) -> str:
        if score <= 25:
            return "LOW"
        if score <= 50:
            return "MEDIUM"
        if score <= 75:
            return "HIGH"
        return "CRITICAL"
