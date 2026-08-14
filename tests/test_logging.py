"""O log estruturado precisa carregar o contexto, não só a mensagem."""

import json
import logging

from conformidade.logging import JsonFormatter


def _formatar(**extra) -> dict:
    registro = logging.LogRecord(
        "teste", logging.WARNING, "arquivo.py", 1, "algo falhou", None, None
    )
    registro.__dict__.update(extra)
    return json.loads(JsonFormatter().format(registro))


def test_campos_de_extra_aparecem_no_json():
    """Custou uma investigação: a camada 3 falhava em produção, o campo com o
    motivo era descartado pelo formatador, e o log dizia apenas
    "camada 3 falhou neste achado"."""
    saida = _formatar(erro="ClientAuthenticationError", detalhe="token negado")
    assert saida["erro"] == "ClientAuthenticationError"
    assert saida["detalhe"] == "token negado"


def test_campos_padrao_do_logging_nao_poluem():
    saida = _formatar()
    assert set(saida) == {"timestamp", "level", "logger", "message"}


def test_valor_nao_serializavel_nao_derruba_o_log():
    """Log que estoura ao formatar apaga justamente o erro que ia registrar."""
    saida = _formatar(objeto=object())
    assert "object object" in saida["objeto"]
