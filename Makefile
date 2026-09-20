.PHONY: help up down produce logs logs-processor clean

COMPOSE = docker compose -f infra/docker-compose.yml

help:
	@echo ""
	@echo "ZA Payment Risk Streaming Pipeline"
	@echo "────────────────────────────────────────────"
	@echo "  make up       Start the full stack"
	@echo "  make down     Stop all services"
	@echo "  make produce  Start the payment event producer"
	@echo "  make logs     Tail all logs"
	@echo "  make clean    Remove volumes and reset state"
	@echo ""

up:
	$(COMPOSE) up -d
	@echo ""
	@echo "Services starting..."
	@echo "  Kafka UI  → http://localhost:8090"
	@echo "  MinIO     → http://localhost:9001  (minioadmin / minioadmin)"
	@echo ""

down:
	$(COMPOSE) down

produce:
	cd src/producer && \
	pip3 install -r requirements.txt -q && \
	python3 producer.py

logs:
	$(COMPOSE) logs -f

clean:
	$(COMPOSE) down -v
	@echo "Volumes removed."
