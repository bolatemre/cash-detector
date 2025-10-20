docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-down-volumes:
	@echo "Stopping containers..."
	docker compose down -v
	@echo "Removing volumes..."
	docker volume prune -f

docker-restart:
	@echo "⚠️  WARNING: This will remove all containers, volumes and data!"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@echo "Stopping containers..."
	docker compose down -v
	@echo "Removing volumes..."
	docker volume prune -f
	@echo "Building images..."
	docker compose build --no-cache
	@echo "Starting services..."
	docker compose up -d
	@echo "✅ System restarted successfully!"
	@echo "Run 'make docker-logs' to view logs"

logs-event-processor:
	docker compose logs -f event-processor

logs-master:
	docker compose logs -f master-service

docker-rebuild:
	docker compose down
	docker compose build --no-cache
	docker compose up -d
