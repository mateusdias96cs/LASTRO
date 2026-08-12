"""Orquestração da ingestão: manifesto → chunks versionados.

Idempotente por construção. O `chunk_id` deriva do conteúdo, e a
`corpus_versao` é o hash do conjunto de chunks — reingerir conteúdo inalterado
produz um arquivo byte a byte idêntico. É a mesma propriedade da camada 1,
estendida ao corpus: se o índice mudou, ou a fonte mudou ou a regra de
fatiamento mudou, nunca "às vezes dá diferente".
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from conformidade.agents.retrieval.contracts import Chunk
from conformidade.agents.retrieval.ingest.chunker import LIMITE_TOKENS, fatiar, id_do_chunk
from conformidade.agents.retrieval.ingest.extract import (
    Secao,
    extrair_cis,
    extrair_html,
    extrair_pdf,
)
from conformidade.agents.retrieval.ingest.fetch import Origem, obter


class ResultadoPagina(BaseModel):
    page_id: str
    secoes: int = 0
    chunks: int = 0
    tokens_max: int = 0
    sha256: str = ""
    erro: str = ""


class RelatorioIngestao(BaseModel):
    corpus_versao: str = ""
    total_paginas: int = 0
    total_chunks: int = 0
    paginas_com_erro: int = 0
    paginas_ausentes: list[str] = Field(default_factory=list)
    por_pagina: list[ResultadoPagina] = Field(default_factory=list)
    chunks_acima_do_limite: int = 0


def carregar_manifesto(caminho: Path) -> dict[str, Any]:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def _extrair(origem: Origem, formato: str = "") -> list[Secao]:
    caminho = Path(origem.caminho)
    # `cis` é um PDF, mas com estrutura própria e regular — uma seção por
    # recomendação, em vez da heurística de títulos numerados do NIST.
    if formato == "cis":
        return extrair_cis(str(caminho))
    if caminho.suffix.lower() == ".pdf":
        return extrair_pdf(str(caminho))
    return extrair_html(caminho.read_text(encoding="utf-8", errors="replace"))


def _versao_do_documento(sha256: str) -> str:
    """Sem versão publicada pelos sites de documentação, o hash do conteúdo é
    o identificador honesto: muda quando — e só quando — o documento muda."""
    return f"sha256:{sha256[:12]}"


def ingerir(
    manifesto: Path,
    cache: Path,
    baixar: bool = False,
    limite_tokens: int = LIMITE_TOKENS,
) -> tuple[list[Chunk], RelatorioIngestao]:
    dados = carregar_manifesto(manifesto)
    relatorio = RelatorioIngestao()
    chunks: list[Chunk] = []

    for pagina in dados.get("paginas", []):
        page_id = pagina["id"]
        relatorio.total_paginas += 1

        origem = obter(page_id, pagina["url"], cache, baixar=baixar, arquivo=pagina.get("arquivo"))
        if origem is None:
            relatorio.paginas_ausentes.append(page_id)
            continue

        resultado = ResultadoPagina(page_id=page_id, sha256=origem.sha256)
        try:
            secoes = _extrair(origem, pagina.get("formato", ""))
        except Exception as exc:  # noqa: BLE001 - uma fonte ruim não derruba as outras
            resultado.erro = f"{type(exc).__name__}: {exc}"
            relatorio.paginas_com_erro += 1
            relatorio.por_pagina.append(resultado)
            continue

        resultado.secoes = len(secoes)
        brutos = fatiar(secoes, limite=limite_tokens)

        for bruto in brutos:
            chunks.append(
                Chunk(
                    chunk_id=id_do_chunk(page_id, bruto.texto, bruto.indice),
                    page_id=page_id,
                    url=pagina["url"],
                    fonte=pagina["fonte"],
                    licenca=pagina["licenca"],
                    camada=int(pagina.get("camada", 0)),
                    doc_versao=_versao_do_documento(origem.sha256),
                    heading_path=bruto.heading_path,
                    texto=bruto.texto,
                    content_sha256=hashlib.sha256(bruto.texto.encode("utf-8")).hexdigest(),
                )
            )

        resultado.chunks = len(brutos)
        resultado.tokens_max = max((b.tokens for b in brutos), default=0)
        if resultado.tokens_max > limite_tokens:
            relatorio.chunks_acima_do_limite += sum(1 for b in brutos if b.tokens > limite_tokens)
        relatorio.por_pagina.append(resultado)

    # Ordem total e estável: a saída não pode depender da ordem de iteração.
    chunks.sort(key=lambda c: (c.page_id, c.chunk_id))
    relatorio.total_chunks = len(chunks)
    relatorio.corpus_versao = versao_do_corpus(chunks)
    return chunks, relatorio


def versao_do_corpus(chunks: list[Chunk]) -> str:
    payload = ";".join(f"{c.chunk_id}:{c.content_sha256}" for c in chunks)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
