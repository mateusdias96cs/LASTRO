"""Extrator do CIS Benchmark.

O PDF não vai para o repositório — é CC BY-NC-SA e fica em `.corpus-cache/`,
baixado manualmente. Os testes que dependem dele pulam quando ele não está
presente; os que verificam a forma do parser rodam sempre, sobre texto sintético
que reproduz a estrutura do documento.
"""

from pathlib import Path

import pytest

from conformidade.agents.retrieval.ingest.extract import (
    BLOCOS_CIS,
    SECOES_NO_ESCOPO,
    extrair_cis,
)

PDF = Path(__file__).resolve().parents[1] / ".corpus-cache" / "CIS_Docker_Benchmark_v1.8.0.pdf"
precisa_do_pdf = pytest.mark.skipif(not PDF.exists(), reason="CIS PDF não está no cache local")


def test_audit_fica_de_fora():
    """`Audit` são comandos `docker inspect` contra container em execução. Nós
    lemos arquivo de configuração: o bloco seria texto longo e não citável."""
    assert "Audit" not in BLOCOS_CIS
    assert "Remediation" in BLOCOS_CIS


def test_escopo_e_so_imagem_e_runtime():
    """Seções 1 a 3 são host e daemon, 7 é Swarm — nada disso aparece na
    entrada que o sistema recebe."""
    assert set(SECOES_NO_ESCOPO) == {"4", "5"}


@precisa_do_pdf
def test_extrai_as_44_recomendacoes_no_escopo():
    secoes = extrair_cis(str(PDF))
    assert len(secoes) == 44


@precisa_do_pdf
def test_nenhuma_recomendacao_fora_do_escopo():
    for s in extrair_cis(str(PDF)):
        numero = s.heading_path.rsplit(" > ", 1)[-1].split()[0]
        assert numero.split(".")[0] in SECOES_NO_ESCOPO, s.heading_path


@precisa_do_pdf
def test_o_sumario_nao_vira_secao():
    """Sem a âncora `Profile Applicability:` o parser casaria com as linhas do
    índice, que repetem número e título seguidos de pontilhado e página."""
    for s in extrair_cis(str(PDF)):
        assert "......" not in s.texto


@precisa_do_pdf
def test_traz_a_configuracao_correta():
    """`Remediation` é o motivo de o CIS existir no corpus: é o único texto
    oficial que diz qual é o valor certo, não só o que o campo faz."""
    secoes = extrair_cis(str(PDF))
    com_remediacao = [s for s in secoes if "Remediation:" in s.texto]
    assert len(com_remediacao) >= 40


@precisa_do_pdf
def test_rodape_de_pagina_nao_polui_o_texto():
    for s in extrair_cis(str(PDF)):
        assert "Internal Only" not in s.texto


@precisa_do_pdf
def test_recomendacao_conhecida_sai_completa():
    secoes = {s.heading_path.rsplit(" > ", 1)[-1].split()[0]: s for s in extrair_cis(str(PDF))}
    rootfs = secoes["5.13"]
    assert "read only" in rootfs.heading_path
    assert "--read-only" in rootfs.texto
    assert rootfs.texto.startswith("Description:")


@precisa_do_pdf
def test_extracao_e_deterministica():
    a = extrair_cis(str(PDF))
    b = extrair_cis(str(PDF))
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
