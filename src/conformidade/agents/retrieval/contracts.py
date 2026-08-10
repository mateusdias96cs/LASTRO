"""Contratos do agente de recuperação.

Definidos antes da implementação porque o harness de eval depende deles: dá
para medir um retriever falso, um lexical simples e o híbrido final com o mesmo
código de métrica.

Regra de proveniência: todo trecho recuperado carrega origem, URL, licença e o
**texto original exato**. Não é firula — o agente crítico (camada 4) precisa
verificar a citação contra a fonte, e no mesmo idioma do original.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from conformidade.agents.retrieval.controls import DocumentoCanonico


class Chunk(BaseModel):
    """Trecho indexável do corpus."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    page_id: str  # casa com `id` em corpus/sources.yaml
    url: str
    fonte: str  # docker | kubernetes | nist
    licenca: str
    camada: int  # 1 normativo · 2 risco · 3 mecanismo do SO
    doc_versao: str
    heading_path: str  # "Security > Pod Security Standards > Restricted"
    texto: str  # original exato, em inglês, para citação verificável
    content_sha256: str


class TrechoRecuperado(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float
    posicao: int
    origem_do_score: str = ""  # "lexical" | "denso" | "rrf" | "rerank"


class ResultadoRecuperacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    control_id: str
    consulta: str
    # Âncora determinística: o texto autoritativo que nós escrevemos, sempre
    # presente independentemente do que a busca devolveu. É o que garante ao
    # agente de análise a afirmação correta mesmo quando o ranking erra — e a
    # medição da Fase 3 mostrou que ele erra em 5 dos 36 controles.
    documento_canonico: DocumentoCanonico | None = None
    trechos: list[TrechoRecuperado] = Field(default_factory=list)
    # Vazio é resposta válida: controle sem cobertura oficial não deve receber
    # um trecho irrelevante só para não voltar vazio.
    corpus_versao: str = ""


@runtime_checkable
class Retriever(Protocol):
    """Qualquer coisa que o harness de eval consegue medir."""

    def buscar(self, control_id: str, consulta: str, k: int = 10) -> ResultadoRecuperacao: ...
