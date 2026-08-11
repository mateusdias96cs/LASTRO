"""Rotas do agente de recuperação.

O índice é carregado sob demanda e mantido em memória: 1.224 chunks × 384
dimensões são ~1,9 MB, e a busca exata custa menos de um milissegundo. Nenhum
modelo é carregado aqui — as 36 consultas têm vetores pré-computados, então a
imagem da API não precisa do fastembed.

Se o índice não estiver presente, a rota responde 503 em vez de degradar em
silêncio: recuperação vazia faria o agente de análise inventar.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from conformidade.agents.retrieval.contracts import ResultadoRecuperacao
from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
from conformidade.agents.retrieval.index.build import (
    carregar_consultas,
    carregar_indice_denso,
    ler_meta,
)
from conformidade.agents.retrieval.ingest import carregar_chunks
from conformidade.agents.retrieval.queries import CONSULTAS
from conformidade.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["recuperação"])


def _base_do_corpus() -> Path:
    return Path(get_settings().corpus_dir)


@lru_cache(maxsize=1)
def _retriever() -> HybridRetriever | None:
    base = _base_do_corpus()
    caminho_chunks = base / "chunks.jsonl"
    caminho_indice = base / "index"

    if not caminho_chunks.exists():
        return None
    chunks = carregar_chunks(caminho_chunks)
    lexical = LexicalIndex(chunks)
    meta = ler_meta(caminho_indice)

    denso = None
    consultas = None
    if (caminho_indice / "vectors.npy").exists():
        denso = carregar_indice_denso(chunks, caminho_indice)
        consultas = carregar_consultas(caminho_indice)

    return HybridRetriever(
        chunks,
        lexical=lexical,
        denso=denso,
        vetores_de_consulta=consultas,
        corpus_versao=meta.get("corpus_versao", ""),
    )


@router.get("/retrieve", response_model=ResultadoRecuperacao)
def retrieve(
    control_id: str = Query(..., description="identificador do controle, ex.: CONF-WLD-002"),
    k: int = Query(10, ge=1, le=50),
) -> ResultadoRecuperacao:
    if control_id not in CONSULTAS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"controle desconhecido: {control_id}",
        )

    retriever = _retriever()
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="corpus não indexado; rode o job de ingestão e indexação",
        )

    return retriever.buscar(control_id, CONSULTAS[control_id], k=k)
