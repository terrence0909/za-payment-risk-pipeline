"""
Kafka producer — streams synthetic ZA payment events continuously.
"""

import json
import logging
import os
import time
import random
from dotenv import load_dotenv
from kafka import KafkaProducer
from generator import PaymentEventGenerator

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("za-producer")

KAFKA_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("TOPIC_RAW", "za.payments.raw")
TPM = int(os.getenv("TRANSACTIONS_PER_MINUTE", "60"))
SLEEP = 60 / TPM

SCENARIOS = ["normal"] * 70 + ["breach"] * 10 + ["suspicious"] * 10 + ["invalid_bop"] * 7 + ["sanctioned"] * 3


def main():
    logger.info(f"Connecting to Kafka at {KAFKA_BROKERS}")
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        retries=5,
    )
    logger.info(f"Connected. Producing to topic '{TOPIC}' at {TPM} tx/min")

    gen = PaymentEventGenerator()
    count = 0

    while True:
        scenario = random.choice(SCENARIOS)
        event = gen.generate(scenario=scenario)
        producer.send(TOPIC, value=event)
        count += 1
        logger.info(
            f"[{count}] {event['transaction_id']} | "
            f"R{event['amount_zar']:>12,.2f} | "
            f"{event['beneficiary_country']} | "
            f"BOP:{event['bop_category_code']} | "
            f"scenario:{scenario}"
        )
        time.sleep(SLEEP)


if __name__ == "__main__":
    main()
