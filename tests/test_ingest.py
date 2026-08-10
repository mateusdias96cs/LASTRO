"""Testes da ingestão (Fase 2)."""

from pathlib import Path

from conformidade.agents.retrieval.contracts import Chunk
from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
from conformidade.agents.retrieval.ingest import (
    estimar_tokens,
    extrair_html,
    fatiar,
    id_do_chunk,
    salvar_chunks,
    versao_do_corpus,
)
from conformidade.agents.retrieval.ingest.extract import Secao
from conformidade.agents.retrieval.ingest.store import carregar_chunks

HTML = """
<html><head><title>t</title><style>body{color:red}</style></head>
<body>
  <nav><a href="/x">Menu Serviços Volumes Redes</a></nav>
  <h1>Security</h1>
  <p>Intro sobre seguranca.</p>
  <h2>Pod Security Standards</h2>
  <p>O perfil restricted exige runAsNonRoot.</p>
  <h3>Restricted</h3>
  <p>allowPrivilegeEscalation deve ser false.</p>
  <h2>Outra secao</h2>
  <p>Conteudo diferente aqui.</p>
  <script>var x = "nao deve aparecer";</script>
  <footer>Rodape com termos repetidos</footer>
</body></html>
"""


# ------------------------------------------------------------- extração


def test_extrai_hierarquia_de_titulos():
    secoes = extrair_html(HTML)
    caminhos = [s.heading_path for s in secoes]
    assert "Security" in caminhos
    assert "Security > Pod Security Standards" in caminhos
    assert "Security > Pod Security Standards > Restricted" in caminhos


def test_h2_seguinte_desempilha_o_h3():
    """`Outra secao` é irmã de `Pod Security Standards`, não filha de `Restricted`."""
    secoes = extrair_html(HTML)
    caminhos = [s.heading_path for s in secoes]
    assert "Security > Outra secao" in caminhos


def test_ignora_navegacao_script_e_rodape():
    """Menu e rodapé repetem os mesmos termos em toda página de documentação e
    envenenariam a busca lexical."""
    texto = " ".join(s.texto for s in extrair_html(HTML))
    assert "nao deve aparecer" not in texto
    assert "Menu Serviços" not in texto
    assert "Rodape" not in texto
    assert "color:red" not in texto


def test_conteudo_do_documento_e_preservado():
    texto = " ".join(s.texto for s in extrair_html(HTML))
    assert "runAsNonRoot" in texto
    assert "allowPrivilegeEscalation deve ser false" in texto


def test_html_vazio_nao_estoura():
    assert extrair_html("") == []


# ----------------------------------------------------------- fatiamento


def _secao(texto: str, heading: str = "A > B") -> Secao:
    return Secao(heading_path=heading, nivel=2, ordem=0, texto=texto)


def test_nenhum_chunk_passa_do_limite():
    """A regressão que motivou a guarda final: a estimativa de tokens usa
    `max()` de duas fórmulas e não é aditiva, então somar estimativas por frase
    subestimava o total. Chunk acima do limite é truncado em silêncio pelo
    modelo — parece indexado e não está."""
    limite = 100
    for texto in (
        "palavra " * 900,
        "--uma-flag-de-cli-bem-longa=valor " * 300,  # chars/4 domina
        ". ".join(f"Frase numero {i} com algum conteudo" for i in range(200)),
    ):
        chunks = fatiar([_secao(texto)], limite=limite)
        assert chunks, "deveria produzir ao menos um chunk"
        excedentes = [c.tokens for c in chunks if c.tokens > limite]
        assert not excedentes, f"chunks acima do limite: {excedentes[:5]}"


def test_secao_pequena_vira_um_chunk_so():
    chunks = fatiar([_secao("Texto curto mas suficiente para passar do minimo exigido aqui.")])
    assert len(chunks) == 1


def test_heading_path_e_prefixado_ao_texto():
    """Um trecho recuperado isoladamente precisa carregar de onde veio."""
    chunks = fatiar([_secao("Conteudo relevante o bastante para virar um chunk valido.")])
    assert chunks[0].texto.startswith("A > B")


def test_secao_curta_demais_e_descartada():
    """Chunk de poucos tokens é legenda ou navegação, nunca evidência."""
    assert fatiar([_secao("oi")]) == []


def test_id_do_chunk_muda_com_o_conteudo_e_nao_com_a_posicao():
    a = id_do_chunk("p:x", "mesmo texto", 0)
    b = id_do_chunk("p:x", "mesmo texto", 0)
    c = id_do_chunk("p:x", "texto diferente", 0)
    assert a == b
    assert a != c
    assert a.startswith("p:x#0000-")


def test_estimativa_de_tokens_e_conservadora():
    """Para texto com identificadores longos, contar palavras subestima."""
    codigo = "--security-opt=no-new-privileges:true --cap-drop=ALL --read-only"
    assert estimar_tokens(codigo) >= len(codigo) // 4


# ------------------------------------------------------- armazenamento


def test_roundtrip_do_jsonl(tmp_path: Path):
    chunks = [
        Chunk(
            chunk_id="p:a#0000-abc",
            page_id="p:a",
            url="https://exemplo/x",
            fonte="docker",
            licenca="Apache-2.0",
            camada=1,
            doc_versao="sha256:aaa",
            heading_path="A > B",
            texto="conteudo com acento ç e emoji 🔒",
            content_sha256="deadbeef",
        )
    ]
    destino = tmp_path / "c.jsonl"
    assert salvar_chunks(chunks, destino) == 1
    assert carregar_chunks(destino) == chunks


def test_escrita_e_deterministica(tmp_path: Path):
    chunks = [
        Chunk(
            chunk_id=f"p:a#{i:04d}-x",
            page_id="p:a",
            url="u",
            fonte="docker",
            licenca="Apache-2.0",
            camada=1,
            doc_versao="v",
            heading_path="H",
            texto=f"texto {i}",
            content_sha256=f"{i}",
        )
        for i in range(5)
    ]
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    salvar_chunks(chunks, a)
    salvar_chunks(chunks, b)
    assert a.read_bytes() == b.read_bytes()


def test_versao_do_corpus_muda_com_o_conteudo():
    def chunk(texto: str, sha: str) -> Chunk:
        return Chunk(
            chunk_id="p:a#0000-x",
            page_id="p:a",
            url="u",
            fonte="docker",
            licenca="Apache-2.0",
            camada=1,
            doc_versao="v",
            heading_path="H",
            texto=texto,
            content_sha256=sha,
        )

    assert versao_do_corpus([chunk("a", "1")]) == versao_do_corpus([chunk("a", "1")])
    assert versao_do_corpus([chunk("a", "1")]) != versao_do_corpus([chunk("b", "2")])


# ----------------------------------------------------- retriever de chunk


def _chunks_de_teste() -> list[Chunk]:
    dados = [
        ("p:socket", "Mounting the docker.sock inside a container is dangerous"),
        ("p:socket", "Outro trecho da mesma pagina sobre daemon socket exposure"),
        ("p:rede", "Publishing ports and configuring the network for services"),
        ("p:probe", "Liveness and readiness probes configuration reference"),
    ]
    return [
        Chunk(
            chunk_id=f"{pid}#{i:04d}-x",
            page_id=pid,
            url="u",
            fonte="docker",
            licenca="Apache-2.0",
            camada=1,
            doc_versao="v",
            heading_path="H",
            texto=txt,
            content_sha256=str(i),
        )
        for i, (pid, txt) in enumerate(dados)
    ]


def _retriever(chunks, agrupar_por_pagina: bool = True) -> HybridRetriever:
    return HybridRetriever(
        chunks, lexical=LexicalIndex(chunks), agrupar_por_pagina=agrupar_por_pagina
    )


def test_retriever_de_chunk_encontra_pelo_termo_exato():
    r = _retriever(_chunks_de_teste())
    res = r.buscar("X", "docker.sock container escape", k=3)
    assert res.trechos[0].chunk.page_id == "p:socket"


def test_max_pooling_evita_uma_pagina_ocupar_tudo():
    """Sem agrupar, os dois trechos de `p:socket` tomariam duas das três vagas
    e esconderiam outras fontes."""
    r = _retriever(_chunks_de_teste(), agrupar_por_pagina=True)
    res = r.buscar("X", "socket daemon container", k=3)
    paginas = [t.chunk.page_id for t in res.trechos]
    assert len(paginas) == len(set(paginas))


def test_retriever_de_chunk_e_deterministico():
    r = _retriever(_chunks_de_teste())
    a = [t.chunk.chunk_id for t in r.buscar("X", "container network", k=4).trechos]
    b = [t.chunk.chunk_id for t in r.buscar("X", "container network", k=4).trechos]
    assert a == b


def test_retriever_de_chunk_preserva_proveniencia():
    """O agente crítico precisa verificar a citação contra a fonte."""
    r = _retriever(_chunks_de_teste())
    chunk = r.buscar("X", "docker.sock", k=1).trechos[0].chunk
    assert chunk.url and chunk.licenca and chunk.doc_versao and chunk.texto
