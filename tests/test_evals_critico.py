"""Avaliação da camada 4: a trava discrimina?

`tests/test_critico.py` prova que o crítico **roda** — cada checagem isolada
produz o reparo certo. Este arquivo prova que ele **decide**: pega o que deve
pegar e, igualmente importante, deixa passar o que está correto.

A segunda metade é a que faltava. Um crítico que rebaixasse tudo passaria em
qualquer conjunto que só perguntasse "pegou o erro?" — pega todos, por
acidente. É o `critico_paranoico` que força o conjunto a ter casos de
aprovação, e o `critico_cego` que força os de reparo.
"""

import pytest

from conformidade.agents.critic import criticar
from conformidade.agents.critic.contracts import VereditoCritico
from conformidade.evals.critico import (
    CASOS,
    critico_cego,
    critico_paranoico,
    deveriam_aprovar,
    deveriam_reprovar,
    formatar,
    rodar,
)

# ------------------------------------------------------------- integridade


def test_conjunto_tem_os_dois_lados():
    """Sem casos de aprovação, um crítico que rebaixa tudo passaria."""
    assert len(deveriam_aprovar()) >= 3
    assert len(deveriam_reprovar()) >= 5


def test_conjunto_cobre_as_quatro_checagens():
    """As quatro coisas que o crítico real faz precisam estar exercitadas."""
    esperados = {v for c in CASOS for v in c.verificadores_esperados}
    assert {
        "controle_trocado",
        "citacao_nao_literal",
        "citacao_de_fonte_inexistente",
        "citou_distrator",
        "ajuste_sem_justificativa",
        "confianca_sem_respaldo",
    } <= esperados


def test_ids_nao_se_repetem():
    ids = [c.id for c in CASOS]
    assert len(ids) == len(set(ids))


def test_o_distrator_do_caso_continua_declarado_no_gabarito():
    """O caso `cita-distrator` depende de `k8s:volumes` ser distrator do
    CONF-WLD-008. Se o gabarito mudar, o caso vira ruído silencioso: o crítico
    não teria como acusar e o teste reprovaria por motivo errado."""
    from conformidade.evals.critico.casos import CONTROLE_COM_DISTRATOR, PAGINA_DISTRATORA
    from conformidade.evals.golden import carregar_gabarito

    caso = carregar_gabarito().caso(CONTROLE_COM_DISTRATOR)
    assert caso is not None
    assert PAGINA_DISTRATORA in caso.nao_deve


# --------------------------------------------------------- o crítico real


def test_critico_real_passa_em_todos():
    """Determinístico: não há taxa aceitável abaixo de 100%. Qualquer caso
    reprovado aqui é defeito do crítico, não variação."""
    relatorio = rodar(criticar)
    assert relatorio.aprovado, formatar(relatorio)
    assert relatorio.taxa == 1.0


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c.id)
def test_cada_caso_isolado(caso):
    """Falha aponta o caso, não só o total."""
    resultado = criticar(caso.entrada, caso.saida)
    assert resultado.veredito is caso.veredito_esperado, caso.descricao
    emitidos = {o.verificador for o in resultado.objecoes}
    assert caso.verificadores_esperados <= emitidos


# ------------------------------------------------------------- os duplos


def test_critico_cego_deixa_passar_tudo_que_deveria_pegar():
    """Mede o custo de não ter a camada 4: cada caso aqui é uma afirmação sem
    respaldo que chegaria ao usuário parecendo verificada."""
    relatorio = rodar(critico_cego, deveriam_reprovar())
    assert relatorio.aprovados == 0, formatar(relatorio)


def test_critico_cego_acerta_por_acidente_os_de_aprovacao():
    """Ele aprova tudo, então acerta os de aprovação sem ter olhado. É o que
    torna o conjunto capaz de distinguir mérito de sorte."""
    assert rodar(critico_cego, deveriam_aprovar()).taxa == 1.0


def test_critico_paranoico_reprova_o_que_estava_correto():
    relatorio = rodar(critico_paranoico, deveriam_aprovar())
    assert relatorio.aprovados == 0, formatar(relatorio)


def test_critico_paranoico_tambem_erra_o_que_deveria_pegar():
    """Rebaixar pelo motivo errado não conta como pegar: o relatório mostraria
    uma ressalva que não corresponde ao problema."""
    relatorio = rodar(critico_paranoico, deveriam_reprovar())
    assert relatorio.aprovados == 0, formatar(relatorio)


def test_nenhum_duplo_passa_no_conjunto_inteiro():
    """Se um duplo passar, o conjunto não discrimina e precisa de mais casos —
    mesmo princípio do `AnalisadorHonesto` na camada 3."""
    for nome, duplo in (("cego", critico_cego), ("paranoico", critico_paranoico)):
        relatorio = rodar(duplo)
        assert not relatorio.aprovado, f"duplo `{nome}` passou e não deveria"


def test_duplos_falham_por_motivos_opostos():
    """Se os dois falhassem nos mesmos casos, um deles seria redundante."""
    cego = {r.id for r in rodar(critico_cego).resultados if not r.passou}
    paranoico = {r.id for r in rodar(critico_paranoico).resultados if not r.passou}
    assert cego & paranoico == cego, "o paranoico deveria falhar em tudo que o cego falha"
    assert paranoico - cego, "o paranoico precisa falhar também nos casos de aprovação"


# -------------------------------------------------------------- relatório


def test_formatar_mostra_aprovado_e_reprovado():
    assert "APROVADO" in formatar(rodar(criticar))
    saida = formatar(rodar(critico_paranoico))
    assert "REPROVADO" in saida
    assert "veredito_inesperado" in saida


def test_erro_no_critico_vira_caso_reprovado_e_nao_derruba():
    def quebrado(entrada, saida):
        raise RuntimeError("boom")

    relatorio = rodar(quebrado)
    assert relatorio.aprovados == 0
    assert all("RuntimeError" in r.erro for r in relatorio.resultados)


def test_avaliacao_e_deterministica():
    assert formatar(rodar(criticar)) == formatar(rodar(criticar))


def test_veredito_descartado_preserva_o_control_id_da_entrada():
    """A saída descartada não pode carregar o controle inventado adiante."""
    caso = next(c for c in CASOS if c.veredito_esperado is VereditoCritico.DESCARTADO)
    resultado = criticar(caso.entrada, caso.saida)
    assert resultado.control_id == caso.entrada.control_id
    assert resultado.analisado.control_id == caso.entrada.control_id
