"""Índice lexical BM25 sobre chunks.

Escrito do zero e não delegado ao `tsvector` do Postgres nesta fase por um
motivo de medição: o número precisa ser comparável ao baseline da Fase 1, que
usa exatamente esta implementação. Trocar a fórmula junto com a unidade
indexada misturaria duas variáveis.

BM25 é indispensável neste domínio. As consultas carregam identificadores raros
— `allowPrivilegeEscalation`, `CAP_SYS_ADMIN`, `no-new-privileges` — e é
justamente aí que embedding falha: ele entende o conceito e erra o termo exato.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from conformidade.agents.retrieval.contracts import Chunk

_TOKEN = re.compile(r"[a-z0-9_.\-/]+")


def tokenizar(texto: str) -> list[str]:
    """Preserva `.`, `-`, `_` e `/` no meio do token, apara nas bordas, e
    também emite os componentes de um caminho.

    Duas necessidades do domínio que se chocam: quebrar em `\\w+` destruiria
    `docker.sock` e `no-new-privileges`, mas manter só o caminho inteiro faria
    a consulta `docker.sock` não casar com `/var/run/docker.sock`. Emitir os
    dois resolve.

    A aparadura das bordas conserta um defeito que a auditoria da camada 2
    expôs e que era pervasivo: pontuação colada produzia token distinto. Em
    `runs as root.` o token era `root.`, e uma consulta por `root` não casava —
    **toda** palavra em fim de frase ficava invisível. O mesmo valia para
    prefixos: `--no-install-recommends` e, no texto do Kubernetes,
    `spec.containers[*].ports[*].hostPort`, onde o `]` corta o token e sobra
    `.hostport`. Era por isso que o único chunk do corpus que documenta
    `hostPort` aparecia em 533º lugar no BM25.

    Medido contra o gabarito: recall@5 0,752 → 0,766, recall@10 0,901 → 0,936,
    MRR 0,877 → 0,891, nDCG 0,782 → 0,806, e os controles com trecho normativo
    entregue à camada 3 subiram de 11 para 13 (de 19 auditáveis).

    Também foi medida a quebra nos pontos, que alcançaria `spec.hostNetwork` e
    irmãos. Foi **rejeitada**: inflou o documento de 126 para 131 tokens e a
    normalização de comprimento do BM25 devolveu o ganho — recall@5 voltou a
    0,752 e um controle a menos recebeu trecho normativo.
    """
    tokens: list[str] = []
    for bruto in _TOKEN.findall(texto.lower()):
        limpo = bruto.strip("._-/")
        if not limpo:
            continue
        tokens.append(limpo)
        if "/" in limpo:
            tokens.extend(parte for parte in limpo.split("/") if parte)
    return tokens


class LexicalIndex:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.chunks = sorted(chunks, key=lambda c: c.chunk_id)

        self.tokens = [Counter(tokenizar(c.texto)) for c in self.chunks]
        self.tamanhos = [sum(t.values()) for t in self.tokens]
        self.tamanho_medio = sum(self.tamanhos) / len(self.tamanhos) if self.tamanhos else 0.0

        self.doc_freq: Counter[str] = Counter()
        for contagem in self.tokens:
            self.doc_freq.update(contagem.keys())
        self.total_docs = len(self.chunks)

    def _idf(self, termo: str) -> float:
        n = self.doc_freq.get(termo, 0)
        if n == 0:
            return 0.0
        return math.log(1 + (self.total_docs - n + 0.5) / (n + 0.5))

    def pontuar(self, consulta: str) -> list[tuple[int, float]]:
        termos = tokenizar(consulta)
        pontos: list[tuple[int, float]] = []
        for i, contagem in enumerate(self.tokens):
            tamanho = self.tamanhos[i] or 1
            total = 0.0
            for termo in termos:
                tf = contagem.get(termo, 0)
                if tf == 0:
                    continue
                norma = 1 - self.b + self.b * (tamanho / (self.tamanho_medio or 1))
                total += self._idf(termo) * (tf * (self.k1 + 1)) / (tf + self.k1 * norma)
            if total > 0:
                pontos.append((i, total))
        # Desempate pelo chunk_id: a ordem não pode depender do índice interno.
        pontos.sort(key=lambda x: (-x[1], self.chunks[x[0]].chunk_id))
        return pontos
