"""Ingestão do corpus — Fase 2.

manifesto → coleta (com cache) → extração de seções → fatiamento → chunks
versionados em JSONL.

Roda como o role `worker` da imagem: um Job, não um serviço.
"""

from conformidade.agents.retrieval.ingest.chunker import (
    LIMITE_TOKENS,
    ChunkBruto,
    estimar_tokens,
    fatiar,
    id_do_chunk,
)
from conformidade.agents.retrieval.ingest.extract import Secao, extrair_html, extrair_pdf
from conformidade.agents.retrieval.ingest.pipeline import (
    RelatorioIngestao,
    ResultadoPagina,
    ingerir,
    versao_do_corpus,
)
from conformidade.agents.retrieval.ingest.store import carregar_chunks, salvar_chunks

__all__ = [
    "LIMITE_TOKENS",
    "ChunkBruto",
    "RelatorioIngestao",
    "ResultadoPagina",
    "Secao",
    "carregar_chunks",
    "estimar_tokens",
    "extrair_html",
    "extrair_pdf",
    "fatiar",
    "id_do_chunk",
    "ingerir",
    "salvar_chunks",
    "versao_do_corpus",
]
