"""Logging estruturado em JSON no stdout.

Container Insights e Log Analytics fazem parse automático de JSON no stdout,
então nenhum agente de log precisa ser instalado na imagem.
"""

import json
import logging
import sys
from datetime import UTC, datetime

# Atributos que o `logging` põe em todo registro. O que sobrar veio de
# `extra=` e é contexto que quem escreveu o log quis carregar.
_PADRAO = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Sem isto, `logger.warning("falhou", extra={"erro": ...})` grava a
        # mensagem e joga fora o `erro` — o log fica estruturado na forma e
        # vazio no conteúdo. Custou uma investigação: a camada 3 falhava em
        # produção, o campo com o motivo era descartado aqui, e o log dizia
        # apenas "camada 3 falhou neste achado".
        for chave, valor in record.__dict__.items():
            if chave in _PADRAO or chave.startswith("_"):
                continue
            simples = isinstance(valor, str | int | float | bool | None)
            payload[chave] = valor if simples else repr(valor)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=repr)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
