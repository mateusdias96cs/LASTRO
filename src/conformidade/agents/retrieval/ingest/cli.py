"""CLI da ingestão.

Mora dentro do pacote, e não em `scripts/`, porque o `.dockerignore` não copia
`scripts/` para a imagem — o role `ingest` do entrypoint precisa de um módulo
importável.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conformidade.agents.retrieval.ingest.pipeline import ingerir
from conformidade.agents.retrieval.ingest.store import salvar_chunks


def construir_parser(raiz: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conformidade-ingest", description=__doc__)
    parser.add_argument("--manifesto", type=Path, default=raiz / "corpus" / "sources.yaml")
    parser.add_argument("--cache", type=Path, default=raiz / ".corpus-cache")
    parser.add_argument("--saida", type=Path, default=raiz / "corpus" / "chunks.jsonl")
    parser.add_argument("--baixar", action="store_true", help="baixa o que não estiver em cache")
    parser.add_argument("--limite-tokens", type=int, default=480)
    return parser


def main(argv: list[str] | None = None, raiz: Path | None = None) -> int:
    raiz = raiz or Path.cwd()
    args = construir_parser(raiz).parse_args(argv)

    chunks, relatorio = ingerir(
        manifesto=args.manifesto,
        cache=args.cache,
        baixar=args.baixar,
        limite_tokens=args.limite_tokens,
    )

    print(f"corpus_versao      : {relatorio.corpus_versao}")
    print(f"páginas            : {relatorio.total_paginas}")
    print(f"chunks             : {relatorio.total_chunks}")
    print(f"páginas com erro   : {relatorio.paginas_com_erro}")
    print(f"acima do limite    : {relatorio.chunks_acima_do_limite}")
    if relatorio.paginas_ausentes:
        print(f"ausentes do cache  : {relatorio.paginas_ausentes}")
        print("  (use --baixar para coletá-las)")

    com_erro = [p for p in relatorio.por_pagina if p.erro]
    for p in com_erro:
        print(f"  ERRO {p.page_id}: {p.erro}", file=sys.stderr)

    if not chunks:
        print("nenhum chunk produzido", file=sys.stderr)
        return 2

    salvar_chunks(chunks, args.saida)
    print(f"\nescrito: {args.saida} ({relatorio.total_chunks} chunks)")

    print("\npáginas com mais chunks:")
    for p in sorted(relatorio.por_pagina, key=lambda x: -x.chunks)[:8]:
        print(f"  {p.chunks:5}  {p.page_id}  (seções={p.secoes}, máx={p.tokens_max} tok)")

    return 1 if com_erro else 0


if __name__ == "__main__":
    sys.exit(main())
