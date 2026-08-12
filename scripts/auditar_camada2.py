#!/usr/bin/env python3
"""Auditoria da camada 2 — o que o portão de qualidade não consegue ver.

    python scripts/auditar_camada2.py [--json saida.json]

Motivação: o gabarito da camada 2 é declarado no nível de **página**. Foi uma
decisão deliberada e boa (mudar o chunking não invalida o gabarito), mas ela
tem um preço que só apareceu quando a camada 3 entrou em operação: um controle
pode marcar `faltando: []` com recall@10 = 0,80 e mesmo assim não ter **um
único trecho citável** no que é entregue ao analisador. Página certa, chunk
inútil. Nenhuma métrica de página enxerga isso.

Esta auditoria mede no nível de chunk. Três decisões de método sustentam ela:

* **os termos vêm de artefato pré-existente.** A sonda pergunta "o top-k contém
  um chunk que carrega um identificador normativo deste controle?". Os
  identificadores são extraídos da seção `Afirmação normativa` dos documentos
  canônicos — texto escrito antes desta auditoria existir, com outra
  finalidade. Inventar a lista agora seria escolher, sem perceber, termos que
  passam;

* **o corte de relevância é derivado, não escolhido.** Um termo só conta como
  evidência se um top-k **aleatório** o contivesse por acaso em menos de 5% das
  vezes. Isso descarta `run` (presente em 30,6% dos chunks) sem que eu precise
  julgar termo a termo;

* **presença e visibilidade são medidas separadamente.** A presença no corpus
  usa casamento de substring no texto cru; a visibilidade ao BM25 usa o
  tokenizador do índice. A diferença entre as duas não é detalhe: é onde mora
  o defeito de `hostPort`, que existe no corpus e é invisível ao índice.

A auditoria **não conserta nada** e não ajusta parâmetro. Diagnóstico e reparo
em passos separados — do contrário não dá para distinguir "o número melhorou"
de "eu movi o alvo".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import numpy as np  # noqa: E402

from conformidade.agents.retrieval.contracts import Chunk  # noqa: E402
from conformidade.agents.retrieval.controls import (  # noqa: E402
    DIRETORIO as DIR_CONTROLES,
)
from conformidade.agents.retrieval.controls import documento_de  # noqa: E402
from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex  # noqa: E402
from conformidade.agents.retrieval.index.build import (  # noqa: E402
    carregar_consultas,
    carregar_indice_denso,
    ler_meta,
)
from conformidade.agents.retrieval.index.lexical import tokenizar  # noqa: E402
from conformidade.agents.retrieval.ingest import carregar_chunks  # noqa: E402
from conformidade.agents.retrieval.ingest.chunker import estimar_tokens  # noqa: E402
from conformidade.agents.retrieval.queries import consulta_de  # noqa: E402
from conformidade.evals.golden import (  # noqa: E402
    carregar_gabarito,
    carregar_paginas_do_manifesto,
)

# `k` que a camada 3 realmente recebe. O gabarito mede em 10; o analisador vê 6.
# Auditar no 6 é auditar o que é entregue, não o que é medido.
K_ENTREGUE = 6
K_GABARITO = 10

# Limite de tokens por chunk usado na ingestão; aqui só verificamos o estouro.
LIMITE_TOKENS = 480

CHANCE_MAXIMA = 0.05

_CRASE = re.compile(r"`([^`\n]+)`")
# Quebra também no ponto: `securityContext.privileged` vira dois candidatos.
# O texto oficial escreve o campo aninhado em YAML, não na forma pontuada.
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

# Frase que PRESCREVE, não apenas descreve. É o que separa uma norma de uma
# menção — e o que permite usar todas as grafias de um campo sem falso
# positivo. `read_only` aparece na tabela de volumes do Compose ("Flag to set
# the volume as read-only") e no CIS 5.13 ("should be treated as a golden
# image by using Docker run's --read-only option"). A segunda prescreve; a
# primeira descreve outro campo com o mesmo nome.
_MODAL = re.compile(
    r"\b(must not|must|should not|should|never|do not|don't|avoid|"
    r"disallow(?:ed)?|forbidden|required|recommend(?:ed)?|prohibited)\b",
    re.I,
)
_FRASE = re.compile(r"(?<=[.!?])\s+")


_SEPARADOR = re.compile(r"[_\-]")


def _grafia(texto: str) -> str:
    """Normaliza `_` e `-`, que separam palavras no mesmo nome de campo.

    O mesmo controle se escreve `read_only` no Compose e `--read-only` na CLI
    da Docker, e o CIS Benchmark usa a segunda forma. Casar substring exata
    tratava as duas como campos diferentes, e um trecho oficial que enuncia a
    norma não era contado como portador.
    """
    return _SEPARADOR.sub("", texto.lower())


def _enuncia_norma(texto: str, termos: set[str]) -> bool:
    """Alguma frase nomeia o campo E prescreve algo sobre ele?"""
    termos = {_grafia(t) for t in termos}
    baixo = _grafia(texto)
    if not any(t in baixo for t in termos):
        return False
    return any(
        any(t in _grafia(f) for t in termos) and _MODAL.search(f) for f in _FRASE.split(texto)
    )


# ---------------------------------------------------------------- estruturas


@dataclass
class Termo:
    termo: str
    df_texto: int  # em quantos chunks aparece como substring (verdade do corpus)
    df_token: int  # em quantos chunks o BM25 o enxerga como token

    @property
    def invisivel_ao_bm25(self) -> bool:
        return self.df_texto > 0 and self.df_token == 0


@dataclass
class Achado:
    control_id: str
    auditavel: bool
    motivo_nao_auditavel: str = ""
    termos: list[Termo] = field(default_factory=list)
    chunks_portadores: int = 0
    melhor_rank: int | None = None  # posição do 1º chunk portador no híbrido
    rank_bm25: int | None = None
    rank_denso: int | None = None
    # Só preenchido quando o agrupamento por página removeu o portador.
    rank_sem_agrupamento: int | None = None
    no_top_entregue: bool = False
    no_top_gabarito: bool = False
    gabarito_diz_coberto: bool = False
    classe: str = ""


def _chance_de_acaso(df: int, n: int, k: int) -> float:
    if df <= 0 or n - df < k:
        return 1.0
    return 1.0 - comb(n - df, k) / comb(n, k)


def _corte_de_df(n: int, k: int) -> int:
    """Maior df cuja chance de acerto acidental ainda fica abaixo do teto."""
    return max((f for f in range(1, n) if _chance_de_acaso(f, n, k) <= CHANCE_MAXIMA), default=0)


def _identificadores(control_id: str) -> set[str]:
    doc = documento_de(control_id)
    if doc is None:
        return set()
    return {
        ident.lower()
        for trecho in _CRASE.findall(doc.afirmacao)
        for ident in _IDENT.findall(trecho)
    }


# ------------------------------------------------------------------- passos


def passo_1_cobertura(chunks: list[Chunk], control_ids: list[str], corte: int) -> dict[str, Achado]:
    """O texto normativo existe no corpus? Substring no texto cru, sem
    tokenizador — presença é verdade do corpus, não do índice."""
    textos = [_grafia(c.texto) for c in chunks]
    df_token: Counter[str] = Counter()
    for c in chunks:
        df_token.update(set(tokenizar(c.texto)))

    achados: dict[str, Achado] = {}
    for cid in control_ids:
        candidatos = _identificadores(cid)
        viaveis = []
        for t in sorted(candidatos):
            df_texto = sum(1 for x in textos if _grafia(t) in x)
            if 0 < df_texto <= corte:
                viaveis.append(Termo(t, df_texto, df_token.get(t, 0)))

        # TODAS as grafias discriminativas, não só a de menor df.
        #
        # A versão anterior mantinha apenas o termo de menor frequência, para
        # fugir do falso positivo do `read_only` de volume do Compose. Isso
        # tornou a sonda cega a vocabulário: o mesmo campo se chama
        # `readOnlyRootFilesystem` no Kubernetes, `read_only` no Compose e
        # `--read-only` na CLI, e o CIS Docker Benchmark usa a terceira forma.
        # Um trecho oficial que enuncia a norma perfeitamente não era contado.
        #
        # O falso positivo agora é barrado por `_enuncia_norma`, que exige
        # modal prescritivo na mesma frase — critério que mede o que a sonda
        # sempre quis medir (o documento **enuncia a norma**?) em vez de
        # grafia. Ver `passo_2_recuperabilidade`.
        termos = viaveis

        if termos:
            achados[cid] = Achado(cid, auditavel=True, termos=termos)
        else:
            ausentes = sorted(t for t in candidatos if not any(_grafia(t) in x for x in textos))
            motivo = (
                f"identificadores ausentes do corpus: {ausentes}"
                if ausentes
                else (
                    "nenhum identificador discriminativo — os termos normativos "
                    f"deste controle são palavras comuns ({sorted(candidatos)})"
                    if candidatos
                    else "a afirmação normativa não cita identificador entre crases"
                )
            )
            achados[cid] = Achado(cid, auditavel=False, motivo_nao_auditavel=motivo)
    return achados


def passo_2_recuperabilidade(
    achados: dict[str, Achado],
    chunks: list[Chunk],
    retriever: HybridRetriever,
    lexical: LexicalIndex,
    denso,
    consultas: dict[str, np.ndarray],
    sem_agrupamento: HybridRetriever | None = None,
) -> None:
    """A busca traz um chunk portador do termo dentro do k entregue?

    Também registra a posição em cada índice isolado — é o passo 6 embutido,
    e só faz sentido calcular para quem falhou, mas custa um produto
    matriz-vetor: barato o bastante para medir sempre e evitar um segundo
    percurso que poderia divergir.

    O mesmo percurso sem agrupamento por página separa duas falhas que parecem
    idênticas na saída e têm consertos opostos. `agrupar_por_pagina` mantém um
    chunk por página: quando um vizinho da mesma página ganha a vaga, o chunk
    portador não é rebaixado, é **removido do resultado inteiro**. Reportar
    isso como "a busca nunca traz" mandaria consertar o ranking, quando o que
    precisa mudar é a política de diversidade.
    """
    for cid, achado in achados.items():
        if not achado.auditavel:
            continue
        alvo = {t.termo for t in achado.termos}
        portadores = {c.chunk_id for c in chunks if _enuncia_norma(c.texto, alvo)}
        achado.chunks_portadores = len(portadores)

        consulta = consulta_de(cid)
        ordenados = [
            t.chunk.chunk_id for t in retriever.buscar(cid, consulta, k=len(chunks)).trechos
        ]
        achado.melhor_rank = next((i for i, c in enumerate(ordenados, 1) if c in portadores), None)

        if achado.melhor_rank is None and sem_agrupamento is not None:
            crus = [
                t.chunk.chunk_id
                for t in sem_agrupamento.buscar(cid, consulta, k=len(chunks)).trechos
            ]
            achado.rank_sem_agrupamento = next(
                (i for i, c in enumerate(crus, 1) if c in portadores), None
            )
        achado.no_top_entregue = bool(achado.melhor_rank and achado.melhor_rank <= K_ENTREGUE)
        achado.no_top_gabarito = bool(achado.melhor_rank and achado.melhor_rank <= K_GABARITO)

        bm = [lexical.chunks[i].chunk_id for i, _ in lexical.pontuar(consulta)]
        achado.rank_bm25 = next((i for i, c in enumerate(bm, 1) if c in portadores), None)
        vetor = consultas.get(cid)
        if vetor is not None:
            dn = [denso.chunks[i].chunk_id for i, _ in denso.pontuar(vetor)]
            achado.rank_denso = next((i for i, c in enumerate(dn, 1) if c in portadores), None)


def passo_3_cegueira_do_gabarito(achados: dict[str, Achado]) -> None:
    """O gabarito diz coberto enquanto não há trecho citável entregue?"""
    gabarito = carregar_gabarito()
    for cid, achado in achados.items():
        caso = gabarito.caso(cid)
        if caso is None:
            continue
        # "Coberto" aqui é a leitura otimista do gabarito: nenhuma página de
        # alta relevância ficou faltando.
        achado.gabarito_diz_coberto = bool(caso.alta)
        if not achado.auditavel:
            achado.classe = "nao_auditavel"
        elif achado.no_top_entregue:
            achado.classe = "ok"
        elif achado.melhor_rank is None:
            achado.classe = (
                "apagado_pelo_agrupamento"
                if achado.rank_sem_agrupamento is not None
                else "busca_nunca_traz"
            )
        else:
            achado.classe = "fora_do_k_entregue"


def passo_4_saude(chunks: list[Chunk], denso, retriever: HybridRetriever) -> list[str]:
    """Quebra silenciosa. Cada checagem aqui existe porque a classe de bug já
    aconteceu neste índice ou porque falharia sem levantar exceção."""
    problemas: list[str] = []

    ids = Counter(c.chunk_id for c in chunks)
    if dup := [i for i, n in ids.items() if n > 1]:
        problemas.append(f"chunk_id duplicado: {dup[:5]}")

    shas = Counter(c.content_sha256 for c in chunks)
    if dup := [s for s, n in shas.items() if n > 1]:
        problemas.append(f"{len(dup)} conteúdo(s) duplicado(s) com sha256 repetido")

    if vazios := [c.chunk_id for c in chunks if not c.texto.strip()]:
        problemas.append(f"chunk vazio: {vazios[:5]}")

    # Usa o estimador da própria ingestão. Reimplementá-lo aqui gerou 16
    # falsos alarmes na primeira execução, por diferença de arredondamento —
    # um teste que mede coisa diferente da que o sistema faz não é teste.
    grandes = [c.chunk_id for c in chunks if estimar_tokens(c.texto) > LIMITE_TOKENS]
    if grandes:
        problemas.append(f"{len(grandes)} chunk(s) acima de {LIMITE_TOKENS} tokens estimados")

    do_manifesto = carregar_paginas_do_manifesto()
    orfaos = sorted({c.page_id for c in chunks} - do_manifesto)
    if orfaos:
        problemas.append(f"page_id fora do manifesto: {orfaos[:5]}")

    # Alinhamento vetor↔chunk. A permutação dupla de `indexar_chunks` pareava
    # cada texto com o vetor de outro chunk sem levantar erro nenhum; o próprio
    # vetor de um chunk tem de recuperá-lo em primeiro lugar.
    if denso is not None and denso.vetores.size:
        passo = max(1, len(denso.chunks) // 40)
        desalinhados = [
            denso.chunks[i].chunk_id
            for i in range(0, len(denso.chunks), passo)
            if denso.pontuar(denso.vetores[i])[0][0] != i
        ]
        if desalinhados:
            problemas.append(f"vetor não recupera o próprio chunk: {desalinhados[:5]}")

    # Determinismo: a identidade do projeto. Mesma entrada, mesma saída.
    a = retriever.buscar("CONF-WLD-001", consulta_de("CONF-WLD-001"), k=10)
    b = retriever.buscar("CONF-WLD-001", consulta_de("CONF-WLD-001"), k=10)
    if a.model_dump_json() != b.model_dump_json():
        problemas.append("busca não é determinística entre duas chamadas idênticas")

    return problemas


def passo_5_distratores(retriever: HybridRetriever) -> list[str]:
    """Onde o distrator declarado cai em relação à fonte verdadeira."""
    gabarito = carregar_gabarito()
    linhas: list[str] = []
    for cid, caso in sorted(gabarito.casos.items()):
        if not caso.nao_deve:
            continue
        trechos = retriever.buscar(cid, consulta_de(cid), k=K_ENTREGUE).trechos
        paginas = [t.chunk.page_id for t in trechos]
        pos_distrator = next((i for i, p in enumerate(paginas, 1) if p in set(caso.nao_deve)), None)
        pos_alta = next((i for i, p in enumerate(paginas, 1) if p in set(caso.alta)), None)
        if pos_distrator is None:
            continue
        veredito = (
            "ACIMA da fonte" if pos_alta is None or pos_distrator < pos_alta else "abaixo da fonte"
        )
        linhas.append(
            f"{cid:<14} distrator na posição {pos_distrator}, "
            f"fonte de alta relevância em {pos_alta or '—'}  → {veredito}"
        )
    return linhas


# -------------------------------------------------------------------- saída


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=RAIZ / "corpus" / "chunks.jsonl")
    parser.add_argument("--indice", type=Path, default=RAIZ / "corpus" / "index")
    parser.add_argument("--json", type=Path, help="grava o resultado estruturado")
    args = parser.parse_args()

    chunks = carregar_chunks(args.chunks)
    lexical = LexicalIndex(chunks)
    denso = carregar_indice_denso(chunks, args.indice)
    consultas = carregar_consultas(args.indice)
    meta = ler_meta(args.indice)
    retriever = HybridRetriever(
        chunks,
        lexical=lexical,
        denso=denso,
        vetores_de_consulta=consultas,
        corpus_versao=meta.get("corpus_versao", ""),
    )
    control_ids = sorted(p.stem for p in DIR_CONTROLES.glob("*.md"))
    corte = _corte_de_df(len(chunks), K_ENTREGUE)

    print("=" * 72)
    print("AUDITORIA DA CAMADA 2 — nível de chunk")
    print("=" * 72)
    print("\n[0] linha de base")
    print(f"    chunks              {len(chunks)}")
    print(f"    controles           {len(control_ids)}")
    print(f"    corpus_versao       {meta.get('corpus_versao', '—')}")
    print(f"    modelo denso        {meta.get('modelo', '—')}")
    print(f"    k entregue à camada 3   {K_ENTREGUE}   (gabarito mede em {K_GABARITO})")
    print(
        f"    corte de df         <= {corte} chunks "
        f"(chance de acaso {_chance_de_acaso(corte, len(chunks), K_ENTREGUE):.1%})"
    )

    achados = passo_1_cobertura(chunks, control_ids, corte)
    auditaveis = [a for a in achados.values() if a.auditavel]
    print("\n[1] cobertura do corpus")
    print(f"    auditáveis por esta sonda   {len(auditaveis)}/{len(control_ids)}")
    for a in sorted(achados.values(), key=lambda x: x.control_id):
        if not a.auditavel:
            print(f"      - {a.control_id}: {a.motivo_nao_auditavel}")

    invisiveis = [(a.control_id, t) for a in auditaveis for t in a.termos if t.invisivel_ao_bm25]
    print(f"\n    termos presentes no corpus e INVISÍVEIS ao BM25: {len(invisiveis)}")
    for cid, t in invisiveis:
        print(f"      - {cid:<14} `{t.termo}` em {t.df_texto} chunk(s), df de token = 0")

    sem_agrupamento = HybridRetriever(
        chunks,
        lexical=lexical,
        denso=denso,
        vetores_de_consulta=consultas,
        agrupar_por_pagina=False,
    )
    passo_2_recuperabilidade(achados, chunks, retriever, lexical, denso, consultas, sem_agrupamento)
    passo_3_cegueira_do_gabarito(achados)

    print(f"\n[2] recuperabilidade no k entregue (={K_ENTREGUE})")
    cab = f"    {'controle':<14} {'port.':>5} {'híbr':>5} {'BM25':>5} {'denso':>5}  situação"
    print(cab)
    print("    " + "-" * (len(cab) - 4))
    for a in sorted(auditaveis, key=lambda x: (x.classe != "ok", x.control_id)):
        marca = {
            "ok": "ok",
            "fora_do_k_entregue": "FORA DO K",
            "busca_nunca_traz": "AUSENTE",
            "apagado_pelo_agrupamento": f"APAGADO (seria {a.rank_sem_agrupamento}º)",
        }[a.classe]
        print(
            f"    {a.control_id:<14} {a.chunks_portadores:>5} "
            f"{str(a.melhor_rank or '—'):>5} {str(a.rank_bm25 or '—'):>5} "
            f"{str(a.rank_denso or '—'):>5}  {marca}"
        )

    falhos = [a for a in auditaveis if a.classe != "ok"]
    print("\n[3] cegueira do gabarito por página")
    cegos = [a for a in falhos if a.gabarito_diz_coberto]
    print(f"    controles sem trecho normativo no top-{K_ENTREGUE}: {len(falhos)}")
    print(f"    destes, o gabarito declara página de alta relevância: {len(cegos)}")
    for a in cegos:
        print(
            f"      - {a.control_id}: melhor portador na posição "
            f"{a.melhor_rank or 'nenhuma'}, fora do que a camada 3 recebe"
        )

    print("\n[4] saúde e quebra silenciosa")
    problemas = passo_4_saude(chunks, denso, retriever)
    if problemas:
        for p in problemas:
            print(f"      [!] {p}")
    else:
        print("      nenhum problema: sem duplicata, sem órfão, vetores alinhados,")
        print("      busca determinística entre chamadas idênticas")

    print(f"\n[5] estrutura dos distratores no top-{K_ENTREGUE}")
    linhas = passo_5_distratores(retriever)
    if linhas:
        for linha in linhas:
            print(f"      {linha}")
    else:
        print("      nenhum distrator declarado aparece no top-k")

    print("\n[6] diagnóstico de consulta — só os que falharam")
    for a in falhos:
        causa = (
            "termo invisível ao BM25"
            if any(t.invisivel_ao_bm25 for t in a.termos)
            else "diluição lexical"
            if (a.rank_bm25 or 10**6) > 20 and (a.rank_denso or 10**6) <= 20
            else "denso não reconhece o conceito"
            if (a.rank_denso or 10**6) > 20 and (a.rank_bm25 or 10**6) <= 20
            else "ambos os índices erram"
        )
        print(f"      {a.control_id:<14} {causa}")
        print(f"                     consulta: {consulta_de(a.control_id)}")

    print("\n" + "=" * 72)
    print("RESUMO")
    print("=" * 72)
    classes = Counter(a.classe for a in achados.values())
    for nome, rotulo in (
        ("ok", "trecho normativo entregue à camada 3"),
        ("fora_do_k_entregue", "existe no corpus, cai fora do k entregue"),
        ("apagado_pelo_agrupamento", "removido do resultado pelo agrupamento por página"),
        ("busca_nunca_traz", "existe no corpus, a busca nunca traz"),
        ("nao_auditavel", "sonda não se aplica (termos são palavras comuns)"),
    ):
        print(f"  {classes.get(nome, 0):>3}  {rotulo}")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "corpus_versao": meta.get("corpus_versao", ""),
                    "corte_df": corte,
                    "k_entregue": K_ENTREGUE,
                    "controles": {
                        cid: {
                            "classe": a.classe,
                            "auditavel": a.auditavel,
                            "motivo": a.motivo_nao_auditavel,
                            "termos": [
                                {"t": t.termo, "df_texto": t.df_texto, "df_token": t.df_token}
                                for t in a.termos
                            ],
                            "melhor_rank": a.melhor_rank,
                            "rank_bm25": a.rank_bm25,
                            "rank_denso": a.rank_denso,
                            "rank_sem_agrupamento": a.rank_sem_agrupamento,
                        }
                        for cid, a in sorted(achados.items())
                    },
                    "saude": problemas,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nresultado estruturado em {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
