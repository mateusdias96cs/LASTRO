"""Testes da camada de avaliação.

A avaliação é o instrumento de medida do projeto. Se ela estiver errada, todo
número que ela produzir vai enganar em vez de informar — por isso ela também
precisa de teste.
"""

import pytest

from conformidade.agents.deterministic import list_controls
from conformidade.agents.retrieval.queries import CONSULTAS, consulta_de
from conformidade.evals.baseline import BaselineLexical, RetrieverFixo, RetrieverPerfeito, tokenizar
from conformidade.evals.golden import carregar_gabarito, carregar_paginas_do_manifesto, validar
from conformidade.evals.harness import rodar
from conformidade.evals.metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    violou_distratores,
)

CONTROLES = {c.control_id for c in list_controls()}


# ------------------------------------------------------------- consultas


def test_todo_controle_tem_consulta():
    faltando = CONTROLES - set(CONSULTAS)
    assert not faltando, f"controles sem consulta em inglês: {sorted(faltando)}"


def test_nenhuma_consulta_orfa():
    orfas = set(CONSULTAS) - CONTROLES
    assert not orfas, f"consultas sem controle correspondente: {sorted(orfas)}"


def test_consultas_sao_em_ingles_e_substanciais():
    """Consulta curta demais não carrega nem o termo exato nem o conceito."""
    for control_id, consulta in CONSULTAS.items():
        assert len(consulta.split()) >= 8, f"{control_id}: consulta curta demais"
        assert consulta == consulta.strip()


def test_consulta_de_falha_alto_para_controle_desconhecido():
    with pytest.raises(KeyError, match="sem consulta"):
        consulta_de("CONF-NAO-EXISTE")


# -------------------------------------------------------------- gabarito


def test_gabarito_integro():
    """Impede que catálogo, manifesto e gabarito saiam de sincronia."""
    problemas = validar(carregar_gabarito(), CONTROLES)
    assert problemas == [], "\n".join(problemas)


def test_gabarito_cobre_os_36_controles():
    assert len(carregar_gabarito().casos) == len(CONTROLES) == 36


def test_todo_controle_tem_ao_menos_uma_pagina_de_alta_relevancia():
    gabarito = carregar_gabarito()
    sem_alta = [
        cid
        for cid, caso in gabarito.casos.items()
        if not caso.alta and not caso.sem_cobertura_oficial
    ]
    assert sem_alta == []


def test_manifesto_sem_pagina_orfa():
    """Página no corpus que nenhum controle usa é só distrator."""
    gabarito = carregar_gabarito()
    usadas = {p for caso in gabarito.casos.values() for p in caso.relevantes}
    orfas = carregar_paginas_do_manifesto() - usadas
    assert orfas == set(), f"páginas no manifesto que nenhum controle referencia: {sorted(orfas)}"


# --------------------------------------------------------------- métricas


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c"], {"a", "d"}, 3) == 0.5
    assert recall_at_k(["a", "b"], {"a", "b"}, 2) == 1.0
    assert recall_at_k(["x"], {"a"}, 1) == 0.0
    # Fora da janela não conta.
    assert recall_at_k(["x", "y", "a"], {"a"}, 2) == 0.0


def test_recall_sem_relevantes_nao_penaliza():
    assert recall_at_k(["x"], set(), 5) == 1.0


def test_precision_at_k():
    assert precision_at_k(["a", "x", "b", "y"], {"a", "b"}, 4) == 0.5
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["a", "b"], {"a"}) == 1.0
    assert reciprocal_rank(["x", "a"], {"a"}) == 0.5
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_ndcg_premia_o_relevante_no_topo():
    ganhos = {"alta": 3.0, "apoio": 1.0}
    bom = ndcg_at_k(["alta", "apoio"], ganhos, 10)
    ruim = ndcg_at_k(["apoio", "alta"], ganhos, 10)
    assert bom == 1.0
    assert ruim < bom


def test_ndcg_ordem_ideal_da_um():
    ganhos = {"a": 3.0, "b": 3.0, "c": 1.0}
    assert ndcg_at_k(["a", "b", "c"], ganhos, 10) == pytest.approx(1.0)


def test_distratores_so_contam_dentro_da_janela():
    assert violou_distratores(["a", "ruim"], {"ruim"}, 5) == ["ruim"]
    assert violou_distratores(["a", "b", "c", "d", "e", "ruim"], {"ruim"}, 5) == []


# ---------------------------------------------------------------- harness


def test_retriever_perfeito_atinge_o_teto():
    """Se o retriever devolve exatamente o gabarito e a métrica não dá 1.0,
    o bug é da métrica — não da recuperação."""
    gabarito = carregar_gabarito()
    perfeito = RetrieverPerfeito(
        {cid: caso.alta + caso.apoio for cid, caso in gabarito.casos.items()}
    )
    rel = rodar(perfeito, gabarito)
    assert rel.recall_at_10 == 1.0
    assert rel.mrr == 1.0
    assert rel.controles_com_distrator == 0
    assert rel.aprovado


def test_retriever_fixo_reprova():
    """Piso: devolver sempre as mesmas páginas não pode passar nos limiares."""
    gabarito = carregar_gabarito()
    rel = rodar(RetrieverFixo(["k8s:rbac", "k8s:namespaces"]), gabarito)
    assert not rel.aprovado
    assert rel.recall_at_10 < 0.5


def test_harness_deduplica_paginas_preservando_ordem():
    gabarito = carregar_gabarito()
    caso = gabarito.casos["CONF-WLD-001"]
    repetido = RetrieverPerfeito({"CONF-WLD-001": caso.alta + caso.alta})
    rel = rodar(repetido, gabarito)
    resultado = next(r for r in rel.por_controle if r.control_id == "CONF-WLD-001")
    assert len(resultado.paginas_recuperadas) == len(set(resultado.paginas_recuperadas))


# --------------------------------------------------------------- baseline


def test_tokenizador_preserva_identificadores_do_dominio():
    """Quebrar `docker.sock` em dois tokens destruiria justamente o termo raro
    que a busca lexical deveria acertar."""
    assert "docker.sock" in tokenizar("mounting /var/run/docker.sock inside")
    assert "no-new-privileges" in tokenizar("use no-new-privileges flag")
    assert "allowprivilegeescalation" in tokenizar("allowPrivilegeEscalation: false")


def test_baseline_encontra_pagina_pelo_termo_exato():
    paginas = {
        "p:socket": "mounting the docker.sock into a container is dangerous",
        "p:rede": "publishing ports and network configuration for services",
        "p:probe": "liveness and readiness probes configuration",
    }
    baseline = BaselineLexical(paginas)
    r = baseline.buscar("X", "docker.sock container escape", k=3)
    assert r.trechos[0].chunk.page_id == "p:socket"


def test_baseline_e_deterministico():
    paginas = {f"p:{i}": "termo comum repetido" for i in range(5)}
    baseline = BaselineLexical(paginas)
    a = [t.chunk.page_id for t in baseline.buscar("X", "termo comum", k=5).trechos]
    b = [t.chunk.page_id for t in baseline.buscar("X", "termo comum", k=5).trechos]
    assert a == b


def test_baseline_devolve_vazio_quando_nada_casa():
    """Não inventar resultado é requisito: RAG que sempre devolve algo faz o
    agente de análise alucinar."""
    baseline = BaselineLexical({"p:a": "conteudo sobre volumes"})
    assert baseline.buscar("X", "xyzabc inexistente", k=5).trechos == []
