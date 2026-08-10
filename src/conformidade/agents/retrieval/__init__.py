"""Agente de recuperação — camada 2 do pipeline.

Estado: Fase 0 (fontes) e Fase 1 (gabarito e avaliação) concluídas. A ingestão
e o índice híbrido são as fases seguintes.

O que já está definido aqui é o contrato e a consulta canônica de cada controle
— o suficiente para o harness de avaliação medir qualquer implementação futura.
"""

from conformidade.agents.retrieval.contracts import (
    Chunk,
    ResultadoRecuperacao,
    Retriever,
    TrechoRecuperado,
)
from conformidade.agents.retrieval.queries import CONSULTAS, consulta_de

__all__ = [
    "CONSULTAS",
    "Chunk",
    "ResultadoRecuperacao",
    "Retriever",
    "TrechoRecuperado",
    "consulta_de",
]
