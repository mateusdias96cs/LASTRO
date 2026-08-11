#!/usr/bin/env python3
"""Avaliação do agente de análise (camada 3).

    python scripts/avaliar_analise.py                  # roda os duplos
    python scripts/avaliar_analise.py --duplo oraculo  # só um

Enquanto o agente com LLM não existe, mede os duplos — o que já valida o
conjunto de casos e prova que os verificadores discriminam.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.evals.analise import carregar, formatar, rodar  # noqa: E402
from conformidade.evals.analise import duplos as d  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duplo", default=None, help="oraculo | honesto | alucina | ...")
    parser.add_argument("--detalhe", action="store_true", help="mostra cada reprovação")
    args = parser.parse_args()

    conjunto = carregar()
    disponiveis = {
        "oraculo": lambda: d.AnalisadorOraculo(conjunto),
        "honesto": d.AnalisadorHonesto,
        "alucina": d.AnalisadorQueAlucina,
        "pressao": d.AnalisadorQueCedeAPressao,
        "troca": d.AnalisadorQueTrocaOControle,
        "preguicoso": d.AnalisadorPreguicoso,
        "distrator": d.AnalisadorQueCitaDistrator,
    }

    nomes = [args.duplo] if args.duplo else list(disponiveis)
    print(f"casos: {len(conjunto.casos)} em {len(conjunto.por_nivel())} níveis\n")
    print(f"{'analisador':14} {'casos':>8} {'cit.falsas':>11}  veredito")
    print("-" * 50)

    for nome in nomes:
        fabrica = disponiveis.get(nome)
        if fabrica is None:
            print(f"duplo desconhecido: {nome}", file=sys.stderr)
            return 2
        relatorio = rodar(fabrica(), conjunto)
        marca = "APROVA" if relatorio.aprovado else "reprova"
        print(
            f"{nome:14} {relatorio.aprovados:>4}/{relatorio.total:<3} "
            f"{relatorio.citacoes_nao_literais:>11}  {marca}"
        )
        if args.detalhe:
            print(formatar(relatorio))

    # O oráculo é a checagem de sanidade do conjunto: se ele reprova, algum
    # caso tem expectativas que se contradizem e nenhum agente passaria.
    oraculo = rodar(d.AnalisadorOraculo(conjunto), conjunto)
    print()
    if oraculo.aprovado:
        print("conjunto íntegro: todos os casos são satisfazíveis")
        return 0
    print("CONJUNTO QUEBRADO — casos insatisfazíveis:", file=sys.stderr)
    for r in oraculo.resultados:
        if not r.passou:
            print(f"  {r.id}: {r.falhas}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
