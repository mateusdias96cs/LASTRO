"""Geração de embeddings.

Modelo **local** (`bge-small-en-v1.5` via fastembed/ONNX), não API. Três razões,
na ordem em que pesaram:

* custo zero de verdade, sem cota — free tier é zero até mudar a política;
* determinismo: modelo fixado por nome e revisão não muda debaixo do índice.
  Um provedor que atualiza os pesos em silêncio invalida o índice inteiro e
  faz todo eval de regressão perder o sentido;
* o eval roda em CI, e depender de rede e limite de taxa num portão que reprova
  build é fragilidade gratuita.

O provider é um protocolo porque o `FakeProvider` permite testar todo o
pipeline de recuperação sem baixar 130 MB de pesos nem tocar na rede.

Observação de arquitetura: as 36 consultas são fixas, então seus vetores são
pré-computados e versionados. Em tempo de request **nada** é embeddado — a
imagem da API não precisa do fastembed, e a mesma consulta produz sempre o
mesmo vetor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

import numpy as np

MODELO_PADRAO = "BAAI/bge-small-en-v1.5"
DIMENSAO_PADRAO = 384


@runtime_checkable
class EmbeddingProvider(Protocol):
    nome: str
    dimensao: int

    def embed(self, textos: Sequence[str]) -> np.ndarray: ...


class FastEmbedProvider:
    """Modelo real, via ONNX Runtime. Não puxa PyTorch."""

    def __init__(self, nome: str = MODELO_PADRAO, cache: str | None = None) -> None:
        from fastembed import TextEmbedding

        self.nome = nome
        self._modelo = TextEmbedding(model_name=nome, cache_dir=cache)
        self.dimensao = DIMENSAO_PADRAO

    def embed(self, textos: Sequence[str]) -> np.ndarray:
        if not textos:
            return np.zeros((0, self.dimensao), dtype=np.float32)
        vetores = np.array(list(self._modelo.embed(list(textos))), dtype=np.float32)
        self.dimensao = vetores.shape[1]
        return normalizar(vetores)


class FakeProvider:
    """Vetores determinísticos derivados de hash do texto.

    Não tem semântica alguma — serve só para exercitar índice, fusão e
    harness sem rede. Um teste que dependa de *qualidade* semântica não pode
    usar este provider, e nenhum usa.
    """

    def __init__(self, dimensao: int = 32) -> None:
        self.nome = "fake"
        self.dimensao = dimensao

    def embed(self, textos: Sequence[str]) -> np.ndarray:
        saida = np.zeros((len(textos), self.dimensao), dtype=np.float32)
        for i, texto in enumerate(textos):
            semente = int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:8], "big")
            gerador = np.random.default_rng(semente)
            saida[i] = gerador.standard_normal(self.dimensao)
        return normalizar(saida)


def normalizar(vetores: np.ndarray) -> np.ndarray:
    """Normaliza L2 para que produto interno seja similaridade de cosseno."""
    normas = np.linalg.norm(vetores, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    return (vetores / normas).astype(np.float32)


def em_lotes(itens: Sequence[str], tamanho: int = 64) -> Iterable[Sequence[str]]:
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio : inicio + tamanho]
