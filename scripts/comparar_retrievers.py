#!/usr/bin/env python3
"""Compara lexical, denso e híbrido sobre o mesmo gabarito.

    python scripts/comparar_retrievers.py

Roda os três modos com o mesmo índice, o mesmo gabarito e o mesmo código de
métrica — a diferença entre as linhas mede só o método de recuperação.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.agents.retrieval.index import (  # noqa: E402
    HybridRetriever,
    LexicalIndex,
)
from conformidade.agents.retrieval.index.build import (  # noqa: E402
    carregar_consultas,
    carregar_indice_denso,
)
from conformidade.agents.retrieval.ingest import carregar_chunks  # noqa: E402
from conformidade.evals.golden import carregar_gabarito  # noqa: E402
from conformidade.evals.harness import RelatorioEval, rodar  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=RAIZ / "corpus" / "chunks.jsonl")
    parser.add_argument("--indice", type=Path, default=RAIZ / "corpus" / "index")
    parser.add_argument("-k", type=int, default=10)
    args = parser.parse_args()

    chunks = carregar_chunks(args.chunks)
    lexical = LexicalIndex(chunks)
    denso = carregar_indice_denso(chunks, args.indice)
    consultas = carregar_consultas(args.indice)
    gabarito = carregar_gabarito()

    modos: dict[str, HybridRetriever] = {
        "lexical": HybridRetriever(chunks, lexical=lexical),
        "denso": HybridRetriever(chunks, denso=denso, vetores_de_consulta=consultas),
        "hibrido": HybridRetriever(
            chunks, lexical=lexical, denso=denso, vetores_de_consulta=consultas
        ),
    }

    print(f"chunks: {len(chunks)}\n")
    cab = f"{'modo':10} {'R@5':>6} {'R@10':>6} {'P@5':>6} {'MRR':>6} {'nDCG':>6} {'distr':>6}"
    print(cab)
    print("-" * len(cab))

    relatorios: dict[str, RelatorioEval] = {}
    for nome, retriever in modos.items():
        rel = rodar(retriever, gabarito, k=args.k)
        relatorios[nome] = rel
        print(
            f"{nome:10} {rel.recall_at_5:6.3f} {rel.recall_at_10:6.3f} "
            f"{rel.precision_at_5:6.3f} {rel.mrr:6.3f} {rel.ndcg_at_10:6.3f} "
            f"{rel.controles_com_distrator:6}"
        )

    print()
    for nome, rel in relatorios.items():
        if rel.aprovado:
            print(f"{nome:10} APROVADO")
        else:
            print(f"{nome:10} reprovado")
            for violacao in rel.violacoes_de_limiar:
                print(f"           - {violacao}")

    melhor = relatorios["hibrido"]
    print("\ndistratores remanescentes no híbrido:")
    for r in melhor.por_controle:
        if r.distratores_no_top_5:
            print(f"  {r.control_id}: {r.distratores_no_top_5}")

    return 0 if melhor.aprovado else 1


if __name__ == "__main__":
    sys.exit(main())
