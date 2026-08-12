"""Ponta a ponta: arquivo entra, configuração corrigida sai.

    from conformidade.pipeline import auditar
    print(auditar(open("compose.yaml").read(), "compose.yaml").markdown)

Encadeia as quatro camadas:

    1  parser + regras     detecta o achado a partir do arquivo
    2  recuperação         busca o respaldo oficial
    3  análise (LLM)       contextualiza e explica
    4  crítico + correção  verifica, conserta o arquivo e monta o relatório

## A camada 3 é opcional

A configuração corrigida sai da camada 1 mais o catálogo de patches — nada
disso passa por modelo. Sem Azure configurado, ou com a API fora do ar, o
usuário continua recebendo o arquivo pronto para colar; o que se perde é a
narrativa do "por quê" e a citação da fonte oficial.

Isso não é degradação acidental, é o desenho: o LLM explica, não decide. Fazer
a entrega principal depender dele seria colocar a parte não determinística no
caminho crítico de uma ferramenta de auditoria.

## O arquivo é dado

Nada do conteúdo enviado é interpretado como instrução em nenhuma camada. Onde
ele aparece no relatório, aparece como evidência recortada dentro de bloco de
código.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.critic import criticar
from conformidade.agents.critic.aplicar import Aplicacao, aplicar
from conformidade.agents.critic.contracts import AchadoCriticado, Formato
from conformidade.agents.deterministic import ArtifactKind, Finding, analyze

_FORMATO = {
    ArtifactKind.DOCKERFILE: Formato.DOCKERFILE,
    ArtifactKind.DOCKER_COMPOSE: Formato.COMPOSE,
    ArtifactKind.KUBERNETES: Formato.KUBERNETES,
}


@dataclass
class Resultado:
    arquivo: str
    formato: Formato
    achados: list[Finding]
    aplicacao: Aplicacao
    criticados: list[tuple[EntradaAnalise, AchadoCriticado]] = field(default_factory=list)
    com_analise: bool = False

    @property
    def markdown(self) -> str:
        from conformidade.agents.critic.relatorio import em_markdown

        return em_markdown(self)


def _entrada(arquivo: str, achado: Finding, contexto: str, recuperacao) -> EntradaAnalise:
    return EntradaAnalise(
        arquivo=arquivo,
        control_id=achado.control_id,
        severidade_detectada=achado.severity,
        target=achado.target,
        linha=achado.location.start_line if achado.location else None,
        evidencia=achado.evidence,
        mensagem=achado.message,
        contexto=contexto,
        recuperacao=recuperacao,
    )


def _sem_analise(achado: Finding) -> AchadoAnalisado:
    """Achado sem passar pelo LLM: o que a camada 1 sabe, e nada além.

    Confiança alta porque a detecção é determinística — o que falta é a
    contextualização, não a certeza sobre o fato.
    """
    return AchadoAnalisado(
        control_id=achado.control_id,
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=achado.severity,
        explicacao=achado.message,
        como_corrigir=achado.remediation or "",
        citacoes=[],
        confianca=Confianca.ALTA,
    )


def auditar(
    conteudo: str,
    arquivo: str = "entrada.yaml",
    contexto: str = "",
    analisador=None,
    recuperador=None,
) -> Resultado:
    """Roda as quatro camadas e devolve o resultado pronto para renderizar.

    `analisador` e `recuperador` são injetados para a avaliação poder trocá-los
    por duplos. Ausentes, a camada 3 é pulada e o resultado sai determinístico.
    """
    relatorio = analyze(conteudo, filename=arquivo)
    achados = list(relatorio.findings)
    formato = _FORMATO.get(relatorio.artifact.kind, Formato.COMPOSE)

    aplicacao = aplicar(conteudo, achados, formato)

    criticados: list[tuple[EntradaAnalise, AchadoCriticado]] = []
    com_analise = analisador is not None

    for achado in achados:
        recuperacao = None
        if recuperador is not None:
            try:
                recuperacao = recuperador(achado.control_id)
            except Exception:  # noqa: BLE001 - fonte indisponível não derruba a auditoria
                recuperacao = None

        entrada = _entrada(arquivo, achado, contexto, recuperacao)
        if analisador is None:
            saida = _sem_analise(achado)
        else:
            try:
                saida = analisador.analisar(entrada)
            except Exception:  # noqa: BLE001 - o arquivo corrigido não depende do LLM
                saida = _sem_analise(achado)
        criticados.append((entrada, criticar(entrada, saida)))

    return Resultado(
        arquivo=arquivo,
        formato=formato,
        achados=achados,
        aplicacao=aplicacao,
        criticados=criticados,
        com_analise=com_analise,
    )
