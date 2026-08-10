"""CLI da indexação densa (role `index` da imagem)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from conformidade.agents.retrieval.embeddings import MODELO_PADRAO, FastEmbedProvider
from conformidade.agents.retrieval.index.build import (
    indexar_chunks,
    indexar_consultas,
    salvar_indice,
)
from conformidade.agents.retrieval.ingest.pipeline import versao_do_corpus
from conformidade.agents.retrieval.ingest.store import carregar_chunks


def main(argv: list[str] | None = None, raiz: Path | None = None) -> int:
    raiz = raiz or Path.cwd()
    parser = argparse.ArgumentParser(prog="conformidade-index", description=__doc__)
    parser.add_argument("--chunks", type=Path, default=raiz / "corpus" / "chunks.jsonl")
    parser.add_argument("--saida", type=Path, default=raiz / "corpus" / "index")
    parser.add_argument("--modelo", default=MODELO_PADRAO)
    parser.add_argument("--cache-modelo", default=None)
    args = parser.parse_args(argv)

    chunks = carregar_chunks(args.chunks)
    print(f"chunks       : {len(chunks)}")
    print(f"modelo       : {args.modelo}")

    provider = FastEmbedProvider(args.modelo, cache=args.cache_modelo)

    inicio = time.monotonic()
    vetores = indexar_chunks(chunks, provider)
    decorrido = time.monotonic() - inicio
    print(f"vetores      : {vetores.shape} em {decorrido:.1f}s")

    consultas = indexar_consultas(provider)
    print(f"consultas    : {len(consultas)} vetores pré-computados")

    corpus_versao = versao_do_corpus(sorted(chunks, key=lambda c: (c.page_id, c.chunk_id)))
    salvar_indice(args.saida, vetores, consultas, args.modelo, corpus_versao)
    print(f"\nescrito em   : {args.saida}")
    print(f"corpus_versao: {corpus_versao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
