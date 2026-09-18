.PHONY: up down logs seed plot test lint fmt clean

up:
	docker compose up --build -d
	@echo "API:  http://localhost:8000/health"
	@echo "Web:  http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f

# Ingestão de dados. Hoje gera a geometria dos circuitos (contrato D3);
# a partir da semana 5 popula também o banco.
seed:
	docker compose run --rm api python -m app.pipeline.circuits

# Desenha os circuitos para conferência visual — o critério "o traçado é
# reconhecível" não se automatiza, alguém precisa olhar.
plot:
	docker compose run --rm api python -m app.pipeline.plotar

test:
	docker compose run --rm api pytest

# Validação lógica dos mapas semânticos de pista (contrato D4).
validate-tracks:
	docker compose run --rm api python -m app.pipeline.validate_track_map

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm api ruff format --check .

fmt:
	docker compose run --rm api ruff format .

# Derruba tudo e apaga os volumes — usar para simular máquina limpa.
clean:
	docker compose down -v
