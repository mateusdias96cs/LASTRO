#!/usr/bin/env python3
"""Atalho para a indexação densa a partir do repositório.

    python scripts/indexar.py

A lógica mora em `conformidade.agents.retrieval.index.cli`, que também é o
ponto de entrada do role `index` da imagem.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.agents.retrieval.index.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(raiz=RAIZ))
