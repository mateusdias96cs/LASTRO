"""Recuperação híbrida: fusão de lexical e denso por Reciprocal Rank Fusion.

Por que RRF e não soma ponderada de scores: BM25 devolve um valor sem limite
superior e o cosseno vive em [-1, 1]. Somá-los exige normalizar duas
distribuições que mudam de consulta para consulta — frágil e difícil de
explicar num relatório de auditoria. RRF usa só a **posição**, então dispensa
calibração e é estável.

    score(d) = Σ  1 / (k + posição_do_ranker(d))

`k` amortece o peso das primeiras posições; 60 é o valor da literatura e o
padrão aqui.

A medição da Fase 2 deu o alvo: fatiar subiu recall@10 de 0,816 para 0,907, mas
derrubou MRR de 0,933 para 0,863 e levou os distratores de 5 para 8. A hipótese
que este módulo testa é que o denso devolva a precisão no topo sem perder a
cobertura.
"""

from __future__ import annotations

import numpy as np

from conformidade.agents.retrieval.contracts import (
    Chunk,
    ResultadoRecuperacao,
    TrechoRecuperado,
)
from conformidade.agents.retrieval.controls import documento_de
from conformidade.agents.retrieval.index.dense import DenseIndex
from conformidade.agents.retrieval.index.lexical import LexicalIndex

K_RRF = 60
# Quantos candidatos cada ranker contribui antes da fusão. Fundo raso demais
# faz a fusão perder o documento que só um dos dois achou — que é justamente
# o ganho que se espera do híbrido.
PROFUNDIDADE = 100


class HybridRetriever:
    """Une lexical e denso. Qualquer um dos dois pode ser omitido, o que
    permite medir os três modos com o mesmo código."""

    def __init__(
        self,
        chunks: list[Chunk],
        lexical: LexicalIndex | None = None,
        denso: DenseIndex | None = None,
        vetores_de_consulta: dict[str, np.ndarray] | None = None,
        k_rrf: int = K_RRF,
        profundidade: int = PROFUNDIDADE,
        agrupar_por_pagina: bool = True,
        corpus_versao: str = "",
    ) -> None:
        if lexical is None and denso is None:
            raise ValueError("é preciso ao menos um índice")
        self.chunks = sorted(chunks, key=lambda c: c.chunk_id)
        self.lexical = lexical
        self.denso = denso
        self.vetores_de_consulta = vetores_de_consulta or {}
        self.k_rrf = k_rrf
        self.profundidade = profundidade
        self.agrupar_por_pagina = agrupar_por_pagina
        self.corpus_versao = corpus_versao

    def _posicoes_lexical(self, consulta: str) -> list[int]:
        if self.lexical is None:
            return []
        return [i for i, _ in self.lexical.pontuar(consulta)[: self.profundidade]]

    def _posicoes_denso(self, control_id: str) -> list[int]:
        if self.denso is None:
            return []
        vetor = self.vetores_de_consulta.get(control_id)
        if vetor is None:
            return []
        return [i for i, _ in self.denso.pontuar(vetor)[: self.profundidade]]

    def buscar(self, control_id: str, consulta: str, k: int = 10) -> ResultadoRecuperacao:
        rankings = [
            r for r in (self._posicoes_lexical(consulta), self._posicoes_denso(control_id)) if r
        ]

        fundidos: dict[int, float] = {}
        for ranking in rankings:
            for posicao, indice in enumerate(ranking, start=1):
                fundidos[indice] = fundidos.get(indice, 0.0) + 1.0 / (self.k_rrf + posicao)

        # Desempate pelo chunk_id mantém a saída reprodutível quando dois
        # chunks empatam no score de fusão.
        ordenados = sorted(fundidos.items(), key=lambda x: (-x[1], self.chunks[x[0]].chunk_id))

        selecionados: list[tuple[int, float]] = []
        if self.agrupar_por_pagina:
            vistas: set[str] = set()
            for indice, score in ordenados:
                page_id = self.chunks[indice].page_id
                if page_id in vistas:
                    continue
                vistas.add(page_id)
                selecionados.append((indice, score))
                if len(selecionados) >= k:
                    break
        else:
            selecionados = ordenados[:k]

        origem = "rrf" if len(rankings) > 1 else ("lexical" if self.lexical else "denso")
        return ResultadoRecuperacao(
            control_id=control_id,
            consulta=consulta,
            documento_canonico=documento_de(control_id),
            trechos=[
                TrechoRecuperado(
                    chunk=self.chunks[indice],
                    score=round(score, 8),
                    posicao=posicao,
                    origem_do_score=origem,
                )
                for posicao, (indice, score) in enumerate(selecionados)
            ],
            corpus_versao=self.corpus_versao,
        )
