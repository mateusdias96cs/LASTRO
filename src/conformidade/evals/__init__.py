"""Avaliação de recuperação.

Construída **antes** do retriever, de propósito: sem medição, decidir entre
lexical, híbrido ou grafo vira opinião. E é a única forma de evitar o pior
padrão de RAG — ajustar tamanho de chunk no olho até "parecer melhor".
"""

from conformidade.evals.golden import Gabarito, carregar_gabarito, validar
from conformidade.evals.harness import RelatorioEval, ResultadoControle, formatar, rodar

__all__ = [
    "Gabarito",
    "RelatorioEval",
    "ResultadoControle",
    "carregar_gabarito",
    "formatar",
    "rodar",
    "validar",
]
