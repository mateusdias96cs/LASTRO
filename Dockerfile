# syntax=docker/dockerfile:1.9
#
# Build multi-stage. A imagem final não contém uv, compiladores nem cache de
# build — só o virtualenv e o código. Menor superfície de ataque no Defender
# for Containers e push mais rápido para o ACR.

# ---------- estágio de build ----------
FROM python:3.15-slim-bookworm AS builder

# Pin do uv casado com o que gerou o uv.lock (lockfile v1/revision 3).
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependências primeiro: essa layer só invalida quando pyproject/uv.lock mudam,
# o que mantém o build do Azure Pipelines rápido via cache do ACR.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Só agora o código: mexer em src/ não reinstala as dependências.
COPY README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------- imagem final ----------
FROM python:3.15-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="conformidade" \
      org.opencontainers.image.description="Sistema multi-agente de conformidade para Docker e Kubernetes" \
      org.opencontainers.image.source="https://github.com/CHANGEME/conformidade" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    CONFORMIDADE_CORPUS_DIR=/app/corpus

# UID numérico alto e fixo: exigido pelo Pod Security Standard `restricted`
# do AKS (runAsNonRoot valida o UID, não o nome do usuário).
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
# O corpus indexado (3,4 MB) entra na imagem, e não num volume: ele é
# versionado no git, muda só quando alguém reindexa, e embutir torna a imagem
# a unidade completa — sobe em qualquer lugar sem depender de storage montado.
COPY --chown=10001:10001 corpus/chunks.jsonl /app/corpus/chunks.jsonl
COPY --chown=10001:10001 corpus/index/ /app/corpus/index/

COPY --chown=10001:10001 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER 10001:10001

EXPOSE 8000

# Ignorado pelo Kubernetes (que usa as probes do manifesto), mas usado pelo
# Docker local e pelo `docker compose`.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://127.0.0.1:{os.getenv('PORT','8000')}/health/live\").read()" || exit 1

# Forma exec: o processo vira PID 1 e recebe o SIGTERM do drain do Kubernetes.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["api"]
