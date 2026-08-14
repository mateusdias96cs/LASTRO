"""Regressões de segurança.

Cada teste aqui corresponde a uma vulnerabilidade que foi **medida** neste
sistema, não a uma preocupação genérica. O comentário de cada um diz o que
estava exposto antes.
"""

import pytest
from fastapi.testclient import TestClient

from conformidade.api.limite import JanelaDeslizante, ip_do_cliente
from conformidade.main import create_app

COMPOSE = b"services:\n  a:\n    image: x:latest\n    privileged: true\n"


@pytest.fixture
def cliente():
    return TestClient(create_app())


# ── V3: campo `contexto` sem teto ───────────────────────────────────────────
# Antes: 200.000 caracteres aceitos. O texto vai junto de cada achado para o
# modelo, então o custo em tokens era multiplicado pelo número de achados.


def test_contexto_gigante_e_recusado(cliente):
    r = cliente.post(
        "/api/v1/auditar", files={"file": ("c.yaml", COMPOSE)}, data={"contexto": "A" * 50_000}
    )
    assert r.status_code == 422


def test_contexto_normal_continua_passando(cliente):
    r = cliente.post(
        "/api/v1/auditar",
        files={"file": ("c.yaml", COMPOSE)},
        data={"contexto": "coletor de log em DaemonSet, precisa ler /var/log do nó"},
    )
    assert r.status_code == 200


# ── V4: exceção interna vazando para o cliente ──────────────────────────────
# Antes: `{'detail': 'não foi possível interpretar o arquivo: maximum
# recursion depth exceeded'}`, e antes disso o PermissionError do cache com o
# caminho absoluto dentro do container.


def test_erro_de_parse_nao_vaza_a_excecao(cliente):
    fundo = b"services:\n  a:\n    command: " + b"[" * 2000 + b"]" * 2000 + b"\n"
    r = cliente.post("/api/v1/auditar", files={"file": ("f.yaml", fundo)})
    assert r.status_code == 422
    detalhe = r.json()["detail"]
    assert "recursion" not in detalhe
    assert "Error" not in detalhe
    assert "Dockerfile" in detalhe  # a frase útil continua lá


# ── V5: corpo lido inteiro antes de medir ───────────────────────────────────


def test_corpo_grande_recusado_pelo_cabecalho(cliente):
    r = cliente.post(
        "/api/v1/auditar",
        content=b"x" * 100,
        headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "text/plain"},
    )
    assert r.status_code == 413


def test_arquivo_acima_do_teto_recusado(cliente):
    r = cliente.post("/api/v1/auditar", files={"file": ("g.yaml", b"#" * (3 * 1024 * 1024))})
    assert r.status_code == 413


# ── V1: consumo ilimitado ───────────────────────────────────────────────────


def test_janela_libera_ate_o_teto_e_recusa_depois():
    j = JanelaDeslizante(janela=60, maximo=3)
    assert [j.permitir("1.2.3.4")[0] for _ in range(3)] == [True, True, True]
    permitida, espera = j.permitir("1.2.3.4")
    assert not permitida
    assert espera > 0


def test_o_limite_e_por_ip_e_nao_global():
    """Um abusador não pode negar serviço a todo mundo."""
    j = JanelaDeslizante(janela=60, maximo=2)
    for _ in range(5):
        j.permitir("abusador")
    assert j.permitir("outra-pessoa")[0] is True


def test_janela_desliza(monkeypatch):
    import conformidade.api.limite as m

    agora = [1000.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: agora[0])
    j = m.JanelaDeslizante(janela=60, maximo=2)
    j.permitir("ip")
    j.permitir("ip")
    assert j.permitir("ip")[0] is False
    agora[0] += 61
    assert j.permitir("ip")[0] is True


def test_ip_vem_do_ultimo_x_forwarded_for():
    """O primeiro valor é escolhido pelo cliente; o último, pelo ingress.

    Ler o primeiro tornaria o limite decorativo: bastaria variar o cabeçalho a
    cada requisição para nunca ser contado duas vezes na mesma chave.
    """

    class FakeReq:
        headers = {"x-forwarded-for": "1.1.1.1, 2.2.2.2, 9.9.9.9"}
        client = None

    assert ip_do_cliente(FakeReq()) == "9.9.9.9"


def test_dicionario_de_ips_nao_cresce_sem_limite():
    import conformidade.api.limite as m

    j = m.JanelaDeslizante(janela=60, maximo=100)
    for i in range(m.MAX_IPS + 500):
        j.permitir(f"ip-{i}")
    assert len(j._marcas) <= m.MAX_IPS + 1


def test_health_nunca_e_limitado(cliente):
    """Um 429 numa probe reinicia o container: a defesa derrubaria o serviço."""
    for _ in range(60):
        assert cliente.get("/health/live").status_code == 200
        assert cliente.get("/health/startup").status_code == 200


def test_rota_cara_devolve_429_com_retry_after(cliente):
    import conformidade.api.limite as m

    limite = m.MAX_NA_JANELA
    ultimo = None
    for _ in range(limite + 2):
        ultimo = cliente.post("/api/v1/auditar", files={"file": ("c.yaml", COMPOSE)})
    assert ultimo.status_code == 429
    assert "Retry-After" in ultimo.headers
