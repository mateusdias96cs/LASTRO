"""Índice denso em memória, com busca exata.

Exata e não aproximada (HNSW/IVF), de propósito. Com 1.224 chunks × 384
dimensões, o produto matriz-vetor custa menos de um milissegundo — índice
aproximado aqui só adicionaria perda de recall e um parâmetro a mais para
confundir a medição. ANN passa a fazer sentido a partir de centenas de
milhares de vetores.

Isso também mantém o eval limpo: a diferença entre lexical e denso mede o
método de recuperação, não a aproximação do índice.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from conformidade.agents.retrieval.contracts import Chunk


class DenseIndex:
    def __init__(self, chunks: list[Chunk], vetores: np.ndarray) -> None:
        if len(chunks) != vetores.shape[0]:
            raise ValueError(f"chunks ({len(chunks)}) e vetores ({vetores.shape[0]}) não batem")
        # A mesma ordenação do índice lexical, para que as posições sejam
        # comparáveis entre os dois na fusão.
        ordem = sorted(range(len(chunks)), key=lambda i: chunks[i].chunk_id)
        self.chunks = [chunks[i] for i in ordem]
        self.vetores = np.ascontiguousarray(vetores[ordem], dtype=np.float32)
        self.dimensao = self.vetores.shape[1] if self.vetores.size else 0

    def pontuar(self, vetor_consulta: np.ndarray) -> list[tuple[int, float]]:
        """Similaridade de cosseno. Assume vetores já normalizados L2."""
        if self.vetores.size == 0:
            return []
        similaridades = self.vetores @ vetor_consulta.astype(np.float32)
        ordem = np.argsort(-similaridades, kind="stable")
        return [(int(i), float(similaridades[i])) for i in ordem]

    # -- persistência ------------------------------------------------------

    def salvar(self, destino: Path) -> None:
        """Grava os vetores na ordem interna (ordenada por `chunk_id`)."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        np.save(destino, self.vetores)

    @staticmethod
    def carregar(chunks: list[Chunk], origem: Path) -> DenseIndex:
        """Reconstrói o índice a partir dos vetores gravados.

        Ordena os chunks pela mesma chave antes de parear. Sem isso, os vetores
        (já ordenados por `salvar`) seriam permutados de novo pelo construtor e
        cada texto ficaria com o vetor de outro chunk — o mesmo erro que
        `indexar_chunks` cometia, agora no caminho de persistência. Falha
        silenciosa: nada quebra, só as respostas ficam erradas.
        """
        return DenseIndex(ordenar(chunks), np.load(origem))


def ordenar(chunks: list[Chunk]) -> list[Chunk]:
    """Chave de ordenação canônica do índice. Um único lugar a mudar."""
    return sorted(chunks, key=lambda c: c.chunk_id)
