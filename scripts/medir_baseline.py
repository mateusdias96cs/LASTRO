#!/usr/bin/env python3
"""Roda a avaliação de recuperação contra um diretório de páginas.

Existe para que o número da linha de base seja reproduzível por qualquer pessoa,
e não uma afirmação em documento. Enquanto a Fase 2 (ingestão) não existe, as
páginas vêm de um diretório passado na linha de comando.

    python scripts/medir_baseline.py --corpus /caminho/paginas
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.evals.baseline import BaselineLexical  # noqa: E402
from conformidade.evals.golden import carregar_gabarito  # noqa: E402
from conformidade.evals.harness import formatar, rodar  # noqa: E402

FONTES = RAIZ / "corpus" / "sources.yaml"


def extrair_texto(caminho: Path) -> str:
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    bruto = re.sub(r"<script\b.*?</script>", " ", bruto, flags=re.S | re.I)
    bruto = re.sub(r"<style\b.*?</style>", " ", bruto, flags=re.S | re.I)
    bruto = re.sub(r"<[^>]+>", " ", bruto)
    return re.sub(r"\s+", " ", html.unescape(bruto))


def slug_da_url(url: str) -> str:
    return url.replace("https://", "").replace("/", "_").rstrip("_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--corpus", type=Path, help="diretório de páginas (nível de página)")
    grupo.add_argument("--chunks", type=Path, help="chunks.jsonl (nível de chunk)")
    parser.add_argument("-k", type=int, default=10, help="quantos trechos recuperar")
    args = parser.parse_args()

    if args.chunks:
        from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
        from conformidade.agents.retrieval.ingest import carregar_chunks

        chunks = carregar_chunks(args.chunks)
        print(f"chunks carregados: {len(chunks)}\n")
        relatorio = rodar(
            HybridRetriever(chunks, lexical=LexicalIndex(chunks)), carregar_gabarito(), k=args.k
        )
        print(formatar(relatorio))
        for r in relatorio.por_controle:
            if r.distratores_no_top_5:
                print(f"  distrator {r.control_id}: {r.distratores_no_top_5}")
        return 0 if relatorio.aprovado else 1

    manifesto = yaml.safe_load(FONTES.read_text(encoding="utf-8"))
    corpus: dict[str, str] = {}
    ausentes: list[str] = []

    for pagina in manifesto["paginas"]:
        slug = slug_da_url(pagina["url"])
        html_path = args.corpus / f"{slug}.html"
        txt_path = args.corpus / f"{slug}.txt"
        if html_path.exists():
            corpus[pagina["id"]] = extrair_texto(html_path)
        elif txt_path.exists():
            # Fonte já extraída (o NIST é PDF, não HTML).
            corpus[pagina["id"]] = re.sub(
                r"\s+", " ", txt_path.read_text(encoding="utf-8", errors="replace")
            )
        else:
            ausentes.append(pagina["id"])

    if not corpus:
        print(f"nenhuma página encontrada em {args.corpus}", file=sys.stderr)
        return 2

    print(f"páginas carregadas: {len(corpus)}")
    if ausentes:
        print(f"ausentes (recall reportado é piso): {ausentes}")
    print()

    relatorio = rodar(BaselineLexical(corpus), carregar_gabarito(), k=args.k)
    print(formatar(relatorio))

    falhas = [r for r in relatorio.por_controle if r.distratores_no_top_5]
    if falhas:
        print()
        print("distratores no top-5:")
        for r in falhas:
            print(f"  {r.control_id}: {r.distratores_no_top_5}")

    return 0 if relatorio.aprovado else 1


if __name__ == "__main__":
    sys.exit(main())
