"""Contrato da rota que o frontend consome.

Estes testes existem porque o frontend depende de campos específicos deste
JSON. Uma refatoração interna das camadas 3 e 4 não pode mudar o shape sem
que algo quebre aqui — do contrário a tela quebra em produção, silenciosa.
"""

import pytest
from fastapi.testclient import TestClient

from conformidade.main import create_app

COMPOSE = b"""services:
  api:
    image: minhaapp:latest
    privileged: true
    network_mode: host
"""


@pytest.fixture
def cliente():
    return TestClient(create_app())


def _auditar(cliente, conteudo=COMPOSE, nome="compose.yaml"):
    return cliente.post("/api/v1/auditar", files={"file": (nome, conteudo)})


# ------------------------------------------------------------------- CORS


def test_preflight_libera_o_frontend_local():
    """Sem isto o navegador bloqueia a chamada e o erro chega como falha de
    rede genérica — o modo de falha mais confuso de diagnosticar."""
    cliente = TestClient(create_app())
    r = cliente.options(
        "/api/v1/auditar",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_origem_nao_declarada_nao_recebe_liberacao():
    cliente = TestClient(create_app())
    r = cliente.options(
        "/api/v1/auditar",
        headers={
            "Origin": "https://site-qualquer.exemplo",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") != "https://site-qualquer.exemplo"


def test_origem_de_producao_e_configuravel(monkeypatch):
    monkeypatch.setenv("CONFORMIDADE_CORS_ORIGINS", "https://ca-web.exemplo.io")
    from conformidade.config import get_settings

    get_settings.cache_clear()
    cliente = TestClient(create_app())
    r = cliente.options(
        "/api/v1/auditar",
        headers={
            "Origin": "https://ca-web.exemplo.io",
            "Access-Control-Request-Method": "POST",
        },
    )
    get_settings.cache_clear()
    assert r.headers["access-control-allow-origin"] == "https://ca-web.exemplo.io"


# --------------------------------------------------------------- contrato


def test_resposta_traz_a_configuracao_corrigida(cliente):
    """A entrega principal. Se sumir, o produto sumiu."""
    corpo = _auditar(cliente).json()
    assert "privileged: false" in corpo["configuracao_corrigida"]
    assert "minhaapp:latest" in corpo["configuracao_corrigida"]


def test_achados_vem_estruturados_e_ordenados_por_risco(cliente):
    achados = _auditar(cliente).json()["achados"]
    assert achados
    assert achados[0]["severidade"] == "critical"
    ordem = ["critical", "high", "medium", "low", "info"]
    indices = [ordem.index(a["severidade"]) for a in achados]
    assert indices == sorted(indices)


def test_cada_achado_tem_o_que_a_tela_precisa(cliente):
    for achado in _auditar(cliente).json()["achados"]:
        assert achado["control_id"] and achado["titulo"] and achado["explicacao"]
        assert achado["severidade"] in {"critical", "high", "medium", "low", "info"}
        assert isinstance(achado["citacoes"], list)
        assert isinstance(achado["ressalvas"], list)


def test_manuais_vem_separados_dos_automaticos(cliente):
    corpo = _auditar(cliente).json()
    assert set(corpo["dependem_de_voce"]) & {"CONF-IMG-002"}
    assert not set(corpo["dependem_de_voce"]) & set(corpo["corrigidos_automaticamente"])


def test_arquivo_vazio_devolve_422(cliente):
    r = cliente.post("/api/v1/auditar", files={"file": ("vazio.yaml", b"   ")})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_arquivo_nao_utf8_devolve_422(cliente):
    r = cliente.post("/api/v1/auditar", files={"file": ("bin.yaml", b"\xff\xfe\x00binario")})
    assert r.status_code == 422


def test_rota_de_texto_puro_devolve_so_o_arquivo(cliente):
    r = cliente.post("/api/v1/auditar/configuracao", files={"file": ("compose.yaml", COMPOSE)})
    assert r.status_code == 200
    assert r.text.startswith("services:")
    assert "privileged: false" in r.text
