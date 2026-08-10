#!/usr/bin/env python3
"""Atalho para a ingestão a partir do repositório.

    python scripts/ingerir.py --baixar     # coleta e ingere
    python scripts/ingerir.py              # reingere a partir do cache

A lógica mora em `conformidade.agents.retrieval.ingest.cli`, que também é o
ponto de entrada do role `ingest` da imagem.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from conformidade.agents.retrieval.ingest.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(raiz=RAIZ))
