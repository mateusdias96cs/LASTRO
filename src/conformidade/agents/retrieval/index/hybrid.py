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

## Um chunk por página: medido, e é o melhor ajuste

A auditoria da camada 2 mostrou que o agrupamento não *rebaixa* o chunk que
carrega o texto normativo — quando um vizinho da mesma página ganha a vaga, ele
**some do resultado**. Quatro controles perdem o trecho assim, e a conclusão
natural seria afrouxar a regra. Foi medido, e a conclusão natural está errada:

    por página     R@5     R@10    nDCG    controles com trecho normativo
    1 (atual)      0,766   0,936   0,806   13/19
    2              0,766   0,843   0,772   12/19
    3              0,766   0,810   0,755   12/19
    sem limite     0,687   0,726   0,730   11/19

Com 2 por página o `CONF-DKR-006` entra, mas `CONF-K8S-005` e `CONF-WLD-004`
saem — chunks repetidos de páginas bem ranqueadas consomem as vagas e empurram
para fora o portador de outro controle. Trocar o controle **crítico** do
`hostNetwork` por outro não é ganho.

Também foi medido subir o `k` entregue à camada 3, que é a outra alavanca
óbvia. De 6 para 10 ganha **um** controle (13 → 14) e leva a exposição a
distratores de 6 para 17 dos 36 — quase o triplo. Citar fonte vizinha é falha
real da camada 3, então o custo supera o ganho.

Os dois parâmetros estão no melhor ajuste. Os 6 controles que ainda não recebem
trecho normativo são problema de **consulta**, não de política de entrega.
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
