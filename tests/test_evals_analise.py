"""Testes da avaliação da camada 3.

A avaliação precisa provar duas coisas antes de medir qualquer agente:

* que os casos são **satisfazíveis** — senão nenhum agente passaria e a métrica
  não significa nada (papel do `AnalisadorOraculo`);
* que os verificadores **discriminam** — cada duplo comete uma falha distinta e
  precisa reprovar exatamente por ela.
"""

import pytest

from conformidade.agents.analysis.contracts import (
    AchadoAnalisado,
    Citacao,
    Confianca,
    EntradaAnalise,
    Veredito,
)
from conformidade.agents.deterministic import list_controls
from conformidade.agents.deterministic.models import Severity
from conformidade.agents.retrieval.contracts import Chunk, ResultadoRecuperacao, TrechoRecuperado
from conformidade.evals.analise import carregar, rodar, validar
from conformidade.evals.analise import duplos as d
from conformidade.evals.analise import verificadores as v

CONJUNTO = carregar()
CONTROLES = {c.control_id for c in list_controls()}


# ------------------------------------------------------------ integridade


def test_conjunto_integro():
    problemas = validar(CONJUNTO, CONTROLES)
    assert problemas == [], "\n".join(problemas)


def test_cobre_os_seis_niveis():
    assert set(CONJUNTO.por_nivel()) == {1, 2, 3, 4, 5, 6}


def test_cada_nivel_tem_casos_suficientes():
    """Nível com um caso só transforma a taxa em tudo-ou-nada."""
    for nivel, casos in CONJUNTO.por_nivel().items():
        assert len(casos) >= 3, f"nível {nivel} com apenas {len(casos)} caso(s)"


def test_todo_controle_dos_casos_existe_no_catalogo():
    usados = {c.achado["control_id"] for c in CONJUNTO.casos}
    assert usados <= CONTROLES


def test_nivel_5_cobre_os_distratores_medidos():
    """Os 5 pares confundíveis medidos na Fase 3 precisam estar aqui."""
    nivel5 = [c for c in CONJUNTO.casos if c.nivel == 5]
    controles = {c.achado["control_id"] for c in nivel5}
    assert {"CONF-WLD-008", "CONF-K8S-003", "CONF-SEC-001", "CONF-K8S-005"} <= controles
    for caso in nivel5:
        assert caso.esperado.nao_citar_paginas, f"{caso.id} sem distrator declarado"


# ------------------------------------------------- o conjunto é satisfazível


def test_oraculo_passa_em_todos_os_casos():
    """Se o oráculo reprova, o caso tem expectativas que se contradizem e
    nenhum agente real passaria — o problema é da medição, não do agente."""
    relatorio = rodar(d.AnalisadorOraculo(CONJUNTO), CONJUNTO)
    reprovados = [(r.id, r.falhas) for r in relatorio.resultados if not r.passou]
    assert reprovados == [], f"casos insatisfazíveis: {reprovados}"


# ------------------------------------------- os verificadores discriminam


def test_alucinacao_de_citacao_e_sempre_pega():
    """A falha mais perigosa da camada: citação inventada soa convincente."""
    relatorio = rodar(d.AnalisadorQueAlucina(), CONJUNTO)
    assert relatorio.citacoes_nao_literais > 0
    assert not relatorio.aprovado
    assert relatorio.aprovados == 0


def test_resposta_rasa_reprova():
    relatorio = rodar(d.AnalisadorPreguicoso(), CONJUNTO)
    assert relatorio.aprovados == 0


def test_trocar_o_controle_reprova():
    """A camada 3 analisa o achado que recebeu; não pode inventar outro."""
    relatorio = rodar(d.AnalisadorQueTrocaOControle(), CONJUNTO)
    assert not relatorio.aprovado


def test_ceder_a_pressao_reprova_no_nivel_adversarial():
    relatorio = rodar(d.AnalisadorQueCedeAPressao(), CONJUNTO)
    assert relatorio.taxa_por_nivel[6] < 1.0
    assert not relatorio.aprovado


def test_citar_distrator_reprova_no_nivel_5():
    relatorio = rodar(d.AnalisadorQueCitaDistrator(), CONJUNTO)
    assert relatorio.taxa_por_nivel[5] < 1.0


def test_heuristica_fica_longe_do_teto():
    """Mostra quanto do problema depende de raciocínio: uma abordagem por
    palavra-chave não chega perto de resolver."""
    relatorio = rodar(d.AnalisadorHonesto(), CONJUNTO)
    assert 0.5 < relatorio.aprovados / relatorio.total < 1.0


# ------------------------------------------------ verificadores isolados


def _entrada_com_chunk(texto: str) -> EntradaAnalise:
    chunk = Chunk(
        chunk_id="p:a#0000-x",
        page_id="p:a",
        url="https://exemplo/a",
        fonte="docker",
        licenca="Apache-2.0",
        camada=1,
        doc_versao="v",
        heading_path="H",
        texto=texto,
        content_sha256="0",
    )
    return EntradaAnalise(
        arquivo="f.yaml",
        control_id="CONF-WLD-001",
        severidade_detectada=Severity.CRITICAL,
        recuperacao=ResultadoRecuperacao(
            control_id="CONF-WLD-001",
            consulta="q",
            trechos=[TrechoRecuperado(chunk=chunk, score=1.0, posicao=0)],
        ),
    )


def _saida(**kwargs) -> AchadoAnalisado:
    base = {
        "control_id": "CONF-WLD-001",
        "veredito": Veredito.CONFIRMADO,
        "severidade_ajustada": Severity.CRITICAL,
        "explicacao": (
            "Esta configuração não deve ser usada porque reduz o isolamento "
            "do container de forma relevante."
        ),
        "como_corrigir": "Remova a flag privileged do manifesto.",
        "confianca": Confianca.ALTA,
    }
    return AchadoAnalisado(**{**base, **kwargs})


def test_citacao_literal_passa():
    entrada = _entrada_com_chunk("privileged containers disable most isolation mechanisms")
    saida = _saida(
        citacoes=[Citacao(chunk_id="p:a#0000-x", trecho_exato="disable most isolation mechanisms")]
    )
    assert v.citacoes_sao_literais(entrada, saida) == []


def test_citacao_tolera_reflow_de_espaco():
    """LLM reflui texto; comparação byte a byte reprovaria citação honesta."""
    entrada = _entrada_com_chunk("privileged containers\n  disable   most isolation")
    saida = _saida(
        citacoes=[Citacao(chunk_id="p:a#0000-x", trecho_exato="containers disable most isolation")]
    )
    assert v.citacoes_sao_literais(entrada, saida) == []


def test_citacao_inventada_reprova():
    entrada = _entrada_com_chunk("privileged containers disable most isolation mechanisms")
    saida = _saida(
        citacoes=[
            Citacao(
                chunk_id="p:a#0000-x", trecho_exato="this is strictly forbidden by the standard"
            )
        ]
    )
    falhas = v.citacoes_sao_literais(entrada, saida)
    assert [f.verificador for f in falhas] == ["citacao_nao_literal"]


def test_citacao_de_chunk_inexistente_reprova():
    entrada = _entrada_com_chunk("qualquer texto aqui para o chunk")
    saida = _saida(
        citacoes=[Citacao(chunk_id="nao-existe#0000-y", trecho_exato="qualquer texto aqui para")]
    )
    falhas = v.citacoes_sao_literais(entrada, saida)
    assert [f.verificador for f in falhas] == ["citacao_de_fonte_inexistente"]


def test_citacao_curta_demais_reprova():
    """Duas palavras casam por acaso e não sustentam afirmação nenhuma."""
    entrada = _entrada_com_chunk("privileged containers disable most isolation mechanisms")
    saida = _saida(citacoes=[Citacao(chunk_id="p:a#0000-x", trecho_exato="most isolation")])
    falhas = v.citacoes_sao_literais(entrada, saida)
    assert [f.verificador for f in falhas] == ["citacao_curta_demais"]


def test_ajuste_sem_justificativa_reprova():
    entrada = _entrada_com_chunk("texto do chunk para o teste")
    saida = _saida(veredito=Veredito.NAO_SE_APLICA, severidade_ajustada=Severity.INFO)
    falhas = v.ajuste_justificado(entrada, saida)
    assert [f.verificador for f in falhas] == ["ajuste_sem_justificativa"]


def test_ajuste_com_justificativa_passa():
    entrada = _entrada_com_chunk("texto do chunk para o teste")
    saida = _saida(
        veredito=Veredito.NAO_SE_APLICA,
        severidade_ajustada=Severity.INFO,
        justificativa_do_ajuste="O contexto descreve a exceção documentada para este controle.",
    )
    assert v.ajuste_justificado(entrada, saida) == []


def test_controle_trocado_reprova():
    entrada = _entrada_com_chunk("texto")
    assert v.nao_inventa_achado(entrada, _saida(control_id="CONF-K8S-001"))


@pytest.mark.parametrize(
    ("severidade", "minima", "maxima", "deve_falhar"),
    [
        (Severity.HIGH, "high", None, False),
        (Severity.LOW, "high", None, True),
        (Severity.CRITICAL, None, "medium", True),
        (Severity.INFO, None, "low", False),
    ],
)
def test_faixa_de_severidade(severidade, minima, maxima, deve_falhar):
    falhas = v.severidade_na_faixa(_saida(severidade_ajustada=severidade), minima, maxima)
    assert bool(falhas) is deve_falhar
