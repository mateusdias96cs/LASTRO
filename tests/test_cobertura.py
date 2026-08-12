"""Declaração de ausência de respaldo oficial.

A regra que estes testes protegem: quando a auditoria provou que nenhum trecho
oficial utilizável chega à camada de análise, o sistema **declara a ausência**
em vez de mandar o modelo escolher o vizinho mais parecido. Citação plausível e
deslocada empresta autoridade de terceiro a uma afirmação que aquele terceiro
não fez — a pior falha possível numa ferramenta de auditoria.
"""

import pytest
from test_azure_provider import _entrada

from conformidade.agents.analysis.azure_provider import prompt_usuario
from conformidade.agents.retrieval.cobertura import (
    SEM_RESPALDO_OFICIAL,
    motivo_da_ausencia,
    tem_respaldo_oficial,
)
from conformidade.agents.retrieval.controls import DIRETORIO, documento_de
from conformidade.agents.retrieval.queries import CONSULTAS


def test_todo_controle_sem_respaldo_existe_no_catalogo():
    """Entrada órfã aqui silenciaria a checagem para um controle real."""
    catalogo = {p.stem for p in DIRETORIO.glob("*.md")}
    assert set(SEM_RESPALDO_OFICIAL) <= catalogo


def test_todo_controle_sem_respaldo_tem_consulta():
    assert set(SEM_RESPALDO_OFICIAL) <= set(CONSULTAS)


def test_motivo_e_frase_utilizavel_em_relatorio():
    """O motivo vai para o relatório do usuário final, não para log."""
    for control_id, motivo in SEM_RESPALDO_OFICIAL.items():
        assert len(motivo.split()) >= 8, control_id
        assert motivo.strip().endswith("."), control_id


def test_controle_sem_respaldo_nao_tem_respaldo():
    assert not tem_respaldo_oficial("CONF-WLD-008")
    assert motivo_da_ausencia("CONF-WLD-008")


def test_controle_com_respaldo_tem_respaldo():
    assert tem_respaldo_oficial("CONF-WLD-002")
    assert motivo_da_ausencia("CONF-WLD-002") == ""


def test_prompt_declara_a_ausencia_e_proibe_citar():
    """Sem isso o modelo receberia seis trechos vizinhos e citaria um deles —
    exatamente o que a auditoria mostrou acontecendo."""
    u = prompt_usuario(_entrada(control_id="CONF-WLD-008"))
    assert "NÃO TEM RESPALDO OFICIAL" in u
    assert "Deixe `citacoes` VAZIO" in u
    assert "catálogo interno" in u


def test_prompt_de_controle_com_respaldo_nao_declara_ausencia():
    u = prompt_usuario(_entrada(control_id="CONF-WLD-002"))
    assert "NÃO TEM RESPALDO OFICIAL" not in u


def test_documento_canonico_continua_presente_sem_respaldo():
    """Ausência de fonte externa não pode virar ausência de norma: o documento
    canônico é justamente o que sustenta o achado nesses casos."""
    assert documento_de("CONF-WLD-008") is not None
    assert "DOCUMENTO CANÔNICO" in prompt_usuario(_entrada(control_id="CONF-WLD-008"))


@pytest.mark.parametrize("control_id", sorted(SEM_RESPALDO_OFICIAL))
def test_cada_controle_sem_respaldo_produz_prompt_coerente(control_id):
    u = prompt_usuario(_entrada(control_id=control_id))
    assert "NÃO TEM RESPALDO OFICIAL" in u
    assert motivo_da_ausencia(control_id) in u
