"""Contrato de saída do agente de análise (camada 3).

Definido **antes** do agente, porque é ele que torna a avaliação possível. Saída
em texto livre só poderia ser julgada por outro LLM — não-determinístico, caro e
que precisaria da própria validação. Saída estruturada permite checar a maior
parte das falhas com asserção comum.

A restrição central do desenho: **o LLM não decide se é violação.** A camada 1
já decidiu, deterministicamente. O trabalho aqui é mais estreito — contextualizar,
priorizar, explicar em português e citar a fonte. Por isso não existe veredito
"não é violação": existe `NAO_SE_APLICA`, que reconhece a exceção documentada
sem apagar o achado.

Se o agente pudesse inventar ou anular achado, a reprodutibilidade das camadas
1 e 2 viraria decoração.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.contracts import ResultadoRecuperacao


class Veredito(StrEnum):
    """O que o contexto faz com o achado — nunca se ele existe."""

    CONFIRMADO = "confirmado"
    ATENUADO_POR_CONTEXTO = "atenuado_por_contexto"
    AGRAVADO_POR_CONTEXTO = "agravado_por_contexto"
    # A configuração isolada não permite concluir. Ex.: "não declara usuário"
    # quando a imagem pode trazer USER embutido — não é verificável a partir
    # do arquivo, e afirmar que é problema seria falso positivo.
    NAO_VERIFICAVEL = "nao_verificavel"
    # Exceção documentada em "Quando não se aplica" cobre este caso.
    NAO_SE_APLICA = "nao_se_aplica"


class Confianca(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class Citacao(BaseModel):
    """Trecho da fonte oficial que sustenta a afirmação.

    `trecho_exato` precisa ser cópia literal do texto do chunk. É o que permite
    verificar citação sem LLM: substring ou não é. Citação inventada é a falha
    mais perigosa desta camada, porque soa convincente.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    trecho_exato: str
    url: str = ""


class AchadoAnalisado(BaseModel):
    model_config = ConfigDict(frozen=True)

    control_id: str
    veredito: Veredito
    severidade_ajustada: Severity
    # Obrigatória quando a severidade muda ou o veredito não é CONFIRMADO.
    justificativa_do_ajuste: str = ""

    explicacao: str  # em português, para quem não é especialista
    como_corrigir: str  # em português, com o comando ou trecho concreto

    citacoes: list[Citacao] = Field(default_factory=list)
    confianca: Confianca = Confianca.MEDIA


class RelatorioAnalise(BaseModel):
    model_config = ConfigDict(frozen=True)

    arquivo: str
    achados: list[AchadoAnalisado] = Field(default_factory=list)
    resumo: str = ""
    # Vazio é resposta válida e desejável quando a recuperação não trouxe
    # respaldo: melhor admitir do que forçar uma citação.
    sem_respaldo_oficial: list[str] = Field(default_factory=list)


class EntradaAnalise(BaseModel):
    """O que a camada 3 recebe. Montado pelas camadas 1 e 2, nunca pelo LLM."""

    arquivo: str
    control_id: str
    severidade_detectada: Severity
    target: str | None = None
    linha: int | None = None
    evidencia: str | None = None
    mensagem: str = ""
    # Contexto declarado por quem envia (tipo de carga, ambiente). É o que o
    # agente usa para aplicar as exceções documentadas.
    contexto: str = ""
    recuperacao: ResultadoRecuperacao | None = None


@runtime_checkable
class Analisador(Protocol):
    """Qualquer coisa que a avaliação consegue medir — o agente real, um
    duplo de teste, ou uma variação de prompt."""

    def analisar(self, entrada: EntradaAnalise) -> AchadoAnalisado: ...
