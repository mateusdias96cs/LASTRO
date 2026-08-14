"""O cache da camada 3 é otimização, não dependência.

Regressão de um erro que chegou ao usuário final em produção:

    PermissionError: [Errno 13] Permission denied: '.cache-analise'

`/app` pertence a root no container — o `WORKDIR` o cria assim, e os
`COPY --chown` só mudam o dono dos caminhos copiados. O caminho relativo
padrão resolvia para `/app/.cache-analise`, e o usuário 10001 não podia criar
o diretório.

O erro em si era o menor dos problemas. `_guardar` roda DEPOIS da chamada ao
modelo e ANTES do `return`: a exceção descartava uma resposta já paga em
tokens, e o achado caía para a explicação do catálogo. Em toda requisição,
porque o cache nunca chegava a existir.
"""

import pytest

from conformidade.agents.analysis.azure_provider import AnalisadorAzureOpenAI
from conformidade.agents.analysis.contracts import AchadoAnalisado, Confianca, Veredito
from conformidade.agents.deterministic.models import Severity


def _saida() -> AchadoAnalisado:
    return AchadoAnalisado(
        control_id="CONF-WLD-001",
        veredito=Veredito.CONFIRMADO,
        severidade_ajustada=Severity.CRITICAL,
        explicacao="O modo privilegiado remove o isolamento entre container e host.",
        como_corrigir="Remova `privileged: true`.",
        confianca=Confianca.ALTA,
    )


def _provedor(cache_dir) -> AnalisadorAzureOpenAI:
    return AnalisadorAzureOpenAI(
        endpoint="https://x.openai.azure.com/", deployment="gpt-5-mini", cache_dir=cache_dir
    )


def test_diretorio_sem_permissao_nao_derruba(tmp_path):
    """O caso exato de produção."""
    sem_permissao = tmp_path / "proibido"
    sem_permissao.mkdir(mode=0o500)
    provedor = _provedor(sem_permissao / "cache")
    try:
        provedor._guardar("abc", _saida())  # não pode levantar
    finally:
        sem_permissao.chmod(0o700)


def test_leitura_de_cache_ilegivel_devolve_none(tmp_path):
    """No pior caso, recalcula — nunca quebra."""
    (tmp_path / "abc.json").write_text("{isto não é json", encoding="utf-8")
    assert _provedor(tmp_path)._do_cache("abc") is None


def test_caminho_gravavel_continua_funcionando(tmp_path):
    """A tolerância à falha não pode desligar o cache quando ele funciona."""
    provedor = _provedor(tmp_path / "cache")
    provedor._guardar("abc", _saida())
    assert provedor._do_cache("abc") == _saida()


def test_avisa_uma_vez_por_processo_e_nao_por_achado(tmp_path, caplog):
    """Um diretório sem permissão geraria um registro por achado em toda
    requisição — o log fica ilegível justamente quando é mais necessário."""
    sem_permissao = tmp_path / "proibido"
    sem_permissao.mkdir(mode=0o500)
    provedor = _provedor(sem_permissao / "cache")
    try:
        with caplog.at_level("WARNING", logger="conformidade.analise"):
            for _ in range(5):
                provedor._guardar("abc", _saida())
    finally:
        sem_permissao.chmod(0o700)
    assert len(caplog.records) == 1
    assert caplog.records[0].erro == "PermissionError"


def test_o_caminho_e_configuravel_por_ambiente(monkeypatch):
    """O Bicep define isto no Container App; o padrão relativo serve ao local."""
    monkeypatch.setenv("CONFORMIDADE_ANALISE_CACHE_DIR", "/tmp/cache-de-teste")
    from conformidade.config import get_settings

    get_settings.cache_clear()
    provedor = AnalisadorAzureOpenAI(endpoint="https://x/", deployment="d")
    get_settings.cache_clear()
    assert str(provedor._cache_dir) == "/tmp/cache-de-teste"


@pytest.mark.skipif(
    not __import__("pathlib").Path("infra/resources.bicep").exists(), reason="sem infra"
)
def test_bicep_define_o_caminho_gravavel():
    """Sem esta variável o container volta ao padrão relativo e ao erro."""
    from pathlib import Path

    bicep = Path("infra/resources.bicep").read_text(encoding="utf-8")
    assert "CONFORMIDADE_ANALISE_CACHE_DIR" in bicep
    assert "/tmp/" in bicep.split("CONFORMIDADE_ANALISE_CACHE_DIR")[1][:80]
