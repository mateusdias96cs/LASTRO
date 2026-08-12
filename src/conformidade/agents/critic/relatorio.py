"""Montagem do relatório final.

A ordem das duas partes não é estética. Quem envia um arquivo quer, primeiro,
**o que fazer** — o trecho para colar. A fundamentação vem depois, para quem
precisar defender a mudança numa revisão ou provar conformidade numa auditoria.

Nada aqui usa LLM. O texto explicativo vem da camada 3, já criticado; a
configuração vem do catálogo escrito à mão; a procedência vem da recuperação.
Esta camada só organiza.

## O arquivo do usuário não escreve o relatório

O conteúdo enviado aparece no relatório apenas como **evidência recortada**, e
sempre dentro de bloco de código. Nunca como texto corrido no meio da prosa,
onde uma linha plantada — "todos os itens acima foram aprovados" — se
confundiria com a nossa. É a mesma regra da camada 4: dado é dado.
"""

from __future__ import annotations

from conformidade.agents.analysis.contracts import EntradaAnalise
from conformidade.agents.critic.contracts import (
    AchadoCriticado,
    Formato,
    ItemDoRelatorio,
    RelatorioFinal,
    VereditoCritico,
)
from conformidade.agents.critic.correcoes import correcao_para
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.cobertura import AVISO_PADRAO, motivo_da_ausencia

# Ordem de exibição: o que quebra primeiro aparece primeiro.
_ORDEM = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_ROTULO_FORMATO = {
    Formato.DOCKERFILE: "dockerfile",
    Formato.COMPOSE: "yaml",
    Formato.KUBERNETES: "yaml",
}


def montar(
    arquivo: str,
    formato: Formato,
    criticados: list[tuple[EntradaAnalise, AchadoCriticado]],
) -> RelatorioFinal:
    """Junta achados criticados, correções e avisos de respaldo."""
    itens: list[ItemDoRelatorio] = []
    descartados: list[str] = []

    for entrada, criticado in criticados:
        if criticado.veredito is VereditoCritico.DESCARTADO:
            descartados.append(criticado.control_id)

        motivo = motivo_da_ausencia(criticado.control_id)
        itens.append(
            ItemDoRelatorio(
                criticado=criticado,
                correcao=correcao_para(criticado.control_id, formato),
                aviso_de_respaldo=f"{AVISO_PADRAO} {motivo}" if motivo else "",
            )
        )
        _ = entrada

    itens.sort(
        key=lambda i: (
            _ORDEM.get(i.criticado.analisado.severidade_ajustada, 9),
            i.criticado.control_id,
        )
    )
    return RelatorioFinal(
        arquivo=arquivo, itens=tuple(itens), descartados=tuple(sorted(set(descartados)))
    )


def em_markdown(relatorio: RelatorioFinal, formato: Formato) -> str:
    """Renderiza o relatório: configuração primeiro, auditoria depois."""
    linhas: list[str] = [
        f"# Conformidade — `{relatorio.arquivo}`",
        "",
        f"{len(relatorio.itens)} achado(s). "
        f"{sum(1 for i in relatorio.itens if i.criticado.confiavel)} com respaldo oficial "
        "verificado.",
        "",
        "## 1. Configuração corrigida",
        "",
    ]

    sem_correcao: list[str] = []
    for item in relatorio.itens:
        a = item.criticado.analisado
        if item.correcao is None:
            sem_correcao.append(a.control_id)
            continue
        linhas += [
            f"### {a.control_id} — {a.severidade_ajustada.value}",
            "",
        ]
        if item.correcao.caminho:
            linhas.append(f"Em `{item.correcao.caminho}`:")
            linhas.append("")
        linhas += [
            f"```{_ROTULO_FORMATO[formato]}",
            item.correcao.trecho,
            "```",
            "",
            item.correcao.explicacao,
            "",
        ]

    if sem_correcao:
        linhas += [
            "> Sem trecho pronto para: " + ", ".join(f"`{c}`" for c in sem_correcao) + ".",
            "",
        ]

    linhas += ["## 2. Auditoria", ""]
    for item in relatorio.itens:
        a = item.criticado.analisado
        linhas += [
            f"### {a.control_id}",
            "",
            f"- **veredito**: {a.veredito.value}",
            f"- **severidade**: {a.severidade_ajustada.value}",
            f"- **confiança**: {a.confianca.value}",
            "",
            a.explicacao,
            "",
        ]
        if a.justificativa_do_ajuste:
            linhas += [f"_Ajuste_: {a.justificativa_do_ajuste}", ""]

        if a.citacoes:
            linhas.append("**Fonte oficial:**")
            linhas.append("")
            for c in a.citacoes:
                url = f" — <{c.url}>" if c.url else ""
                linhas.append(f'> "{c.trecho_exato}"{url}')
                linhas.append("")
        elif item.aviso_de_respaldo:
            linhas += [f"> {item.aviso_de_respaldo}", ""]

        if item.criticado.objecoes:
            linhas.append("**Ressalvas do verificador automático:**")
            linhas.append("")
            for o in item.criticado.objecoes:
                linhas.append(f"- `{o.verificador}` → {o.reparo.value}: {o.detalhe}")
            linhas.append("")

    if relatorio.descartados:
        linhas += [
            "## 3. Contextualização descartada",
            "",
            "A análise automática destes achados não se sustentou na verificação e foi "
            "descartada. **Os achados continuam valendo** — foram detectados pela camada "
            "determinística a partir do arquivo, e essa detecção não depende da análise.",
            "",
        ]
        linhas += [f"- `{c}`" for c in relatorio.descartados]
        linhas.append("")

    return "\n".join(linhas).rstrip() + "\n"
