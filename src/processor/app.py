"""
Faust stream processor — ZA Payment Risk Pipeline.

Consumes raw payment events from Kafka, runs the compliance
rules engine on each one, routes HIGH/CRITICAL to an alerts
topic, and writes scored records to MinIO in Delta Lake format.
"""

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone

import faust

from rules_engine import ComplianceRulesEngine, EngineResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("za-processor")

KAFKA_BROKERS  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_RAW      = os.getenv("TOPIC_RAW",     "za.payments.raw")
TOPIC_SCORED   = os.getenv("TOPIC_SCORED",  "za.payments.scored")
TOPIC_ALERTS   = os.getenv("TOPIC_ALERTS",  "za.payments.alerts")

app = faust.App(
    "za-payment-risk-processor",
    broker=f"kafka://{KAFKA_BROKERS}",
    value_serializer="json",
    topic_replication_factor=1,
)

raw_topic    = app.topic(TOPIC_RAW,    value_type=bytes)
scored_topic = app.topic(TOPIC_SCORED, value_type=bytes)
alerts_topic = app.topic(TOPIC_ALERTS, value_type=bytes)

engine = ComplianceRulesEngine()


def build_scored_event(txn: dict, result: EngineResult) -> dict:
    return {
        **txn,
        "risk_score":        result.risk_score,
        "risk_band":         result.risk_band,
        "compliance_passed": result.passed,
        "requires_sar":      result.requires_sar,
        "finsurvreportable": result.finsurvreportable,
        "violation_count":   len(result.violations),
        "warning_count":     len(result.warnings),
        "violations":        [asdict(v) for v in result.violations],
        "warnings":          [asdict(w) for w in result.warnings],
        "processed_at":      datetime.now(timezone.utc).isoformat(),
        "processor_version": "1.0.0",
    }


@app.agent(raw_topic)
async def process_payments(stream):
    async for raw in stream:
        try:
            txn    = json.loads(raw) if isinstance(raw, bytes) else raw
            result = engine.evaluate(txn)
            scored = build_scored_event(txn, result)

            await scored_topic.send(value=json.dumps(scored).encode())

            if result.risk_band in ("HIGH", "CRITICAL"):
                alert = {
                    "alert_id":            f"ALERT-{txn.get('transaction_id')}",
                    "transaction_id":      txn.get("transaction_id"),
                    "risk_band":           result.risk_band,
                    "risk_score":          result.risk_score,
                    "requires_sar":        result.requires_sar,
                    "violations":          [asdict(v) for v in result.violations],
                    "amount_zar":          txn.get("amount_zar"),
                    "beneficiary_country": txn.get("beneficiary_country"),
                    "bank_code":           txn.get("bank_code"),
                    "alerted_at":          datetime.now(timezone.utc).isoformat(),
                }
                await alerts_topic.send(value=json.dumps(alert).encode())
                logger.warning(
                    f"ALERT [{result.risk_band}] {txn.get('transaction_id')} "
                    f"score={result.risk_score} violations={len(result.violations)} "
                    f"SAR={result.requires_sar}"
                )
            else:
                logger.info(
                    f"PASS  [{result.risk_band}] {txn.get('transaction_id')} "
                    f"score={result.risk_score} "
                    f"R{txn.get('amount_zar', 0):>12,.2f} → {txn.get('beneficiary_country')}"
                )

        except json.JSONDecodeError as e:
            logger.error(f"Malformed event: {e}")
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)


if __name__ == "__main__":
    app.main()
