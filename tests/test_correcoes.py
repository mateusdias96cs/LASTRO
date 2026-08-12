"""Catálogo de correções: cobertura e utilidade.

A checagem central é a de cobertura. Um controle que detecta problema e não
sabe dizer como resolvê-lo entrega meio trabalho, e a falta passaria
despercebida — o relatório simplesmente não mostraria o bloco de configuração.
"""

import pytest
import yaml

from conformidade.agents.critic.contracts import CatalogoDeCorrecoes, CorrecaoAplicavel, Formato
from conformidade.agents.critic.correcoes import (
    CATALOGO,
    correcao_para,
    pares_obrigatorios,
)


def test_todo_par_obrigatorio_tem_correcao():
    """A checagem que impede lacuna silenciosa."""
    faltando = sorted(
        f"{cid}/{fmt.value}" for cid, fmt in pares_obrigatorios() if not correcao_para(cid, fmt)
    )
    assert not faltando, f"controle sem correção para o formato onde dispara: {faltando}"


def test_nenhuma_correcao_orfa():
    """Correção para par que nunca dispara é código morto que dá falsa
    sensação de cobertura."""
    obrigatorios = pares_obrigatorios()
    orfas = sorted(
        f"{c.control_id}/{c.formato.value}"
        for c in CATALOGO.correcoes
        if (c.control_id, c.formato) not in obrigatorios
    )
    assert not orfas, f"correção para par que a camada 1 nunca produz: {orfas}"


def test_duplicata_e_rejeitada():
    base = CATALOGO.correcoes[0]
    with pytest.raises(ValueError, match="duas vezes"):
        CatalogoDeCorrecoes(correcoes=(base, base))


def test_trecho_vazio_e_rejeitado():
    with pytest.raises(ValueError, match="não é copiável"):
        CorrecaoAplicavel(control_id="CONF-WLD-001", formato=Formato.COMPOSE, trecho="   \n ")


@pytest.mark.parametrize(
    "correcao", CATALOGO.correcoes, ids=lambda c: f"{c.control_id}-{c.formato}"
)
def test_correcao_e_utilizavel(correcao):
    """O usuário copia isto direto. Precisa ter substância e explicação."""
    assert correcao.trecho.strip()
    assert not correcao.trecho.startswith("\n")
    assert len(correcao.explicacao.split()) >= 8, "explicação curta demais para quem não é da área"
    assert correcao.explicacao.strip().endswith("."), correcao.control_id


@pytest.mark.parametrize(
    "correcao",
    [c for c in CATALOGO.correcoes if c.formato is not Formato.DOCKERFILE],
    ids=lambda c: f"{c.control_id}-{c.formato}",
)
def test_trecho_yaml_e_yaml_valido(correcao):
    """Compose e Kubernetes são YAML. Trecho que não parseia quebraria o
    arquivo de quem colar — e o erro seria nosso."""
    conteudo = yaml.safe_load(correcao.trecho)
    # Trecho 100% comentado é válido e intencional (ex.: "remova estas linhas").
    if conteudo is None:
        assert all(
            not linha.strip() or linha.strip().startswith("#")
            for linha in correcao.trecho.splitlines()
        ), f"{correcao.control_id}: YAML vazio sem ser comentário"


@pytest.mark.parametrize(
    "correcao",
    [c for c in CATALOGO.correcoes if c.formato is Formato.DOCKERFILE],
    ids=lambda c: c.control_id,
)
def test_trecho_dockerfile_usa_instrucao_conhecida(correcao):
    instrucoes = (
        "FROM",
        "RUN",
        "COPY",
        "ADD",
        "USER",
        "ENTRYPOINT",
        "CMD",
        "HEALTHCHECK",
        "LABEL",
        "ENV",
        "ARG",
        "EXPOSE",
        "WORKDIR",
        "#",
    )
    primeira = correcao.trecho.lstrip().split()[0]
    assert primeira.startswith(instrucoes), f"{correcao.control_id}: `{primeira}` não é instrução"


def test_controles_sem_respaldo_ainda_tem_correcao():
    """Não ter fonte oficial não pode virar não saber corrigir: a norma é
    nossa e o conserto também."""
    from conformidade.agents.retrieval.cobertura import SEM_RESPALDO_OFICIAL

    for control_id in SEM_RESPALDO_OFICIAL:
        pares = {(cid, f) for cid, f in pares_obrigatorios() if cid == control_id}
        for cid, fmt in pares:
            assert correcao_para(cid, fmt), f"{cid}/{fmt.value} sem respaldo E sem correção"


def test_mesmo_controle_difere_entre_formatos():
    """Se Compose e Kubernetes recebessem o mesmo texto, um dos dois estaria
    errado — `read_only` e `readOnlyRootFilesystem` são campos diferentes."""
    compose = correcao_para("CONF-WLD-008", Formato.COMPOSE)
    k8s = correcao_para("CONF-WLD-008", Formato.KUBERNETES)
    assert compose.trecho != k8s.trecho
    assert "read_only" in compose.trecho
    assert "readOnlyRootFilesystem" in k8s.trecho
