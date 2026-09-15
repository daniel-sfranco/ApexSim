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

## Comandos

| Comando | O que faz |
|---|---|
| `make up` | Sobe api, web e banco |
| `make down` | Derruba os serviços |
| `make logs` | Acompanha os logs |
| `make seed` | Roda a ingestão de dados (geometria dos circuitos) |
| `make test` | Testes do backend |
| `make lint` | `ruff check` + `ruff format --check` |
| `make fmt` | Formata o código |
| `make clean` | Derruba tudo e apaga os volumes (simula máquina limpa) |

## Serviços

| Serviço | Porta | Stack |
|---|---|---|
| `api` | 8000 | Python 3.11, FastAPI, uv |
| `web` | 3000 | Node 20 — scaffold Next.js em andamento |
| `db` | 5432 | PostgreSQL 16 |

O cache do FastF1 fica num volume nomeado (`fastf1_cache`). Não apague sem
motivo: a API do Jolpica tem rate limit baixo e a reingestão é lenta.

## Estrutura

```
backend/     API FastAPI e pipeline de dados
frontend/    Aplicação web
circuits/    Geometria dos circuitos (contrato D3)
data/raw/    Datasets brutos — fora do controle de versão
docs/        Documentação técnica por trilha
```

## Contribuindo

Branches `feat/`, `fix/` ou `docs/`, commits em português no imperativo.
Ninguém commita direto na `main` — tudo por Pull Request com pelo menos uma
aprovação.
