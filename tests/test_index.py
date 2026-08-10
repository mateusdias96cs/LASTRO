"""Testes do índice e da recuperação híbrida (Fase 3).

Todos usam `FakeProvider`: vetores determinísticos derivados de hash, sem
semântica. Isso é proposital — aqui se testa a mecânica (ordenação, fusão,
agrupamento, determinismo), não a qualidade semântica. Qualidade se mede com o
gabarito, contra o modelo real, fora da suíte unitária.
"""

import numpy as np
import pytest

from conformidade.agents.retrieval.contracts import Chunk
from conformidade.agents.retrieval.embeddings import FakeProvider, normalizar
from conformidade.agents.retrieval.index import DenseIndex, HybridRetriever, LexicalIndex
from conformidade.agents.retrieval.index.build import indexar_chunks, indexar_consultas
from conformidade.agents.retrieval.queries import CONSULTAS


def _chunk(pid: str, i: int, texto: str) -> Chunk:
    return Chunk(
        chunk_id=f"{pid}#{i:04d}-x",
        page_id=pid,
        url=f"https://exemplo/{pid}",
        fonte="docker",
        licenca="Apache-2.0",
        camada=1,
        doc_versao="v1",
        heading_path="H",
        texto=texto,
        content_sha256=str(i),
    )


@pytest.fixture
def chunks() -> list[Chunk]:
    return [
        _chunk("p:socket", 0, "mounting the docker.sock inside a container is dangerous"),
        _chunk("p:socket", 1, "the daemon socket grants root equivalent access to the host"),
        _chunk("p:rede", 2, "publishing ports and configuring networks for services"),
        _chunk("p:probe", 3, "liveness and readiness probe configuration reference"),
        _chunk("p:caps", 4, "cap_drop ALL then add only the required capability"),
    ]


# ------------------------------------------------------------- embeddings


def test_fake_provider_e_deterministico():
    p = FakeProvider()
    a = p.embed(["texto um", "texto dois"])
    b = p.embed(["texto um", "texto dois"])
    assert np.array_equal(a, b)


def test_vetores_saem_normalizados():
    p = FakeProvider()
    normas = np.linalg.norm(p.embed(["a", "b", "c"]), axis=1)
    assert np.allclose(normas, 1.0, atol=1e-6)


def test_normalizar_nao_divide_por_zero():
    assert not np.isnan(normalizar(np.zeros((1, 4), dtype=np.float32))).any()


def test_embed_de_lista_vazia():
    assert FakeProvider().embed([]).shape[0] == 0


# ------------------------------------------------------------ índice denso


def test_dense_index_rejeita_tamanhos_incompativeis(chunks):
    with pytest.raises(ValueError, match="não batem"):
        DenseIndex(chunks, np.zeros((2, 8), dtype=np.float32))


def test_dense_index_ordena_por_similaridade(chunks):
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    # A consulta é o texto exato de um chunk: ele tem que vir em primeiro.
    alvo = idx.chunks[2]
    vetor = p.embed([alvo.texto])[0]
    assert idx.pontuar(vetor)[0][0] == 2


def test_dense_index_alinha_chunks_e_vetores(chunks):
    """O construtor reordena chunks e vetores com a mesma chave; se o
    alinhamento quebrar, a busca devolve o texto de outro chunk."""
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    for i, chunk in enumerate(idx.chunks):
        vetor = p.embed([chunk.texto])[0]
        assert idx.pontuar(vetor)[0][0] == i


def test_dense_index_vazio_nao_estoura():
    idx = DenseIndex([], np.zeros((0, 8), dtype=np.float32))
    assert idx.pontuar(np.zeros(8, dtype=np.float32)) == []


def test_roundtrip_do_indice(chunks, tmp_path):
    p = FakeProvider()
    original = DenseIndex(chunks, indexar_chunks(chunks, p))
    destino = tmp_path / "v.npy"
    original.salvar(destino)
    assert np.array_equal(DenseIndex.carregar(chunks, destino).vetores, original.vetores)


# ------------------------------------------------------------ consultas


def test_indexar_consultas_cobre_o_catalogo():
    vetores = indexar_consultas(FakeProvider())
    assert set(vetores) == set(CONSULTAS)


# ------------------------------------------------------------- híbrido


def test_hibrido_exige_ao_menos_um_indice(chunks):
    with pytest.raises(ValueError, match="ao menos um índice"):
        HybridRetriever(chunks)


def test_modo_so_lexical(chunks):
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks))
    res = r.buscar("X", "docker.sock container", k=3)
    assert res.trechos[0].chunk.page_id == "p:socket"
    assert res.trechos[0].origem_do_score == "lexical"


def test_modo_so_denso(chunks):
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    alvo = idx.chunks[0]
    r = HybridRetriever(chunks, denso=idx, vetores_de_consulta={"X": p.embed([alvo.texto])[0]})
    res = r.buscar("X", "irrelevante para o denso", k=3)
    assert res.trechos[0].chunk.chunk_id == alvo.chunk_id
    assert res.trechos[0].origem_do_score == "denso"


def test_fusao_marca_a_origem_como_rrf(chunks):
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    r = HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=idx,
        vetores_de_consulta={"X": p.embed(["docker socket"])[0]},
    )
    assert r.buscar("X", "docker.sock", k=3).trechos[0].origem_do_score == "rrf"


def test_rrf_soma_as_duas_listas(chunks):
    """Documento bem colocado nos dois rankers tem que superar quem só aparece
    em um — é a razão de existir da fusão."""
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    alvo = next(c for c in idx.chunks if "docker.sock" in c.texto)
    r = HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=idx,
        vetores_de_consulta={"X": p.embed([alvo.texto])[0]},
        agrupar_por_pagina=False,
    )
    res = r.buscar("X", "docker.sock inside container", k=5)
    assert res.trechos[0].chunk.chunk_id == alvo.chunk_id


def test_agrupamento_por_pagina_evita_monopolio(chunks):
    """Sem agrupar, os dois chunks de `p:socket` tomariam duas vagas e
    esconderiam outras fontes."""
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks), agrupar_por_pagina=True)
    paginas = [t.chunk.page_id for t in r.buscar("X", "socket daemon container", k=5).trechos]
    assert len(paginas) == len(set(paginas))


def test_sem_agrupar_permite_varios_chunks_da_mesma_pagina(chunks):
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks), agrupar_por_pagina=False)
    paginas = [t.chunk.page_id for t in r.buscar("X", "socket daemon container", k=5).trechos]
    assert paginas.count("p:socket") >= 2


def test_hibrido_e_deterministico(chunks):
    p = FakeProvider()
    idx = DenseIndex(chunks, indexar_chunks(chunks, p))
    r = HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=idx,
        vetores_de_consulta={"X": p.embed(["socket"])[0]},
    )
    a = [t.chunk.chunk_id for t in r.buscar("X", "container socket", k=5).trechos]
    b = [t.chunk.chunk_id for t in r.buscar("X", "container socket", k=5).trechos]
    assert a == b


def test_consulta_sem_vetor_nao_derruba_a_busca(chunks):
    """Controle sem vetor pré-computado degrada para lexical em vez de falhar."""
    p = FakeProvider()
    r = HybridRetriever(
        chunks,
        lexical=LexicalIndex(chunks),
        denso=DenseIndex(chunks, indexar_chunks(chunks, p)),
        vetores_de_consulta={},
    )
    res = r.buscar("CONTROLE-SEM-VETOR", "docker.sock", k=3)
    assert res.trechos and res.trechos[0].origem_do_score == "lexical"


def test_nada_casa_devolve_vazio(chunks):
    """RAG que sempre devolve algo faz o agente de análise alucinar."""
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks))
    assert r.buscar("X", "zzzz termo inexistente qqqq", k=5).trechos == []


def test_proveniencia_preservada(chunks):
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks))
    chunk = r.buscar("X", "docker.sock", k=1).trechos[0].chunk
    assert chunk.url and chunk.licenca and chunk.doc_versao and chunk.texto
