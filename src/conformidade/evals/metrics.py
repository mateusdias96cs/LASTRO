"""Métricas de recuperação.

Implementadas aqui, e não importadas de uma biblioteca, porque precisam ser
auditáveis: o número que reprova um build tem que ser explicável linha a linha.

Convenção: `recuperados` é a lista ordenada de identificadores devolvida pelo
retriever (posição 0 = melhor colocado).
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(recuperados: Sequence[str], relevantes: set[str], k: int) -> float:
    """Fração dos relevantes que apareceu nos k primeiros.

    A métrica mais importante deste sistema: se o trecho certo não vem, nenhum
    agente adiante consegue consertar. É o teto de qualidade do pipeline.
    """
    if not relevantes:
        return 1.0  # nada a recuperar: não penaliza
    acertos = len(set(recuperados[:k]) & relevantes)
    return acertos / len(relevantes)


def precision_at_k(recuperados: Sequence[str], relevantes: set[str], k: int) -> float:
    """Fração dos k primeiros que é relevante. Mede o lixo que vai junto."""
    if k <= 0 or not recuperados:
        return 0.0
    janela = recuperados[:k]
    return len([r for r in janela if r in relevantes]) / len(janela)


def reciprocal_rank(recuperados: Sequence[str], relevantes: set[str]) -> float:
    """1/posição do primeiro relevante. Zero se nenhum aparecer."""
    for posicao, item in enumerate(recuperados, start=1):
        if item in relevantes:
            return 1.0 / posicao
    return 0.0


def dcg(ganhos: Sequence[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(ganhos))


def ndcg_at_k(recuperados: Sequence[str], ganho_por_item: dict[str, float], k: int) -> float:
    """nDCG com relevância graduada.

    Distingue "trouxe a página normativa em 1º" de "trouxe uma página de apoio
    em 1º e a normativa em 8º" — diferença que Recall sozinho não captura.
    """
    if not ganho_por_item:
        return 1.0
    obtidos = [ganho_por_item.get(item, 0.0) for item in recuperados[:k]]
    ideais = sorted(ganho_por_item.values(), reverse=True)[:k]
    denominador = dcg(ideais)
    if denominador == 0:
        return 1.0
    return dcg(obtidos) / denominador


def violou_distratores(recuperados: Sequence[str], proibidos: set[str], k: int) -> list[str]:
    """Distratores que apareceram nos k primeiros quando não deveriam.

    É o teste dos pares confundíveis: buscar `hostPort` não pode trazer
    `hostNetwork` no topo. Falha aqui é mais grave que recall baixo, porque
    produz citação plausível e errada — exatamente o que engana o revisor.
    """
    return [item for item in recuperados[:k] if item in proibidos]
