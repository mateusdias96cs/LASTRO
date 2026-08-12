#!/usr/bin/env python3
"""Roda a avaliação da camada 4 contra o crítico real e os duplos.

    python scripts/avaliar_critico.py

O crítico real precisa fazer 100%: ele é determinístico, e qualquer caso
reprovado é defeito. Os duplos precisam falhar cada um do seu jeito — se o
cego passar bem, o conjunto não tem casos que exigem reparo; se o paranoico
passar bem, faltam casos que exigem aprovação.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.agents.critic import criticar  # noqa: E402
from conformidade.evals.critico import (  # noqa: E402
    CASOS,
    critico_cego,
    critico_paranoico,
    rodar,
)


def main() -> int:
    print(f"casos: {len(CASOS)}\n")
    print(f"{'crítico':16} {'casos':>7}  veredito")
    print("-" * 40)
    relatorios = {}
    for nome, fn in (("real", criticar), ("cego", critico_cego), ("paranoico", critico_paranoico)):
        rel = rodar(fn)
        relatorios[nome] = rel
        marca = "APROVA" if rel.aprovado else "reprova"
        print(f"{nome:16} {f'{rel.aprovados}/{rel.total}':>7}  {marca}")

    real = relatorios["real"]
    print()
    if not real.aprovado:
        print("crítico real REPROVADO:")
        for r in real.resultados:
            if not r.passou:
                print(f"  {r.id}: {r.falhas or r.erro}")
        return 1
    if relatorios["cego"].aprovado or relatorios["paranoico"].aprovado:
        print("conjunto NÃO discrimina: um duplo passou e não deveria")
        return 1
    print("conjunto discrimina: o real passa, os dois duplos falham por motivos opostos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
