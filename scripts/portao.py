#!/usr/bin/env python3
"""Portão de qualidade — o mesmo comando local e no pipeline.

    python scripts/portao.py                 # roda tudo, sai 1 se reprovar
    python scripts/portao.py --sem-lint      # pula ruff
    python scripts/portao.py --sem-testes    # pula pytest
    python scripts/portao.py --gravar-baseline

Sem argumento, executa a sequência inteira: lint, testes, integridade do
corpus, limiares do gabarito e regressão contra a linha de base.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.evals.portao import (  # noqa: E402
    executar,
    formatar,
    gravar_baseline,
)

CHUNKS = RAIZ / "corpus" / "chunks.jsonl"
INDICE = RAIZ / "corpus" / "index"
BASELINE = RAIZ / "evals" / "baseline_metricas.json"


def rodar_comando(nome: str, comando: list[str]) -> bool:
    print(f"\n── {nome} " + "─" * max(0, 56 - len(nome)))
    processo = subprocess.run(comando, cwd=RAIZ)
    ok = processo.returncode == 0
    print(f"   {'ok' if ok else 'FALHA'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sem-lint", action="store_true")
    parser.add_argument("--sem-testes", action="store_true")
    parser.add_argument("--sem-limiares", action="store_true")
    parser.add_argument(
        "--gravar-baseline",
        action="store_true",
        help="regrava a linha de base com as métricas atuais",
    )
    args = parser.parse_args()

    falhas: list[str] = []

    if not args.sem_lint:
        if not rodar_comando("lint (ruff check)", ["ruff", "check", "."]):
            falhas.append("lint")
        if not rodar_comando("formato (ruff format)", ["ruff", "format", "--check", "."]):
            falhas.append("formato")

    if not args.sem_testes:
        if not rodar_comando("testes (pytest)", ["pytest", "-q"]):
            falhas.append("testes")

    print("\n── recuperação " + "─" * 46)
    resultado = executar(CHUNKS, INDICE, BASELINE, checar_limiares=not args.sem_limiares)
    print(formatar(resultado))

    if resultado.metricas:
        print("\n   métricas:")
        for nome, valor in sorted(resultado.metricas.items()):
            print(f"     {nome:26} {valor}")

    if args.gravar_baseline:
        if not resultado.metricas:
            print("\nsem métricas para gravar", file=sys.stderr)
            return 2
        gravar_baseline(BASELINE, resultado.metricas)
        print(f"\nlinha de base gravada em {BASELINE}")
        return 0

    if not resultado.aprovado:
        falhas.append("recuperação")

    print("\n" + "=" * 60)
    if falhas:
        print(f"PORTÃO REPROVADO — etapas com falha: {', '.join(falhas)}")
        return 1
    print("PORTÃO APROVADO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
