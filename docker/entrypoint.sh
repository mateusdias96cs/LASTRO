#!/bin/sh
# Entrypoint multi-role: a mesma imagem serve a API e, futuramente, cada agente.
# Um único repositório no ACR e uma única tag por commit — o role vem do `command`
# do Deployment (AKS) ou do container do Container Apps.
set -eu

ROLE="${1:-api}"
[ "$#" -gt 0 ] && shift

case "$ROLE" in
  api)
    # `conformidade-api` (console script) chama uvicorn com log_config=None,
    # deixando o logging JSON da aplicação valer. `exec` mantém o processo como
    # PID 1 para receber o SIGTERM do drain do Kubernetes.
    # Host e porta vêm das settings (PORT / CONFORMIDADE_HOST).
    exec conformidade-api
    ;;
  ingest)
    # Job de ingestão do corpus (Fase 2). Não é serviço: roda, escreve e sai.
    exec python -m conformidade.agents.retrieval.ingest.cli "$@"
    ;;
  index)
    # Indexação densa (Fase 3). Precisa do extra `embed` instalado na imagem.
    exec python -m conformidade.agents.retrieval.index.cli "$@"
    ;;
  worker)
    echo '{"level":"ERROR","message":"role worker ainda nao implementado"}' >&2
    exit 64
    ;;
  shell)
    exec /bin/sh "$@"
    ;;
  *)
    # Escotilha: `docker run <img> python -m ...` sem passar por um role.
    exec "$ROLE" "$@"
    ;;
esac
