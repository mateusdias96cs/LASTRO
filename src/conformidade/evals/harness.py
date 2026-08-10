"""Executor da avaliação de recuperação.

Mede qualquer coisa que satisfaça o protocolo `Retriever` — do baseline lexical
ao híbrido final — com o mesmo código. Assim, comparar duas abordagens é trocar
um argumento, não reescrever a medição.

O harness converte trechos em **páginas** antes de medir, porque o gabarito é
declarado no nível de página (ver `golden.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from conformidade.agents.retrieval.contracts import Retriever
from conformidade.agents.retrieval.queries import consulta_de
from conformidade.evals.golden import CasoGabarito, Gabarito
from conformidade.evals.metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    violou_distratores,
)


class ResultadoControle(BaseModel):
    control_id: str
    paginas_recuperadas: list[str] = Field(default_factory=list)
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    distratores_no_top_5: list[str] = Field(default_factory=list)
    faltando: list[str] = Field(default_factory=list)


class RelatorioEval(BaseModel):
    total_controles: int = 0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    controles_com_distrator: int = 0
    por_controle: list[ResultadoControle] = Field(default_factory=list)
    violacoes_de_limiar: list[str] = Field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.violacoes_de_limiar


def _paginas_ordenadas(page_ids: Sequence[str]) -> list[str]:
    """Deduplica preservando a ordem: duas passagens da mesma página contam
    como uma só recuperação daquela página."""
    vistas: set[str] = set()
    saida: list[str] = []
    for pid in page_ids:
        if pid not in vistas:
            vistas.add(pid)
            saida.append(pid)
    return saida


def avaliar_controle(retriever: Retriever, caso: CasoGabarito, k: int = 10) -> ResultadoControle:
    resultado = retriever.buscar(caso.control_id, consulta_de(caso.control_id), k=k)
    paginas = _paginas_ordenadas([t.chunk.page_id for t in resultado.trechos])

    relevantes = caso.relevantes
    return ResultadoControle(
        control_id=caso.control_id,
        paginas_recuperadas=paginas,
        recall_at_5=recall_at_k(paginas, relevantes, 5),
        recall_at_10=recall_at_k(paginas, relevantes, 10),
        precision_at_5=precision_at_k(paginas, relevantes, 5),
        mrr=reciprocal_rank(paginas, relevantes),
        ndcg_at_10=ndcg_at_k(paginas, caso.ganhos, 10),
        distratores_no_top_5=violou_distratores(paginas, set(caso.nao_deve), 5),
        faltando=sorted(set(caso.alta) - set(paginas[:k])),
    )


def _media(valores: list[float]) -> float:
    return round(sum(valores) / len(valores), 4) if valores else 0.0


def rodar(retriever: Retriever, gabarito: Gabarito, k: int = 10) -> RelatorioEval:
    resultados = [
        avaliar_controle(retriever, caso, k=k)
        for _, caso in sorted(gabarito.casos.items())
        if not caso.sem_cobertura_oficial
    ]

    relatorio = RelatorioEval(
        total_controles=len(resultados),
        recall_at_5=_media([r.recall_at_5 for r in resultados]),
        recall_at_10=_media([r.recall_at_10 for r in resultados]),
        precision_at_5=_media([r.precision_at_5 for r in resultados]),
        mrr=_media([r.mrr for r in resultados]),
        ndcg_at_10=_media([r.ndcg_at_10 for r in resultados]),
        controles_com_distrator=len([r for r in resultados if r.distratores_no_top_5]),
        por_controle=resultados,
    )

    limiares = gabarito.limiares
    for nome in ("recall_at_5", "recall_at_10", "mrr", "ndcg_at_10"):
        minimo = limiares.get(nome)
        obtido = getattr(relatorio, nome)
        if minimo is not None and obtido < minimo:
            relatorio.violacoes_de_limiar.append(f"{nome}={obtido:.3f} abaixo do mínimo {minimo}")

    teto_distratores = limiares.get("distratores_no_top_5")
    if teto_distratores is not None and relatorio.controles_com_distrator > teto_distratores:
        culpados = [r.control_id for r in resultados if r.distratores_no_top_5]
        relatorio.violacoes_de_limiar.append(
            f"{relatorio.controles_com_distrator} controle(s) com distrator no top-5 "
            f"(máximo {int(teto_distratores)}): {culpados}"
        )

    return relatorio


def formatar(relatorio: RelatorioEval) -> str:
    linhas = [
        f"controles avaliados : {relatorio.total_controles}",
        f"recall@5            : {relatorio.recall_at_5:.3f}",
        f"recall@10           : {relatorio.recall_at_10:.3f}",
        f"precision@5         : {relatorio.precision_at_5:.3f}",
        f"MRR                 : {relatorio.mrr:.3f}",
        f"nDCG@10             : {relatorio.ndcg_at_10:.3f}",
        f"com distrator top-5 : {relatorio.controles_com_distrator}",
        "",
        "APROVADO" if relatorio.aprovado else "REPROVADO:",
    ]
    linhas.extend(f"  - {v}" for v in relatorio.violacoes_de_limiar)
    return "\n".join(linhas)
