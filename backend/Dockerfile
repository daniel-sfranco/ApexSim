FROM python:3.11-slim

# uv vem da imagem oficial: instala as dependências em segundos e garante o
# mesmo lockfile nas cinco máquinas do grupo.
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

WORKDIR /app

# O venv fica FORA de /app porque o compose monta ./backend em /app para ter
# hot reload — o bind mount esconderia um venv criado dentro dessa pasta.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Camada separada só com o manifesto: o Docker reaproveita o cache das
# dependências enquanto só o código-fonte muda.
COPY pyproject.toml uv.lock* ./
RUN uv sync --extra dev --no-install-project

COPY . .
RUN uv sync --extra dev

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
