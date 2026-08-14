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


# ---------------------------------------------------------- diagnóstico


def test_diagnostico_responde_por_que_nao_houve_ia(cliente):
    """Existe para responder numa chamada o que custou uma sessão de
    investigação: a mensagem dizia "não configurada" com a configuração
    correta, e a busca foi para o recurso errado."""
    corpo = cliente.get("/api/v1/diagnostico").json()
    assert "camada_3_configurada" in corpo
    assert "camada_3_motivo" in corpo
    assert "camada_3_credencial" in corpo


def test_diagnostico_nao_vaza_valor_de_configuracao(monkeypatch):
    """Informa presença, nunca valor: endpoint e client id não podem aparecer
    numa rota sem autenticação."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://segredo.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-secreto")
    monkeypatch.setenv("CONFORMIDADE_AZURE_CLIENT_ID", "id-secreto")
    from conformidade.config import get_settings
    from conformidade.pipeline import _analisador_ou_motivo

    get_settings.cache_clear()
    _analisador_ou_motivo.cache_clear()

    texto = TestClient(create_app()).get("/api/v1/diagnostico").text

    get_settings.cache_clear()
    _analisador_ou_motivo.cache_clear()

    assert "segredo.openai" not in texto
    assert "gpt-secreto" not in texto
    assert "id-secreto" not in texto
    assert '"endpoint_definido":true' in texto.replace(" ", "")


def test_motivo_distingue_configuracao_ausente_de_outra_falha():
    """A mensagem genérica anterior mandava investigar o lado errado."""
    from conformidade.config import get_settings
    from conformidade.pipeline import _analisador_ou_motivo

    get_settings.cache_clear()
    _analisador_ou_motivo.cache_clear()
    _, motivo = _analisador_ou_motivo()
    _analisador_ou_motivo.cache_clear()
    get_settings.cache_clear()

    assert "AZURE_OPENAI_ENDPOINT" in motivo
    assert "não configurada" not in motivo


def test_client_id_da_identidade_gerenciada_chega_ao_provider(monkeypatch):
    """Identidade atribuída pelo usuário exige client id explícito: sem ele o
    pedido de token é ambíguo e falha longe da causa."""
    monkeypatch.setenv("CONFORMIDADE_AZURE_CLIENT_ID", "1234-abcd")
    from conformidade.agents.analysis.azure_provider import AnalisadorAzureOpenAI
    from conformidade.config import get_settings

    get_settings.cache_clear()
    provider = AnalisadorAzureOpenAI(endpoint="https://x/", deployment="d")
    get_settings.cache_clear()
    assert provider._client_id == "1234-abcd"


# ------------------------------------------------------ progresso real


def test_stream_emite_as_quatro_camadas_em_ordem(cliente):
    """O loader da tela mostra a camada que está rodando. Sem estes eventos,
    qualquer indicador de progresso seria coreografia inventada."""
    import json

    etapas = []
    resultado = None
    with cliente.stream(
        "POST", "/api/v1/auditar/stream", files={"file": ("compose.yaml", COMPOSE)}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for linha in r.iter_lines():
            if not linha.startswith("data: "):
                continue
            evento = json.loads(linha[6:])
            if evento["tipo"] == "etapa" and evento.get("concluida"):
                etapas.append(evento["etapa"])
            elif evento["tipo"] == "resultado":
                resultado = evento["dados"]

    assert etapas == ["deterministico", "recuperacao", "analise", "critico"]
    assert resultado is not None
    assert "privileged: false" in resultado["configuracao_corrigida"]


def test_stream_reporta_progresso_achado_a_achado(cliente):
    """A camada 3 é ~99% do tempo. Um indicador que trate as quatro camadas
    como iguais fica parado no terceiro quarto e parece travado."""
    import json

    contagens = []
    with cliente.stream(
        "POST", "/api/v1/auditar/stream", files={"file": ("compose.yaml", COMPOSE)}
    ) as r:
        for linha in r.iter_lines():
            if linha.startswith("data: "):
                evento = json.loads(linha[6:])
                if evento["tipo"] == "analise":
                    contagens.append((evento["feitos"], evento["total"]))

    assert contagens, "nenhum progresso de análise foi emitido"
    feitos, total = contagens[-1]
    assert feitos == total > 0


def test_rota_original_continua_intacta(cliente):
    """O streaming é adicional. Quem integra por script não deve notar."""
    corpo = _auditar(cliente).json()
    assert corpo["configuracao_corrigida"]
    assert corpo["achados"]
