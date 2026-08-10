"""Construção e carga do índice denso.

Separa duas operações com custos muito diferentes:

* **indexar** — roda o modelo sobre os 1.224 chunks. Custa minutos de CPU e é
  feito no job de ingestão, não em tempo de request;
* **carregar** — lê os vetores do disco. Custa milissegundos e é o que a API faz.

Os vetores das 36 consultas são gravados à parte porque são pequenos (36 × 384
floats ≈ 55 KB) e **estáveis**: só mudam quando o catálogo ou o modelo mudam.
Versioná-los é o que permite a API responder sem carregar o modelo.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from conformidade.agents.retrieval.contracts import Chunk
from conformidade.agents.retrieval.embeddings import EmbeddingProvider, em_lotes
from conformidade.agents.retrieval.index.dense import DenseIndex, ordenar
from conformidade.agents.retrieval.queries import CONSULTAS

ARQ_VETORES = "vectors.npy"
ARQ_CONSULTAS = "query_vectors.npz"
ARQ_META = "index_meta.json"


def indexar_chunks(chunks: list[Chunk], provider: EmbeddingProvider, lote: int = 64) -> np.ndarray:
    """Vetores **na mesma ordem** de `chunks`.

    Não ordena internamente, de propósito. Uma versão anterior ordenava por
    `chunk_id` aqui e devolvia vetores nessa ordem, enquanto `DenseIndex`
    assume que `vetores[i]` corresponde a `chunks[i]` como recebido — e
    reordena os dois de novo. O resultado era dupla permutação: cada texto
    pareado com o vetor de outro chunk, sem erro nenhum, só respostas
    silenciosamente erradas.

    Deixar o alinhamento como responsabilidade de um único ponto (`DenseIndex`)
    elimina a classe inteira de bug.
    """
    textos = [c.texto for c in chunks]
    blocos = [provider.embed(list(bloco)) for bloco in em_lotes(textos, lote)]
    if not blocos:
        return np.zeros((0, provider.dimensao), dtype=np.float32)
    return np.vstack(blocos)


def indexar_consultas(provider: EmbeddingProvider) -> dict[str, np.ndarray]:
    ids = sorted(CONSULTAS)
    vetores = provider.embed([CONSULTAS[c] for c in ids])
    return {cid: vetores[i] for i, cid in enumerate(ids)}


def salvar_indice(
    destino: Path,
    vetores: np.ndarray,
    vetores_consulta: dict[str, np.ndarray],
    modelo: str,
    corpus_versao: str,
) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    np.save(destino / ARQ_VETORES, vetores)
    np.savez(destino / ARQ_CONSULTAS, **vetores_consulta)
    (destino / ARQ_META).write_text(
        json.dumps(
            {
                "modelo": modelo,
                "dimensao": int(vetores.shape[1]) if vetores.size else 0,
                "total_chunks": int(vetores.shape[0]),
                "corpus_versao": corpus_versao,
                "total_consultas": len(vetores_consulta),
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def carregar_consultas(origem: Path) -> dict[str, np.ndarray]:
    with np.load(origem / ARQ_CONSULTAS) as dados:
        return {chave: dados[chave].astype(np.float32) for chave in dados.files}


def carregar_indice_denso(chunks: list[Chunk], origem: Path) -> DenseIndex:
    """Os vetores foram gravados na ordem canônica; os chunks precisam vir na
    mesma antes de parear (ver `DenseIndex.carregar`)."""
    return DenseIndex(ordenar(chunks), np.load(origem / ARQ_VETORES))


def ler_meta(origem: Path) -> dict:
    caminho = origem / ARQ_META
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
