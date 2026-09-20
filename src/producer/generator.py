"""
Synthetic ZA cross-border payment event generator.
Uses real SARB FinSurv BOP category codes, real SA bank SWIFT BICs,
and statistically plausible ADA utilisation patterns.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Optional


BOP_CODES = {
    "101": "Private individual transfer — family support",
    "102": "Private individual transfer — gifts",
    "201": "Dividends",
    "202": "Interest payments",
    "301": "Import of goods",
    "302": "Export of goods",
    "401": "Travel and tourism",
    "501": "Professional and management fees",
    "502": "IT and software services",
    "601": "Investment in foreign assets — unit trusts",
    "602": "Investment in foreign assets — direct equity",
    "701": "Loan repayment",
}

INVALID_BOP_CODES = ["000", "999", "ABC", "X01"]

SA_BANK_BICS = [
    "ABSAZAJJ",  # Absa Bank
    "FIRNZAJJ",  # FNB
    "SBZAZAJJ",  # Standard Bank
    "NEDSZAJJ",  # Nedbank
    "INVEZMJJ",  # Investec
    "CABLZAJJ",  # Capitec
]

CORRIDORS = {
    "GBR": {"swift_prefix": "BARCGB", "risk_weight": 1.0, "sanctioned": False},
    "USA": {"swift_prefix": "CHASUS", "risk_weight": 1.0, "sanctioned": False},
    "DEU": {"swift_prefix": "DEUTDE", "risk_weight": 1.0, "sanctioned": False},
    "NLD": {"swift_prefix": "INGBNL", "risk_weight": 1.0, "sanctioned": False},
    "CHE": {"swift_prefix": "UBSWCH", "risk_weight": 1.1, "sanctioned": False},
    "MUS": {"swift_prefix": "MCBLMU", "risk_weight": 1.4, "sanctioned": False},
    "SGP": {"swift_prefix": "DBSSSG", "risk_weight": 1.3, "sanctioned": False},
    "ARE": {"swift_prefix": "NBADAE", "risk_weight": 1.5, "sanctioned": False},
    "ZWE": {"swift_prefix": "BARCZA", "risk_weight": 2.0, "sanctioned": False},
    "NGA": {"swift_prefix": "GTBING", "risk_weight": 1.8, "sanctioned": False},
    "IRN": {"swift_prefix": "MELIIR", "risk_weight": 5.0, "sanctioned": True},
}

EXCHANGE_RATES = {
    "GBP": 23.50, "USD": 18.20, "EUR": 19.80,
    "CHF": 20.10, "SGD": 13.50, "AED": 4.95,
    "MUR": 0.41,  "ZWL": 0.05,
}

CURRENCY_BY_COUNTRY = {
    "GBR": "GBP", "USA": "USD", "DEU": "EUR",
    "NLD": "EUR", "CHE": "CHF", "MUS": "MUR",
    "SGP": "SGD", "ARE": "AED", "ZWE": "ZWL",
    "NGA": "USD", "IRN": "USD",
}


class PaymentEventGenerator:

    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)
        self._ada_tracker: dict = {}

    def generate(self, scenario: str = "normal") -> dict:
        originator_id = f"RSA-{random.choice(['IND', 'COM', 'TRU'])}-{random.randint(10000, 99999)}"
        country = self._pick_country(scenario)
        currency = CURRENCY_BY_COUNTRY.get(country, "USD")
        exchange_rate = EXCHANGE_RATES.get(currency, 18.0)
        amount_zar = self._pick_amount(scenario)
        amount_foreign = round(amount_zar / exchange_rate, 2)
        ada_ytd = self._ada_tracker.get(originator_id, random.uniform(0, 800000))
        if scenario == "breach":
            ada_ytd = random.uniform(900000, 999999)
        bop_code = self._pick_bop_code(scenario)
        entity_type = random.choice(["INDIVIDUAL", "INDIVIDUAL", "INDIVIDUAL", "COMPANY"])

        event = {
            "transaction_id": f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bank_code": random.choice(SA_BANK_BICS),
            "originator_id": originator_id,
            "beneficiary_country": country,
            "swift_bic": f"{CORRIDORS[country]['swift_prefix']}XX",
            "amount_zar": round(amount_zar, 2),
            "currency": currency,
            "exchange_rate": exchange_rate,
            "amount_foreign": amount_foreign,
            "bop_category_code": bop_code,
            "bop_description": BOP_CODES.get(bop_code, "UNKNOWN"),
            "ada_ytd_used": round(ada_ytd, 2),
            "ada_limit": 1000000.00,
            "transaction_purpose": random.choice([
                "FAMILY_SUPPORT", "INVESTMENT", "TRADE_PAYMENT",
                "SERVICE_PAYMENT", "LOAN_REPAYMENT", "TRAVEL",
            ]),
            "is_resident": random.random() > 0.1,
            "entity_type": entity_type,
            "source_system": "PAYMENTS_CORE_v3",
            "schema_version": "1.0.0",
        }

        self._ada_tracker[originator_id] = ada_ytd + amount_zar
        return event

    def _pick_country(self, scenario: str) -> str:
        if scenario == "sanctioned":
            return "IRN"
        countries = list(CORRIDORS.keys())[:10]
        weights = [3, 3, 2, 2, 1, 1, 1, 1, 0.5, 0.5]
        return random.choices(countries, weights=weights)[0]

    def _pick_amount(self, scenario: str) -> float:
        if scenario == "breach":
            return round(random.uniform(150000, 400000), 2)
        if scenario == "suspicious":
            return float(random.choice([100000, 200000, 500000, 250000]))
        return round(random.lognormvariate(11.5, 1.2), 2)

    def _pick_bop_code(self, scenario: str) -> str:
        if scenario == "invalid_bop":
            return random.choice(INVALID_BOP_CODES)
        if random.random() < 0.05:
            return random.choice(INVALID_BOP_CODES)
        return random.choice(list(BOP_CODES.keys()))
