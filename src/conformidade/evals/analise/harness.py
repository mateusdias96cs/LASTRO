"""Executor da avaliação da camada 3.

Mede qualquer coisa que satisfaça o protocolo `Analisador` — o agente com LLM,
um duplo de teste, ou duas versões de prompt lado a lado.

A recuperação é a de verdade: os casos com `recuperacao: real` chamam o
retriever híbrido, então a avaliação exercita a integração completa entre as
camadas 2 e 3, não um mock do corpus.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from conformidade.agents.analysis.contracts import Analisador, EntradaAnalise
from conformidade.agents.retrieval.contracts import ResultadoRecuperacao
from conformidade.agents.retrieval.queries import consulta_de
from conformidade.evals.analise import verificadores as v
from conformidade.evals.analise.casos import Caso, Conjunto

RAIZ = Path(__file__).resolve().parents[4]
CHUNKS = RAIZ / "corpus" / "chunks.jsonl"
INDICE = RAIZ / "corpus" / "index"


class ResultadoCaso(BaseModel):
    id: str
    nivel: int
    passou: bool
    falhas: list[str] = Field(default_factory=list)
    citacoes_nao_literais: int = 0
    erro: str = ""


class RelatorioAnalise(BaseModel):
    total: int = 0
    aprovados: int = 0
    por_nivel: dict[int, str] = Field(default_factory=dict)
    taxa_por_nivel: dict[int, float] = Field(default_factory=dict)
    citacoes_nao_literais: int = 0
    resultados: list[ResultadoCaso] = Field(default_factory=list)
    violacoes: list[str] = Field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.violacoes


def _retriever_real():
    from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
    from conformidade.agents.retrieval.index.build import (
        carregar_consultas,
        carregar_indice_denso,
        ler_meta,
    )
    from conformidade.agents.retrieval.ingest import carregar_chunks

    chunks = carregar_chunks(CHUNKS)
    return HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=carregar_indice_denso(chunks, INDICE),
        vetores_de_consulta=carregar_consultas(INDICE),
        corpus_versao=ler_meta(INDICE).get("corpus_versao", ""),
    )


def montar_entrada(caso: Caso, retriever=None) -> EntradaAnalise:
    if caso.recuperacao == "vazia":
        recuperacao = ResultadoRecuperacao(
            control_id=caso.achado["control_id"], consulta="", trechos=[]
        )
    else:
        control_id = caso.achado["control_id"]
        recuperacao = retriever.buscar(control_id, consulta_de(control_id), k=6)
    return caso.para_entrada(recuperacao)


def avaliar_caso(analisador: Analisador, caso: Caso, retriever=None) -> ResultadoCaso:
    entrada = montar_entrada(caso, retriever)
    try:
        saida = analisador.analisar(entrada)
    except Exception as exc:  # noqa: BLE001 - um caso quebrado não derruba a suíte
        return ResultadoCaso(
            id=caso.id, nivel=caso.nivel, passou=False, erro=f"{type(exc).__name__}: {exc}"
        )

    e = caso.esperado
    falhas: list[v.Falha] = []
    falhas += v.nao_inventa_achado(entrada, saida)
    falhas += v.citacoes_sao_literais(entrada, saida)
    falhas += v.exige_citacao(entrada, saida, e.exige_citacao)
    falhas += v.nao_cita_distrator(entrada, saida, e.nao_citar_paginas)
    falhas += v.veredito_esperado(saida, e.veredito)
    falhas += v.severidade_na_faixa(saida, e.severidade_minima, e.severidade_maxima)
    falhas += v.ajuste_justificado(entrada, saida)
    falhas += v.responde_em_portugues(saida)
    falhas += v.contem_termos(saida, e.deve_mencionar, e.nao_deve_mencionar)
    falhas += v.explicacao_substancial(saida)

    if e.citacoes_maximas is not None and len(saida.citacoes) > e.citacoes_maximas:
        falhas.append(
            v.Falha(
                "citacoes_demais",
                f"{len(saida.citacoes)} citações, máximo {e.citacoes_maximas}",
            )
        )

    nao_literais = len(
        [
            f
            for f in falhas
            if f.verificador in ("citacao_nao_literal", "citacao_de_fonte_inexistente")
        ]
    )
    return ResultadoCaso(
        id=caso.id,
        nivel=caso.nivel,
        passou=not falhas,
        falhas=[f"{f.verificador}: {f.detalhe}" for f in falhas],
        citacoes_nao_literais=nao_literais,
    )


def rodar(analisador: Analisador, conjunto: Conjunto) -> RelatorioAnalise:
    precisa_de_retriever = any(c.recuperacao == "real" for c in conjunto.casos)
    retriever = _retriever_real() if precisa_de_retriever else None

    resultados = [avaliar_caso(analisador, caso, retriever) for caso in conjunto.casos]
    relatorio = RelatorioAnalise(
        total=len(resultados),
        aprovados=len([r for r in resultados if r.passou]),
        citacoes_nao_literais=sum(r.citacoes_nao_literais for r in resultados),
        resultados=resultados,
    )

    for nivel, casos in conjunto.por_nivel().items():
        do_nivel = [r for r in resultados if r.nivel == nivel]
        ok = len([r for r in do_nivel if r.passou])
        taxa = ok / len(do_nivel) if do_nivel else 1.0
        relatorio.por_nivel[nivel] = f"{ok}/{len(do_nivel)}"
        relatorio.taxa_por_nivel[nivel] = round(taxa, 4)

        minimo = conjunto.taxa_minima_por_nivel.get(nivel)
        if minimo is not None and taxa < minimo:
            reprovados = [r.id for r in do_nivel if not r.passou]
            relatorio.violacoes.append(
                f"nível {nivel}: {taxa:.0%} abaixo do mínimo {minimo:.0%} — {reprovados}"
            )
        _ = casos

    if relatorio.citacoes_nao_literais > conjunto.citacoes_nao_literais_maximas:
        relatorio.violacoes.append(
            f"{relatorio.citacoes_nao_literais} citação(ões) inventada(s) — "
            f"máximo {conjunto.citacoes_nao_literais_maximas}. É a falha mais grave "
            "desta camada: soa convincente e não tem fonte."
        )

    return relatorio


def formatar(relatorio: RelatorioAnalise) -> str:
    linhas = [
        f"casos            : {relatorio.aprovados}/{relatorio.total}",
        f"citações falsas  : {relatorio.citacoes_nao_literais}",
        "",
        "por nível:",
    ]
    rotulos = {
        1: "direto",
        2: "exceção aplica",
        3: "contexto agrava",
        4: "não verificável",
        5: "par confundível",
        6: "adversarial",
    }
    for nivel, contagem in relatorio.por_nivel.items():
        taxa = relatorio.taxa_por_nivel[nivel]
        linhas.append(f"  {nivel} {rotulos.get(nivel, ''):17} {contagem:>7}  {taxa:.0%}")

    reprovados = [r for r in relatorio.resultados if not r.passou]
    if reprovados:
        linhas.append("")
        linhas.append("casos reprovados:")
        for r in reprovados:
            linhas.append(f"  {r.id}")
            for f in r.falhas[:3]:
                linhas.append(f"      {f}")
            if r.erro:
                linhas.append(f"      erro: {r.erro}")

    linhas.append("")
    linhas.append("APROVADO" if relatorio.aprovado else "REPROVADO:")
    linhas.extend(f"  - {x}" for x in relatorio.violacoes)
    return "\n".join(linhas)
