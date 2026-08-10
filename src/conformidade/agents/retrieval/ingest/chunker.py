"""Fatiamento de seções em chunks.

Duas restrições moldam o desenho:

* **512 tokens** é o limite do `bge-small-en-v1.5`. Texto além disso é
  truncado silenciosamente pelo modelo — o pior tipo de falha, porque o chunk
  parece indexado e não está.
* **A medição da Fase 1 provou que documento grande é invisível.** O NIST tem
  22.560 tokens contra média de 7.462 do corpus, e a normalização por tamanho
  do BM25 o afundava a ponto de nunca aparecer no top-10, mesmo sendo a melhor
  fonte de vários controles. Fatiar não é refinamento, é o que o torna
  alcançável.

O `heading_path` é prefixado ao texto do chunk de propósito: um trecho
recuperado isoladamente precisa carregar o contexto de onde veio, tanto para a
busca casar quanto para o agente de análise entender o que está lendo.
"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel

from conformidade.agents.retrieval.ingest.extract import Secao

# Margem sobre os 512 do modelo: a estimativa de tokens é aproximada e
# truncamento silencioso é pior que chunk pequeno demais.
LIMITE_TOKENS = 480

# Piso definido por medição, não por intuição. Com 20 tokens, 2,1% das seções
# eram descartadas — e a amostra mostrou que essa faixa concentra justamente o
# texto mais normativo do corpus, as entradas terse de referência:
#
#   "cap_add specifies additional container capabilities as strings."   (19t)
#   "pids tunes a container's PIDs limit, set as an integer."           (13t)
#
# Perder isso custa mais do que o ruído que o piso evita. Abaixo de 12 tokens
# o conteúdo é legenda, rótulo de navegação ou fragmento solto.
MINIMO_TOKENS = 12

_FIM_DE_FRASE = re.compile(r"(?<=[.!?:;])\s+")


def estimar_tokens(texto: str) -> int:
    """Estimativa conservadora, sem carregar o tokenizador do modelo.

    Usa o maior entre duas aproximações: palavras × 1,35 (razão típica de
    subpalavras em inglês para modelos BERT) e caracteres ÷ 4 (melhor para
    trecho de código, onde identificadores viram muitos tokens). Pegar o maior
    erra para o lado seguro.

    A Fase 3 substitui isto pelo tokenizador real do fastembed.
    """
    palavras = len(texto.split())
    return max(int(palavras * 1.35), len(texto) // 4)


class ChunkBruto(BaseModel):
    """Chunk antes de receber os metadados da página."""

    indice: int
    heading_path: str
    texto: str
    tokens: int
    ordem_secao: int


def _partir_por_frase(texto: str, limite: int) -> list[str]:
    """Quebra em fronteira de frase; só corta no meio se uma frase sozinha
    ultrapassar o limite."""
    partes: list[str] = []
    atual: list[str] = []
    tokens_atual = 0

    for frase in _FIM_DE_FRASE.split(texto):
        frase = frase.strip()
        if not frase:
            continue
        tokens_frase = estimar_tokens(frase)

        if tokens_frase > limite:
            if atual:
                partes.append(" ".join(atual))
                atual, tokens_atual = [], 0
            partes.extend(_partir_por_palavra(frase, limite))
            continue

        if tokens_atual + tokens_frase > limite and atual:
            partes.append(" ".join(atual))
            atual, tokens_atual = [], 0

        atual.append(frase)
        tokens_atual += tokens_frase

    if atual:
        partes.append(" ".join(atual))
    return partes


def _partir_por_palavra(texto: str, limite: int) -> list[str]:
    """Último recurso: frase única maior que o limite (tabela, bloco de código).

    Acumula palavra a palavra medindo o tamanho real em vez de dividir por um
    número fixo de palavras. A diferença importa em página de referência de
    CLI, cheia de `--identificadores-longos`: ali a estimativa por caracteres
    domina a por palavras, e um corte fixo de palavras estoura o limite.
    """
    partes: list[str] = []
    atual: list[str] = []
    chars = 0

    for palavra in texto.split():
        n_palavras = len(atual) + 1
        n_chars = chars + len(palavra) + (1 if atual else 0)
        if atual and max(int(n_palavras * 1.35), n_chars // 4) > limite:
            partes.append(" ".join(atual))
            atual, chars = [palavra], len(palavra)
        else:
            atual.append(palavra)
            chars = n_chars

    if atual:
        partes.append(" ".join(atual))
    return partes


def fatiar(
    secoes: list[Secao], limite: int = LIMITE_TOKENS, minimo: int = MINIMO_TOKENS
) -> list[ChunkBruto]:
    """Seções → chunks, respeitando o limite de tokens.

    Seções curtas demais são descartadas: um chunk de 5 tokens é ruído de
    navegação ou legenda, nunca evidência utilizável.
    """
    chunks: list[ChunkBruto] = []
    indice = 0

    for secao in secoes:
        prefixo = f"{secao.heading_path}\n\n" if secao.heading_path else ""
        tokens_prefixo = estimar_tokens(prefixo)
        limite_corpo = max(minimo, limite - tokens_prefixo)

        corpo_total = estimar_tokens(secao.texto)
        partes = (
            [secao.texto]
            if corpo_total <= limite_corpo
            else _partir_por_frase(secao.texto, limite_corpo)
        )

        for parte in partes:
            if estimar_tokens(parte) < minimo:
                continue
            texto = f"{prefixo}{parte}".strip()

            # Guarda final. As etapas acima somam estimativas por frase, e a
            # estimativa não é aditiva (`max` de duas fórmulas). Sem esta
            # verificação sobre o texto montado, chunks passavam do limite e
            # seriam truncados em silêncio pelo modelo — o pior tipo de falha,
            # porque o chunk parece indexado e não está.
            finais = (
                [texto] if estimar_tokens(texto) <= limite else _partir_por_palavra(texto, limite)
            )

            for final in finais:
                if estimar_tokens(final) < minimo:
                    continue
                chunks.append(
                    ChunkBruto(
                        indice=indice,
                        heading_path=secao.heading_path,
                        texto=final,
                        tokens=estimar_tokens(final),
                        ordem_secao=secao.ordem,
                    )
                )
                indice += 1

    return chunks


def id_do_chunk(page_id: str, texto: str, indice: int) -> str:
    """Identificador estável.

    Inclui o hash do conteúdo, e não só o índice: assim, reordenar a página não
    muda o id de um chunk cujo texto não mudou, e a supressão de um achado
    aceito sobrevive à reingestão.
    """
    digest = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:10]
    return f"{page_id}#{indice:04d}-{digest}"
