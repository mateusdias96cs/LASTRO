"""Entrypoint da API.

Os endpoints de health seguem a separação liveness/readiness/startup exigida
pelas probes do AKS e usada também pelos health probes do Container Apps.
"""

from typing import Any

from fastapi import FastAPI, Response, status

from conformidade import __version__
from conformidade.api.deterministic import router as deterministic_router
from conformidade.api.retrieval import router as retrieval_router
from conformidade.config import Settings, get_settings
from conformidade.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Conformidade",
        description="Sistema multi-agente de conformidade para Docker e Kubernetes",
        version=__version__,
    )

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
