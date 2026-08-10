"""Retrievers de referência para a avaliação.

`BaselineLexical` é um BM25 escrito do zero sobre o texto das páginas. Ele existe
para dar o **piso**: se a busca lexical simples já atinge o limiar, o ganho do
vetorial precisa justificar a complexidade que ele adiciona.

Os retrievers sintéticos existem para testar o harness. Sem eles, um bug na
métrica só apareceria misturado a um resultado ruim de recuperação — e aí não
dá para saber qual dos dois está errado.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from conformidade.agents.retrieval.contracts import (
    Chunk,
    ResultadoRecuperacao,
    TrechoRecuperado,
)

_TOKEN = re.compile(r"[a-z0-9_.\-/]+")


def tokenizar(texto: str) -> list[str]:
    """Preserva `.`, `-`, `_` e `/` dentro do token, e também emite os
    componentes de um caminho.

    Duas necessidades do domínio que se chocam:

    * quebrar em `\\w+` transformaria `docker.sock` em `docker` + `sock` e
      `no-new-privileges` em três tokens genéricos, destruindo justamente os
      identificadores raros que a busca lexical deveria acertar;
    * manter só o caminho inteiro faria a consulta `docker.sock` **não** casar
      com um documento que escreve `/var/run/docker.sock`.

    Emitir os dois resolve: o caminho completo casa quando a consulta é
    específica, e o componente casa quando ela é mais solta.
    """
    tokens: list[str] = []
    for bruto in _TOKEN.findall(texto.lower()):
        tokens.append(bruto)
        if "/" in bruto:
            tokens.extend(parte for parte in bruto.split("/") if parte)
    return tokens


def _chunk_de_pagina(page_id: str, texto: str) -> Chunk:
    return Chunk(
        chunk_id=f"{page_id}#0",
        page_id=page_id,
        url="",
        fonte=page_id.split(":")[0],
        licenca="",
        camada=0,
        doc_versao="baseline",
        heading_path="",
        texto=texto[:2000],
        content_sha256="",
    )


class BaselineLexical:
    """BM25 no nível de página. Sem embedding, sem rede, sem banco."""

    def __init__(self, paginas: dict[str, str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.page_ids = sorted(paginas)
        self.textos = {pid: paginas[pid] for pid in self.page_ids}

        self.tokens: dict[str, Counter[str]] = {
            pid: Counter(tokenizar(texto)) for pid, texto in self.textos.items()
        }
        self.tamanhos = {pid: sum(c.values()) for pid, c in self.tokens.items()}
        self.tamanho_medio = (
            sum(self.tamanhos.values()) / len(self.tamanhos) if self.tamanhos else 0.0
        )

        self.doc_freq: Counter[str] = Counter()
        for contagem in self.tokens.values():
            self.doc_freq.update(contagem.keys())
        self.total_docs = len(self.page_ids)

    def _idf(self, termo: str) -> float:
        n = self.doc_freq.get(termo, 0)
        if n == 0:
            return 0.0
        return math.log(1 + (self.total_docs - n + 0.5) / (n + 0.5))

    def pontuar(self, consulta: str) -> list[tuple[str, float]]:
        termos = tokenizar(consulta)
        pontos: list[tuple[str, float]] = []
        for pid in self.page_ids:
            contagem = self.tokens[pid]
            tamanho = self.tamanhos[pid] or 1
            total = 0.0
            for termo in termos:
                tf = contagem.get(termo, 0)
                if tf == 0:
                    continue
                norma = 1 - self.b + self.b * (tamanho / (self.tamanho_medio or 1))
                total += self._idf(termo) * (tf * (self.k1 + 1)) / (tf + self.k1 * norma)
            if total > 0:
                pontos.append((pid, total))
        # Desempate por page_id: sem isso, páginas com score idêntico sairiam em
        # ordem imprevisível e a medição não seria reprodutível.
        pontos.sort(key=lambda x: (-x[1], x[0]))
        return pontos

    def buscar(self, control_id: str, consulta: str, k: int = 10) -> ResultadoRecuperacao:
        trechos = [
            TrechoRecuperado(
                chunk=_chunk_de_pagina(pid, self.textos[pid]),
                score=round(score, 6),
                posicao=i,
                origem_do_score="lexical",
            )
            for i, (pid, score) in enumerate(self.pontuar(consulta)[:k])
        ]
        return ResultadoRecuperacao(
            control_id=control_id,
            consulta=consulta,
            trechos=trechos,
            corpus_versao="baseline",
        )


class RetrieverPerfeito:
    """Devolve exatamente o gabarito. Serve para provar que uma métrica bem
    implementada dá 1.0 — se não der, o bug é da métrica."""

    def __init__(self, gabarito_por_controle: dict[str, list[str]]) -> None:
        self.gabarito = gabarito_por_controle

    def buscar(self, control_id: str, consulta: str, k: int = 10) -> ResultadoRecuperacao:
        paginas = self.gabarito.get(control_id, [])[:k]
        return ResultadoRecuperacao(
            control_id=control_id,
            consulta=consulta,
            trechos=[
                TrechoRecuperado(chunk=_chunk_de_pagina(pid, ""), score=1.0 - i / 100, posicao=i)
                for i, pid in enumerate(paginas)
            ],
        )


class RetrieverFixo:
    """Devolve sempre as mesmas páginas, ignorando a consulta. Piso absoluto."""

    def __init__(self, paginas: list[str]) -> None:
        self.paginas = paginas

    def buscar(self, control_id: str, consulta: str, k: int = 10) -> ResultadoRecuperacao:
        return ResultadoRecuperacao(
            control_id=control_id,
            consulta=consulta,
            trechos=[
                TrechoRecuperado(chunk=_chunk_de_pagina(pid, ""), score=0.5, posicao=i)
                for i, pid in enumerate(self.paginas[:k])
            ],
        )
