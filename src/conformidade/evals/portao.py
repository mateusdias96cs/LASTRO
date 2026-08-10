"""Portão de qualidade.

Reúne as verificações que reprovam uma mudança. Mora no pacote, e não só em
`scripts/`, para que o mesmo código rode local e no pipeline — "passou na minha
máquina" e "passou no CI" precisam significar a mesma coisa.

Três famílias de verificação, em ordem de custo:

1. **integridade** — corpus e índice consistentes entre si;
2. **limiar** — a recuperação atinge o mínimo aceitável;
3. **regressão** — nenhuma métrica caiu além da tolerância em relação à
   linha de base registrada.

A terceira é a que costuma faltar. Sem ela, uma queda de recall de 0,907 para
0,86 passa despercebida enquanto estiver acima do limiar — e o sistema piora
aos poucos sem nunca disparar alarme.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
from conformidade.agents.retrieval.index.build import (
    carregar_consultas,
    carregar_indice_denso,
    ler_meta,
)
from conformidade.agents.retrieval.ingest import carregar_chunks
from conformidade.agents.retrieval.ingest.pipeline import versao_do_corpus
from conformidade.evals.golden import carregar_gabarito
from conformidade.evals.harness import RelatorioEval, rodar

# Quanto uma métrica pode piorar antes de ser considerada regressão. Pequeno de
# propósito: a recuperação é determinística, então variação genuína só vem de
# mudança de corpus, de índice ou de código.
TOLERANCIA = 0.01

METRICAS = ("recall_at_5", "recall_at_10", "precision_at_5", "mrr", "ndcg_at_10")


@dataclass
class Verificacao:
    nome: str
    passou: bool
    detalhe: str = ""
    # Verificação informativa aparece no relatório mas não reprova o build.
    bloqueante: bool = True


@dataclass
class ResultadoPortao:
    """Separa o que bloqueia do que informa.

    A distinção não é cosmética. As metas do gabarito (zero distratores, em
    particular) são o alvo, não o estado atual — hoje faltam 5. Se elas
    bloqueassem, o portão ficaria vermelho desde o primeiro dia, e portão
    permanentemente vermelho é portão que a equipe aprende a ignorar. Pior que
    não ter.

    O que bloqueia é o que já está sob controle: integridade do corpus e
    **não piorar**. A meta continua visível em toda execução, com a distância
    até ela explícita, e a checagem de regressão impede que essa distância
    aumente em silêncio.
    """

    verificacoes: list[Verificacao] = field(default_factory=list)
    metricas: dict[str, float] = field(default_factory=dict)

    @property
    def aprovado(self) -> bool:
        return all(v.passou for v in self.verificacoes if v.bloqueante)

    @property
    def metas_nao_atingidas(self) -> list[Verificacao]:
        return [v for v in self.verificacoes if not v.passou and not v.bloqueante]

    def adicionar(
        self, nome: str, passou: bool, detalhe: str = "", bloqueante: bool = True
    ) -> None:
        self.verificacoes.append(Verificacao(nome, passou, detalhe, bloqueante))


def verificar_integridade(chunks_path: Path, indice_path: Path) -> list[Verificacao]:
    """Corpus e índice precisam descrever o mesmo conteúdo.

    O caso que isso pega: alguém reingere o corpus e esquece de reindexar. O
    índice continua respondendo, com vetores de um conteúdo que não existe
    mais — sem erro nenhum, só resultado errado.
    """
    saida: list[Verificacao] = []

    if not chunks_path.exists():
        return [Verificacao("corpus presente", False, f"{chunks_path} não existe")]
    saida.append(Verificacao("corpus presente", True, str(chunks_path)))

    chunks = carregar_chunks(chunks_path)
    saida.append(Verificacao("corpus não vazio", len(chunks) > 0, f"{len(chunks)} chunks"))

    meta = ler_meta(indice_path)
    if not meta:
        saida.append(Verificacao("índice presente", False, f"{indice_path} sem metadados"))
        return saida
    saida.append(Verificacao("índice presente", True, meta.get("modelo", "?")))

    versao_atual = versao_do_corpus(sorted(chunks, key=lambda c: (c.page_id, c.chunk_id)))
    versao_indice = meta.get("corpus_versao", "")
    saida.append(
        Verificacao(
            "índice atualizado",
            versao_atual == versao_indice,
            f"corpus={versao_atual} índice={versao_indice}"
            + ("" if versao_atual == versao_indice else " — rode scripts/indexar.py"),
        )
    )

    saida.append(
        Verificacao(
            "índice cobre todos os chunks",
            meta.get("total_chunks") == len(chunks),
            f"índice={meta.get('total_chunks')} corpus={len(chunks)}",
        )
    )
    return saida


def construir_retriever(chunks_path: Path, indice_path: Path) -> HybridRetriever:
    chunks = carregar_chunks(chunks_path)
    return HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=carregar_indice_denso(chunks, indice_path),
        vetores_de_consulta=carregar_consultas(indice_path),
        corpus_versao=ler_meta(indice_path).get("corpus_versao", ""),
    )


def verificar_regressao(
    atual: RelatorioEval, baseline: dict, tolerancia: float = TOLERANCIA
) -> list[Verificacao]:
    saida: list[Verificacao] = []
    for metrica in METRICAS:
        anterior = baseline.get(metrica)
        if anterior is None:
            continue
        valor = getattr(atual, metrica)
        queda = anterior - valor
        saida.append(
            Verificacao(
                f"sem regressão em {metrica}",
                queda <= tolerancia,
                f"{valor:.3f} (linha de base {anterior:.3f}, "
                f"{'−' if queda > 0 else '+'}{abs(queda):.3f})",
            )
        )

    anterior_distr = baseline.get("controles_com_distrator")
    if anterior_distr is not None:
        saida.append(
            Verificacao(
                "sem novos distratores",
                atual.controles_com_distrator <= anterior_distr,
                f"{atual.controles_com_distrator} (linha de base {anterior_distr})",
            )
        )
    return saida


def executar(
    chunks_path: Path,
    indice_path: Path,
    baseline_path: Path,
    checar_limiares: bool = True,
) -> ResultadoPortao:
    resultado = ResultadoPortao()

    for v in verificar_integridade(chunks_path, indice_path):
        resultado.verificacoes.append(v)
    if not resultado.aprovado:
        return resultado  # sem corpus íntegro, medir não faz sentido

    relatorio = rodar(construir_retriever(chunks_path, indice_path), carregar_gabarito())
    resultado.metricas = {m: getattr(relatorio, m) for m in METRICAS}
    resultado.metricas["controles_com_distrator"] = relatorio.controles_com_distrator

    if checar_limiares:
        # Informativo: é a meta, não o piso. Ver docstring de ResultadoPortao.
        for violacao in relatorio.violacoes_de_limiar:
            resultado.adicionar("meta do gabarito", False, violacao, bloqueante=False)
        if not relatorio.violacoes_de_limiar:
            resultado.adicionar("meta do gabarito", True, "todas atingidas")

    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        resultado.verificacoes.extend(verificar_regressao(relatorio, baseline))
    else:
        resultado.adicionar("linha de base presente", False, f"{baseline_path} não existe")

    return resultado


def gravar_baseline(destino: Path, metricas: dict[str, float]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(metricas, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def formatar(resultado: ResultadoPortao) -> str:
    linhas = []
    for v in resultado.verificacoes:
        if v.passou:
            marca = "ok   "
        elif v.bloqueante:
            marca = "FALHA"
        else:
            marca = "meta "
        linhas.append(f"  [{marca}] {v.nome:30} {v.detalhe}")

    pendentes = resultado.metas_nao_atingidas
    if pendentes:
        linhas.append("")
        linhas.append(f"  {len(pendentes)} meta(s) ainda não atingida(s) — não bloqueia,")
        linhas.append("  mas a checagem de regressão impede que a distância aumente.")

    return "\n".join(linhas)
