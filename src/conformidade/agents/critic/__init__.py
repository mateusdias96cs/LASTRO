"""Camada 4 — o crítico.

A única camada com LLM é a 3, e portanto a única que pode inventar. Esta é a
trava: confere a saída do analista sem modelo nenhum, e rebaixa ou descarta o
que não se sustenta.
"""

from conformidade.agents.critic.aplicar import Aplicacao, aplicar
from conformidade.agents.critic.contracts import (
    AchadoCriticado,
    CatalogoDeCorrecoes,
    CorrecaoAplicavel,
    Formato,
    ItemDoRelatorio,
    Objecao,
    RelatorioFinal,
    Reparo,
    VereditoCritico,
)
from conformidade.agents.critic.correcoes import CATALOGO, correcao_para
from conformidade.agents.critic.critico import criticar
from conformidade.agents.critic.relatorio import em_markdown

__all__ = [
    "CATALOGO",
    "AchadoCriticado",
    "CatalogoDeCorrecoes",
    "CorrecaoAplicavel",
    "Formato",
    "ItemDoRelatorio",
    "Objecao",
    "RelatorioFinal",
    "Reparo",
    "VereditoCritico",
    "correcao_para",
    "criticar",
    "Aplicacao",
    "aplicar",
    "em_markdown",
]
