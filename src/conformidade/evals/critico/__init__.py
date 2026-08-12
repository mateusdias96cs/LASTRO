"""Avaliação da camada 4 — o crítico.

Prova que a trava **discrimina**: pega o que deve pegar e deixa passar o que
está correto. Os testes unitários em `tests/test_critico.py` provam que ela
roda; os duplos aqui provam que ela decide.
"""

from conformidade.evals.critico.casos import CASOS, CasoCritico, deveriam_aprovar, deveriam_reprovar
from conformidade.evals.critico.duplos import critico_cego, critico_paranoico
from conformidade.evals.critico.harness import RelatorioCritico, formatar, rodar

__all__ = [
    "CASOS",
    "CasoCritico",
    "RelatorioCritico",
    "critico_cego",
    "critico_paranoico",
    "deveriam_aprovar",
    "deveriam_reprovar",
    "formatar",
    "rodar",
]
