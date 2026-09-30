.PHONY: up down logs seed circuitos plot kaggle dados migrate migration psql test lint fmt clean

up:
	docker compose up --build -d
	@echo "API:  http://localhost:8000/health"
	@echo "Web:  http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f

# Popula o banco de desenvolvimento com a referência: compostos, os 3 circuitos
# do projeto e o grid de 2024 (piloto e equipe). Aplica as migrations antes, então
# funciona num banco vazio. Idempotente: rodar de novo não duplica nada.
seed:
	docker compose run --rm api sh -c "alembic upgrade head && python -m db.seed"

# Regenera a geometria dos circuitos (contrato D3) a partir do FastF1. Precisa de
# rede e é lento na primeira vez; os JSONs de circuits/ já estão versionados.
circuitos:
	docker compose run --rm api python -m app.pipeline.circuits

# Desenha os circuitos para conferência visual — o critério "o traçado é
# reconhecível" não se automatiza, alguém precisa olhar.
plot:
	docker compose run --rm api python -m app.pipeline.plotar

# Baixa os 3 datasets do Kaggle para data/raw/ (fora do git). Precisa de
# KAGGLE_API_TOKEN no .env. Idempotente: o que já foi baixado é pulado.
kaggle:
	docker compose run --rm --no-deps --user $$(id -u):$$(id -g) -e HOME=/tmp api python -m app.pipeline.kaggle_download

# Reconcilia as fontes e gera as curvas de degradação (entrega D5). A saída vai
# para data/mapeamentos/ e data/curvas_degradacao/, que SÃO versionados.
dados: kaggle
	docker compose run --rm --no-deps --user $$(id -u):$$(id -g) -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl api python -m app.pipeline.reconciliacao
	docker compose run --rm --no-deps --user $$(id -u):$$(id -g) -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl api python -m app.pipeline.degradacao

# Aplica no banco de desenvolvimento as migrations que ainda não rodaram.
# O `make up` já faz isso sozinho; use este alvo para rodar sem subir a API.
migrate:
	docker compose run --rm api alembic upgrade head

# Gera uma migration a partir das mudanças em backend/db/models.py.
# Uso: make migration m="adiciona tabela de alias de pilotos"
# Sempre revise o arquivo gerado: o autogenerate não pega tudo (ex.: renomeios).
migration:
	@test -n "$(m)" || (echo 'uso: make migration m="descrição da mudança"' && exit 1)
	docker compose run --rm --user $$(id -u):$$(id -g) -e HOME=/tmp api alembic revision --autogenerate -m "$(m)"

# Abre um psql no banco de desenvolvimento.
psql:
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm api ruff format --check .

fmt:
	docker compose run --rm api ruff format .

# Derruba tudo e apaga os volumes — usar para simular máquina limpa.
clean:
	docker compose down -v
