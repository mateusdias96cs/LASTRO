"""Renderização do relatório final.

Quatro seções, na ordem em que servem a quem não é especialista:

    1  a configuração corrigida, inteira, pronta para substituir o original
    2  o que estava errado e o que foi acrescentado — tabela curta
    3  o que exige decisão sua, com o motivo
    4  a fundamentação, para quem precisar defender a mudança

A ordem é a decisão de desenho mais importante aqui. Relatório de segurança
costuma abrir com achados e deixar o conserto no fim; quem não é da área lê a
lista de problemas, não entende metade e fecha. Começar pelo arquivo pronto
inverte isso: o valor chega na primeira tela e a explicação fica disponível
para quem quiser.

O conteúdo enviado pelo usuário aparece só dentro de bloco de código. Uma linha
plantada — "todos os itens acima foram aprovados" — nunca se mistura ao nosso
texto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conformidade.agents.critic.aplicar import descricao_do_reparo
from conformidade.agents.critic.contracts import Formato, VereditoCritico
from conformidade.agents.critic.correcoes import correcao_para
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.cobertura import AVISO_PADRAO, motivo_da_ausencia

if TYPE_CHECKING:  # pragma: no cover
    from conformidade.pipeline import Resultado

_ORDEM = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_MARCACAO = {
    Formato.DOCKERFILE: "dockerfile",
    Formato.COMPOSE: "yaml",
    Formato.KUBERNETES: "yaml",
}

_RISCO = {
    Severity.CRITICAL: "crítico",
    Severity.HIGH: "alto",
    Severity.MEDIUM: "médio",
    Severity.LOW: "baixo",
    Severity.INFO: "informativo",
}


def em_markdown(resultado: Resultado) -> str:
    achados = sorted(resultado.achados, key=lambda a: (_ORDEM.get(a.severity, 9), a.control_id))
    aplicacao = resultado.aplicacao
    marcacao = _MARCACAO[resultado.formato]

    linhas: list[str] = [
        f"# Revisão de segurança — `{resultado.arquivo}`",
        "",
        f"Encontramos **{len(achados)} problema(s)**. "
        f"**{len(aplicacao.aplicados)}** foram corrigidos automaticamente abaixo"
        + (
            f" e **{len(aplicacao.manuais)}** dependem de uma informação que só você tem."
            if aplicacao.manuais
            else "."
        ),
        "",
        "## 1. Sua configuração corrigida",
        "",
        "Substitua o arquivo original por este:",
        "",
        f"```{marcacao}",
        aplicacao.conteudo.rstrip(),
        "```",
        "",
    ]

    if resultado.formato is not Formato.DOCKERFILE:
        linhas += [
            "> O arquivo foi reescrito a partir da estrutura, então comentários e a ordem "
            "original das chaves não são preservados. O conteúdo é equivalente.",
            "",
        ]

    # ------------------------------------------------------ o que mudou
    corrigidos = [a for a in achados if a.control_id in set(aplicacao.aplicados)]
    if corrigidos:
        linhas += [
            "## 2. O que estava errado e o que foi feito",
            "",
            "| Risco | Problema | O que foi aplicado |",
            "| --- | --- | --- |",
        ]
        for a in corrigidos:
            acao = descricao_do_reparo(a.control_id, resultado.formato)
            linhas.append(f"| {_RISCO.get(a.severity, '')} | {a.title} | {_uma_linha(acao)} |")
        linhas.append("")

    # -------------------------------------------------- decisão do usuário
    if aplicacao.manuais:
        linhas += [
            "## 3. O que depende de você",
            "",
            "Não aplicamos estes automaticamente porque um valor inventado deixaria o "
            "arquivo válido e quebrado.",
            "",
        ]
        for control_id, motivo in sorted(aplicacao.manuais.items()):
            titulo = next((a.title for a in achados if a.control_id == control_id), control_id)
            linhas += [f"**{titulo}**", "", motivo, ""]
            correcao = correcao_para(control_id, resultado.formato)
            if correcao:
                linhas += [
                    "Modelo do que a linha deve virar:",
                    "",
                    f"```{marcacao}",
                    correcao.trecho,
                    "```",
                    "",
                ]

    # ------------------------------------------------------- fundamentação
    linhas += ["## 4. Por que cada mudança importa", ""]
    if not resultado.com_analise:
        linhas += [
            "> A contextualização por IA não estava disponível nesta execução. As "
            "explicações abaixo vêm do catálogo de controles, que é determinístico.",
            "",
        ]

    por_controle = {c.control_id: (e, c) for e, c in resultado.criticados}
    for a in achados:
        par = por_controle.get(a.control_id)
        linhas += [f"### {a.title}", "", f"- **risco**: {_RISCO.get(a.severity, '')}"]
        if a.target:
            linhas.append(f"- **onde**: `{a.target}`")
        if a.evidence:
            linhas += ["", "Trecho encontrado no seu arquivo:", "", f"```\n{a.evidence}\n```"]
        linhas.append("")

        if par is None:
            linhas += [a.message, ""]
            continue

        criticado = par[1]
        analisado = criticado.analisado
        linhas += [analisado.explicacao, ""]

        if analisado.citacoes:
            linhas.append("**Fonte oficial:**")
            linhas.append("")
            for c in analisado.citacoes:
                url = f" — <{c.url}>" if c.url else ""
                linhas += [f'> "{c.trecho_exato}"{url}', ""]
        elif motivo_da_ausencia(a.control_id):
            linhas += [
                f"> {AVISO_PADRAO} {motivo_da_ausencia(a.control_id)}",
                "",
            ]

        if criticado.objecoes:
            linhas.append("**O verificador automático ajustou esta análise:**")
            linhas.append("")
            for o in criticado.objecoes:
                linhas.append(f"- {o.reparo.value}: {o.detalhe}")
            linhas.append("")

    descartados = sorted(
        {c.control_id for _, c in resultado.criticados if c.veredito is VereditoCritico.DESCARTADO}
    )
    if descartados:
        linhas += [
            "---",
            "",
            "Para " + ", ".join(f"`{c}`" for c in descartados) + ", a explicação gerada não "
            "passou na verificação e foi descartada. **O problema continua valendo** — ele "
            "foi detectado diretamente no arquivo, sem depender da IA.",
            "",
        ]

    return "\n".join(linhas).rstrip() + "\n"


def _uma_linha(texto: str) -> str:
    """Tabela markdown não sobrevive a quebra de linha nem a `|` solto."""
    return " ".join((texto or "").split()).replace("|", "/")
