"""Avaliação do agente de análise (camada 3).

Construída antes do agente. A maior parte das falhas desta camada é verificável
sem LLM — citação literal, controle não inventado, veredito, severidade — o que
mantém a medição barata, determinística e auditável.
"""

from conformidade.evals.analise.casos import Caso, Conjunto, carregar, validar
from conformidade.evals.analise.harness import RelatorioAnalise, formatar, rodar

__all__ = ["Caso", "Conjunto", "RelatorioAnalise", "carregar", "formatar", "rodar", "validar"]
