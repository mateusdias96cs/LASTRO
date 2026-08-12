"""Executor da avaliação da camada 4.

Mede qualquer coisa com a assinatura de `criticar` — o crítico real ou um
duplo. Mesma forma de `evals/analise/harness.py`: `rodar()` produz o relatório,
`formatar()` o imprime com a seção APROVADO/REPROVADO.

Diferença de escopo em relação à camada 3, e ela é deliberada: lá o limiar é
por nível, porque o agente é um LLM e uma taxa abaixo de 100% é esperada. Aqui
o crítico é determinístico, então **qualquer caso reprovado é defeito**, não
variação. O limiar é 100% e não há graduação.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from conformidade.agents.analysis.contracts import AchadoAnalisado, EntradaAnalise
from conformidade.agents.critic.contracts import AchadoCriticado
from conformidade.evals.critico.casos import CASOS, CasoCritico

Critico = Callable[[EntradaAnalise, AchadoAnalisado], AchadoCriticado]


class ResultadoCaso(BaseModel):
    id: str
    passou: bool
    falhas: list[str] = Field(default_factory=list)
    erro: str = ""


class RelatorioCritico(BaseModel):
    total: int = 0
    aprovados: int = 0
    resultados: list[ResultadoCaso] = Field(default_factory=list)
    violacoes: list[str] = Field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.violacoes

    @property
    def taxa(self) -> float:
        return self.aprovados / self.total if self.total else 1.0


def avaliar_caso(critico: Critico, caso: CasoCritico) -> ResultadoCaso:
    try:
        resultado = critico(caso.entrada, caso.saida)
    except Exception as exc:  # noqa: BLE001 - um duplo quebrado não derruba a suíte
        return ResultadoCaso(id=caso.id, passou=False, erro=f"{type(exc).__name__}: {exc}")

    falhas: list[str] = []

    if resultado.veredito is not caso.veredito_esperado:
        falhas.append(
            f"veredito_inesperado: respondeu `{resultado.veredito.value}`, "
            f"esperado `{caso.veredito_esperado.value}`"
        )

    emitidos = {o.verificador for o in resultado.objecoes}
    faltando = sorted(caso.verificadores_esperados - emitidos)
    if faltando:
        falhas.append(f"verificador_ausente: não acusou {faltando}")

    # Rebaixar pelo motivo errado é tão ruim quanto não rebaixar: o relatório
    # mostraria uma ressalva que não corresponde ao problema.
    if caso.veredito_esperado.value != "aprovado":
        inventados = sorted(e for e in emitidos if e.startswith("desconfianca"))
        if inventados:
            falhas.append(f"objecao_sem_lastro: acusou {inventados}, que não é falha real")

    if caso.sem_citacoes_ao_final and resultado.analisado.citacoes:
        falhas.append(
            f"citacao_mantida: {len(resultado.analisado.citacoes)} citação(ões) "
            "sobreviveram e deveriam ter sido removidas"
        )

    if resultado.control_id != caso.entrada.control_id:
        falhas.append(
            f"controle_alterado: devolveu `{resultado.control_id}` "
            f"em vez de `{caso.entrada.control_id}`"
        )

    return ResultadoCaso(id=caso.id, passou=not falhas, falhas=falhas)


def rodar(critico: Critico, casos: tuple[CasoCritico, ...] = CASOS) -> RelatorioCritico:
    resultados = [avaliar_caso(critico, caso) for caso in casos]
    relatorio = RelatorioCritico(
        total=len(resultados),
        aprovados=len([r for r in resultados if r.passou]),
        resultados=resultados,
    )
    if relatorio.aprovados != relatorio.total:
        reprovados = [r.id for r in resultados if not r.passou]
        relatorio.violacoes.append(
            f"{len(reprovados)} caso(s) reprovado(s) — {reprovados}. "
            "O crítico é determinístico: qualquer reprovação é defeito, não variação."
        )
    return relatorio


def formatar(relatorio: RelatorioCritico) -> str:
    linhas = [
        f"casos            : {relatorio.aprovados}/{relatorio.total}",
        f"taxa             : {relatorio.taxa:.0%}",
    ]
    reprovados = [r for r in relatorio.resultados if not r.passou]
    if reprovados:
        linhas += ["", "casos reprovados:"]
        for r in reprovados:
            linhas.append(f"  {r.id}")
            linhas += [f"      {f}" for f in r.falhas]
            if r.erro:
                linhas.append(f"      erro: {r.erro}")

    linhas += ["", "APROVADO" if relatorio.aprovado else "REPROVADO:"]
    linhas += [f"  - {v}" for v in relatorio.violacoes]
    return "\n".join(linhas)
