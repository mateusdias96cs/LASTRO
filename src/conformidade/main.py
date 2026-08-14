"""Entrypoint da API.

Os endpoints de health seguem a separação liveness/readiness/startup exigida
pelas probes do AKS e usada também pelos health probes do Container Apps.
"""

from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from conformidade import __version__
from conformidade.api.auditoria import router as auditoria_router
from conformidade.api.deterministic import router as deterministic_router
from conformidade.api.retrieval import router as retrieval_router
from conformidade.config import Settings, get_settings
from conformidade.logging import configure_logging

# Teto do corpo da requisição. O arquivo em si é limitado a 2 MiB pelas rotas;
# a folga aqui cobre o envelope multipart (fronteiras, cabeçalhos de parte e o
# campo `contexto`) sem deixar a porta aberta.
MAX_CORPO_BYTES = 4 * 1024 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Conformidade",
        description="Sistema multi-agente de conformidade para Docker e Kubernetes",
        version=__version__,
    )

    # O frontend mora em outro domínio (Container App separado), então o
    # navegador exige que a API declare de quais origens aceita chamada. Sem
    # isto toda requisição falha e o erro aparece como falha de rede genérica.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_permitidas,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        # Não há cookie nem sessão: a API é sem estado e sem autenticação de
        # usuário. Liberar credenciais só ampliaria a superfície à toa.
        allow_credentials=False,
    )

    # Recusa pelo cabeçalho, antes de o corpo ser lido.
    #
    # As rotas já limitam a leitura a `MAX_UPLOAD_BYTES + 1`, o que protege a
    # memória. Isto é a camada anterior: um corpo de 1 GB anunciado no
    # `Content-Length` é recusado sem que um byte suba pela rede. Vale para
    # toda rota, inclusive as que ainda não existem.
    #
    # Cabeçalho ausente (`Transfer-Encoding: chunked`) passa direto e cai na
    # checagem das rotas, que é a que realmente protege.
    @app.middleware("http")
    async def limitar_corpo(request: Request, call_next):
        declarado = request.headers.get("content-length")
        if declarado and declarado.isdigit() and int(declarado) > MAX_CORPO_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": f"corpo acima do limite de {MAX_CORPO_BYTES} bytes"},
            )
        return await call_next(request)

    app.include_router(auditoria_router)
    app.include_router(deterministic_router)
    app.include_router(retrieval_router)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
        }

    @app.get("/health/live", status_code=status.HTTP_200_OK)
    def live() -> dict[str, str]:
        """O processo está vivo. Nunca depende de dependências externas."""
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready(response: Response) -> dict[str, Any]:
        """Pronto para receber tráfego.

        Sem dependências externas ainda; quando entrarem (banco, fila, Key Vault)
        as checagens vão aqui e devolvem 503 enquanto não estiverem prontas.
        """
        checks: dict[str, str] = {}
        if all(v == "ok" for v in checks.values()):
            return {"status": "ready", "checks": checks}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    @app.get("/health/startup", status_code=status.HTTP_200_OK)
    def startup() -> dict[str, str]:
        """Startup probe: inicialização concluída."""
        return {"status": "started"}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "conformidade.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    run()
