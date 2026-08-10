"""Testes dos documentos canônicos dos controles.

São o conteúdo autoritativo do produto: o texto que vai para o relatório do
usuário e para o prompt do agente de análise. Erro aqui não é bug de código, é
informação errada entregue como se fosse verificada — por isso as invariantes
são de integridade e completude, não de formatação.
"""

import pytest

from conformidade.agents.deterministic import list_controls
from conformidade.agents.retrieval.controls import (
    SECOES_OBRIGATORIAS,
    carregar_todos,
    documento_de,
    parsear,
    validar,
)
from conformidade.agents.retrieval.index import HybridRetriever, LexicalIndex
from conformidade.agents.retrieval.queries import CONSULTAS

CONTROLES = {c.control_id for c in list_controls()}
DOCUMENTOS = carregar_todos()


# ---------------------------------------------------------- completude


def test_todo_controle_tem_documento():
    faltando = CONTROLES - set(DOCUMENTOS)
    assert not faltando, f"controles sem documento canônico: {sorted(faltando)}"


def test_nenhum_documento_orfao():
    orfaos = set(DOCUMENTOS) - CONTROLES
    assert not orfaos, f"documentos sem controle no catálogo: {sorted(orfaos)}"


def test_catalogo_documentos_e_consultas_batem():
    """As três listas descrevem o mesmo conjunto; divergência entre elas é
    exatamente o tipo de drift que passa despercebido."""
    assert CONTROLES == set(DOCUMENTOS)
    assert CONTROLES == set(CONSULTAS)


def test_validacao_sem_problemas():
    assert validar(CONTROLES) == []


# ------------------------------------------------------------ conteúdo


@pytest.mark.parametrize("control_id", sorted(CONTROLES))
def test_documento_tem_as_secoes_obrigatorias(control_id):
    doc = DOCUMENTOS[control_id]
    assert doc.afirmacao and doc.por_que_importa and doc.como_corrigir


@pytest.mark.parametrize("control_id", sorted(CONTROLES))
def test_metadados_vem_do_catalogo(control_id):
    """Título e severidade não são duplicados no arquivo — vêm da camada 1,
    para não divergirem em silêncio."""
    doc = DOCUMENTOS[control_id]
    assert doc.titulo
    assert doc.severidade in ("critical", "high", "medium", "low", "info")


def test_documentos_sao_em_portugues():
    """O relatório vai para o usuário em português; o corpus é que é inglês."""
    marcadores = ("não", "container", "deve", "que")
    for control_id, doc in DOCUMENTOS.items():
        texto = doc.texto.lower()
        assert any(m in texto for m in marcadores), control_id


def test_documento_traz_exemplo_de_correcao():
    """`Como corrigir` sem exemplo concreto vira conselho vago."""
    sem_exemplo = [
        cid
        for cid, doc in DOCUMENTOS.items()
        if "`" not in doc.como_corrigir and "```" not in doc.como_corrigir
    ]
    assert sem_exemplo == [], f"correção sem trecho concreto: {sem_exemplo}"


def test_pares_confundiveis_sao_desambiguados():
    """Os 5 distratores que a busca não resolve precisam estar tratados no
    texto — é essa a razão de a âncora existir."""
    esperado = {
        "CONF-WLD-008": "volume",  # raiz somente-leitura × volume :ro
        "CONF-K8S-003": "Secret",  # token de service account × Secret comum
        "CONF-K8S-005": "hostNetwork",  # hostPort × hostNetwork
        "CONF-SEC-001": "_FILE",  # segredo em runtime × build
        "CONF-K8S-002": "AppArmor",  # seccomp × AppArmor
    }
    for control_id, termo in esperado.items():
        doc = DOCUMENTOS[control_id]
        assert termo.lower() in doc.texto.lower(), f"{control_id} não desambigua `{termo}`"


# -------------------------------------------------------------- parser


def test_parser_rejeita_secao_obrigatoria_ausente():
    with pytest.raises(ValueError, match="seções obrigatórias"):
        parsear("X", "## Afirmação normativa\n\ntexto\n")


def test_parser_rejeita_secao_vazia():
    conteudo = "## Afirmação normativa\n\na\n\n## Por que importa\n\n\n## Como corrigir\n\nc\n"
    with pytest.raises(ValueError, match="seções obrigatórias"):
        parsear("X", conteudo)


def test_secao_de_excecao_e_opcional():
    conteudo = "\n".join(f"## {s}\n\nconteudo da secao\n" for s in SECOES_OBRIGATORIAS)
    assert parsear("X", conteudo).quando_nao_se_aplica == ""


def test_texto_remonta_o_documento():
    doc = documento_de("CONF-WLD-002")
    assert doc is not None
    assert doc.afirmacao in doc.texto
    assert doc.como_corrigir in doc.texto


# --------------------------------------------------- integração com a busca


def test_recuperacao_sempre_traz_a_ancora():
    """Mesmo sem nenhum trecho recuperado, o documento canônico vem — é a
    garantia de que o agente de análise nunca fica sem base."""
    from conformidade.agents.retrieval.contracts import Chunk

    chunks = [
        Chunk(
            chunk_id="p:a#0000-x",
            page_id="p:a",
            url="u",
            fonte="docker",
            licenca="Apache-2.0",
            camada=1,
            doc_versao="v",
            heading_path="H",
            texto="conteudo sem relacao nenhuma com a consulta",
            content_sha256="0",
        )
    ]
    r = HybridRetriever(chunks, lexical=LexicalIndex(chunks))
    res = r.buscar("CONF-WLD-002", "zzz termo inexistente qqq", k=5)
    assert res.trechos == []
    assert res.documento_canonico is not None
    assert res.documento_canonico.control_id == "CONF-WLD-002"
    assert "socket" in res.documento_canonico.afirmacao.lower()
