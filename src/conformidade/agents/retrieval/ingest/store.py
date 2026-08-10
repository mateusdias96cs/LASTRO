"""Persistência dos chunks em JSONL.

JSONL e não banco, nesta fase, de propósito: o artefato da ingestão precisa ser
inspecionável, diferenciável em revisão de código e carregável sem
infraestrutura. A Fase 3 carrega este mesmo arquivo no pgvector — o formato é
o contrato entre as duas fases.

A escrita é ordenada e sem espaço supérfluo para que dois runs sobre o mesmo
conteúdo produzam arquivos idênticos byte a byte.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from conformidade.agents.retrieval.contracts import Chunk


def salvar_chunks(chunks: Iterable[Chunk], destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destino.open("w", encoding="utf-8", newline="\n") as saida:
        for chunk in chunks:
            saida.write(json.dumps(chunk.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")
            total += 1
    return total


def carregar_chunks(origem: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with origem.open("r", encoding="utf-8") as entrada:
        for linha in entrada:
            linha = linha.strip()
            if linha:
                chunks.append(Chunk.model_validate_json(linha))
    return chunks
