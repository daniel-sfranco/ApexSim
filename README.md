# ApexSim

Simulador de corridas de Fórmula 1 orientado a eventos e dados históricos.
Projeto da disciplina **MC857 (Turma A)** — Unicamp, 2º semestre de 2026.

O usuário configura a prova (circuito, grid, clima, estratégia de pneus) e
acompanha as voltas em tempo real como estrategista de pista — não como piloto.

## Setup

Pré-requisito: Docker com Compose v2.

```bash
git clone https://github.com/daniel-sfranco/ApexSim.git
cd ApexSim
cp .env.example .env
make up
```

Pronto. Verifique:

- API — <http://localhost:8000/health> responde `{"status": "ok"}`
- Docs da API — <http://localhost:8000/docs>
- Web — <http://localhost:3000>
- Mock WS — `ws://localhost:8080`

## Comandos

| Comando | O que faz |
|---|---|
| `make up` | Sobe api, web e banco |
| `make down` | Derruba os serviços |
| `make logs` | Acompanha os logs |
| `make seed` | Popula o banco com a referência (compostos, circuitos, grid de 2024). Idempotente |
| `make circuitos` | Regenera a geometria dos circuitos (D3) a partir do FastF1: precisa de rede |
| `make kaggle` | Baixa os datasets do Kaggle para `data/raw/` (precisa de `KAGGLE_API_TOKEN` no `.env`) |
| `make dados` | Reconcilia as fontes e gera as curvas de degradação ([`docs/dados-kaggle.md`](docs/dados-kaggle.md)) |
| `make medir` | Mede o custo de gravar uma corrida inteira no banco (cria e apaga uma corrida de teste) |
| `make migrate` | Aplica as migrations pendentes no banco de desenvolvimento |
| `make migration m="..."` | Gera uma migration a partir das mudanças em `backend/db/models.py` |
| `make psql` | Abre um `psql` no banco de desenvolvimento |
| `make test` | Testes do backend |
| `make lint` | `ruff check` + `ruff format --check` |
| `make fmt` | Formata o código |
| `make clean` | Derruba tudo e apaga os volumes (simula máquina limpa). **Apaga também o cache do FastF1**, cuja reingestão é lenta por causa do rate limit |

## Serviços

| Serviço | Porta | Stack |
|---|---|---|
| `api` | 8000 | Python 3.11, FastAPI, uv |
| `web` | 3000, 8080 | Node 20 — React (Vite) + Mock WebSocket Server |
| `db` | 5433 (host) | PostgreSQL 16 |

O cache do FastF1 fica num volume nomeado (`fastf1_cache`). Não apague sem
motivo: a API do Jolpica tem rate limit baixo e a reingestão é lenta.

## Banco de dados

PostgreSQL 16, acessado com SQLAlchemy 2 e versionado com Alembic. O schema e o
porquê de cada decisão estão em [`docs/banco-de-dados.md`](docs/banco-de-dados.md).

- O `make up` aplica as migrations sozinho antes de subir a API. Depois de um
  `git pull` que traga migration nova, basta rodar `make up` de novo.
- Mudou `backend/db/models.py`? Rode `make migration m="o que mudou"`, **revise o
  arquivo gerado** e commite os dois. Um teste falha se o modelo e as migrations
  divergirem, e outro se duas pessoas criarem migration em paralelo (histórico
  bifurcado: nesse caso rebaseie a sua sobre a mais recente).
- Os testes de banco (`make test`) rodam num banco descartável
  (`apexsim_test`), nunca no de desenvolvimento.
- Do host, o banco fica em `localhost:5433` (usuário/senha/base `apexsim`).

## Estrutura

```
backend/     API FastAPI, pipeline de dados e camada de banco (db/, migrations/)
frontend/    Aplicação web
circuits/    Geometria dos circuitos (contrato D3)
data/raw/    Datasets brutos — fora do controle de versão
data/mapeamentos/, data/curvas_degradacao/   Saídas da ingestão (versionadas)
docs/        Documentação técnica por trilha
```

## Contribuindo

Branches `feat/`, `fix/` ou `docs/`, commits em português no imperativo.
Ninguém commita direto na `main` — tudo por Pull Request com pelo menos uma
aprovação.
