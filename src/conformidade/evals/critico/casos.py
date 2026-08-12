"""Conjunto de casos da camada 4.

## Por que Python e não YAML

Os casos da camada 3 são YAML porque descrevem **entrada para um LLM**: achado,
contexto, expectativa. São dados, e ficam melhor num arquivo que quem não
programa consegue editar.

Aqui o caso é outro animal. Ele precisa de um `AchadoAnalisado` completo cuja
citação seja **literal contra o texto de um chunk específico** — a checagem
central do crítico é `trecho in chunk.texto`. Em YAML isso obrigaria a
reconstruir chunk e citação a partir de campos soltos, e a literalidade
dependeria de o texto estar duplicado nos dois lugares sem divergir. Um erro de
digitação viraria "o crítico reprovou", não "o caso está errado".

Em Python o trecho é fatiado do próprio texto do chunk, então é literal por
construção. É também como `tests/test_critico.py` já monta esses objetos.

## O que cada caso declara

Veredito esperado e **quais verificadores** deveriam disparar. Só o veredito
seria fraco demais: um crítico que rebaixasse tudo pelo motivo errado passaria.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Citacao,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.critic.contracts import VereditoCritico
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.contracts import (
    Chunk,
    ResultadoRecuperacao,
    TrechoRecuperado,
)

# Texto real do Pod Security Standards. A citação boa é fatiada daqui, então é
# literal sem depender de eu copiar certo.
FONTE = "Privileged Pods disable most security mechanisms and must be disallowed."
TRECHO_BOM = "disable most security mechanisms and must be disallowed"

# `k8s:volumes` é distrator declarado do CONF-WLD-008 no gabarito da camada 2.
# O caso do distrator depende disso; há teste conferindo que continua sendo.
CONTROLE_COM_DISTRATOR = "CONF-WLD-008"
PAGINA_DISTRATORA = "k8s:volumes"
FONTE_DISTRATORA = "Read-only mounts can be recursive with the RecursiveReadOnly field."


@dataclass(frozen=True)
class CasoCritico:
    """Uma saída de analista e o que o crítico deveria fazer com ela."""

    id: str
    descricao: str
    entrada: EntradaAnalise
    saida: AchadoAnalisado
    veredito_esperado: VereditoCritico
    # Nomes de verificador que precisam aparecer nas objeções. Exigir só o
    # veredito deixaria passar um crítico que rebaixa pelo motivo errado.
    verificadores_esperados: frozenset[str] = field(default_factory=frozenset)
    # `True` quando o reparo correto esvazia as citações.
    sem_citacoes_ao_final: bool = False


def _chunk(chunk_id: str, page_id: str, texto: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        page_id=page_id,
        url=f"https://exemplo/{page_id}",
        fonte="kubernetes",
        licenca="CC-BY-4.0",
        camada=1,
        doc_versao="v",
        heading_path="H",
        texto=texto,
        content_sha256=chunk_id,
    )


CHUNK_BOM = _chunk("k8s:pss#0003-aa", "k8s:pod-security-standards", FONTE)
CHUNK_DISTRATOR = _chunk("k8s:volumes#0059-bb", PAGINA_DISTRATORA, FONTE_DISTRATORA)


def _entrada(control_id: str, chunks: list[Chunk]) -> EntradaAnalise:
    return EntradaAnalise(
        arquivo="deployment.yaml",
        control_id=control_id,
        severidade_detectada=Severity.CRITICAL,
        target="api",
        evidencia="privileged: true",
        mensagem="Executa em modo privilegiado.",
        recuperacao=ResultadoRecuperacao(
            control_id=control_id,
            consulta="q",
            trechos=[TrechoRecuperado(chunk=c, score=1.0, posicao=i) for i, c in enumerate(chunks)],
        ),
    )


def _saida(control_id: str = "CONF-WLD-001", **kwargs) -> AchadoAnalisado:
    base = {
        "control_id": control_id,
        "veredito": Veredito.CONFIRMADO,
        "severidade_ajustada": Severity.CRITICAL,
        "explicacao": (
            "O modo privilegiado remove o isolamento entre o container e o host, "
            "concedendo acesso a dispositivos e capacidades do kernel."
        ),
        "como_corrigir": "Remova `privileged: true` do manifesto.",
        "citacoes": [
            Citacao(chunk_id=CHUNK_BOM.chunk_id, trecho_exato=TRECHO_BOM, url=CHUNK_BOM.url)
        ],
        "confianca": Confianca.ALTA,
    }
    return AchadoAnalisado(**{**base, **kwargs})


_ENTRADA_PADRAO = _entrada("CONF-WLD-001", [CHUNK_BOM])
_ENTRADA_COM_DISTRATOR = _entrada(CONTROLE_COM_DISTRATOR, [CHUNK_BOM, CHUNK_DISTRATOR])


CASOS: tuple[CasoCritico, ...] = (
    # ------------------------------------------------------ deve aprovar
    CasoCritico(
        id="integra",
        descricao="saída bem fundamentada, citação literal — nada a reparar",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(),
        veredito_esperado=VereditoCritico.APROVADO,
    ),
    CasoCritico(
        id="sem-citacao-mas-coerente",
        descricao="não citou, e isso é aceitável — o crítico não exige citação",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(citacoes=[], confianca=Confianca.MEDIA),
        veredito_esperado=VereditoCritico.APROVADO,
    ),
    CasoCritico(
        id="ajuste-justificado",
        descricao="desviou do confirmado, mas explicou — o desvio é legítimo",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(
            veredito=Veredito.ATENUADO_POR_CONTEXTO,
            severidade_ajustada=Severity.LOW,
            justificativa_do_ajuste=(
                "O contexto corresponde à exceção documentada para agentes de "
                "infraestrutura, que precisam desse acesso por desenho."
            ),
        ),
        veredito_esperado=VereditoCritico.APROVADO,
    ),
    # ----------------------------------------------------- deve rebaixar
    CasoCritico(
        id="citacao-inventada",
        descricao="citou frase que não existe na fonte — a falha mais perigosa",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(
            citacoes=[
                Citacao(
                    chunk_id=CHUNK_BOM.chunk_id,
                    trecho_exato="the documentation forbids this in every environment",
                )
            ]
        ),
        veredito_esperado=VereditoCritico.REBAIXADO,
        verificadores_esperados=frozenset({"citacao_nao_literal", "confianca_sem_respaldo"}),
        sem_citacoes_ao_final=True,
    ),
    CasoCritico(
        id="fonte-inexistente",
        descricao="citou chunk que não estava entre os recuperados",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(citacoes=[Citacao(chunk_id="k8s:nunca#9999-zz", trecho_exato=TRECHO_BOM)]),
        veredito_esperado=VereditoCritico.REBAIXADO,
        verificadores_esperados=frozenset({"citacao_de_fonte_inexistente"}),
        sem_citacoes_ao_final=True,
    ),
    CasoCritico(
        id="cita-distrator",
        descricao="citou a página vizinha declarada no gabarito, não a do controle",
        entrada=_ENTRADA_COM_DISTRATOR,
        saida=_saida(
            control_id=CONTROLE_COM_DISTRATOR,
            citacoes=[
                Citacao(
                    chunk_id=CHUNK_DISTRATOR.chunk_id,
                    trecho_exato="mounts can be recursive with the RecursiveReadOnly field",
                    url=CHUNK_DISTRATOR.url,
                )
            ],
        ),
        veredito_esperado=VereditoCritico.REBAIXADO,
        verificadores_esperados=frozenset({"citou_distrator"}),
        sem_citacoes_ao_final=True,
    ),
    CasoCritico(
        id="veredito-sem-justificativa",
        descricao="desviou do confirmado sem explicar — volta ao determinístico",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(veredito=Veredito.NAO_VERIFICAVEL, justificativa_do_ajuste=""),
        veredito_esperado=VereditoCritico.REBAIXADO,
        verificadores_esperados=frozenset({"ajuste_sem_justificativa"}),
    ),
    CasoCritico(
        id="citacao-boa-e-ruim",
        descricao="uma citação se sustenta e outra não — só a ruim deve sair",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(
            citacoes=[
                Citacao(chunk_id=CHUNK_BOM.chunk_id, trecho_exato=TRECHO_BOM),
                Citacao(chunk_id=CHUNK_BOM.chunk_id, trecho_exato="frase que nao existe ali"),
            ]
        ),
        veredito_esperado=VereditoCritico.REBAIXADO,
        verificadores_esperados=frozenset({"citacao_nao_literal"}),
    ),
    # ---------------------------------------------------- deve descartar
    CasoCritico(
        id="controle-trocado",
        descricao="respondeu sobre outro controle — inventou achado",
        entrada=_ENTRADA_PADRAO,
        saida=_saida(control_id="CONF-K8S-005"),
        veredito_esperado=VereditoCritico.DESCARTADO,
        verificadores_esperados=frozenset({"controle_trocado"}),
        sem_citacoes_ao_final=True,
    ),
)


def deveriam_aprovar() -> tuple[CasoCritico, ...]:
    return tuple(c for c in CASOS if c.veredito_esperado is VereditoCritico.APROVADO)


def deveriam_reprovar() -> tuple[CasoCritico, ...]:
    return tuple(c for c in CASOS if c.veredito_esperado is not VereditoCritico.APROVADO)
