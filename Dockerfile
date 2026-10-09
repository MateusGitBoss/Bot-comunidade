FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

WORKDIR /app
# Dependências primeiro: a camada fica em cache enquanto só o código muda
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
COPY docs/faq ./docs/faq
COPY prompts ./prompts
RUN uv sync --locked --no-dev

RUN useradd --create-home app
USER app

# Bot de Discord não recebe HTTP: ele abre a conexão com o Discord, por isso não há EXPOSE
CMD ["bot"]
