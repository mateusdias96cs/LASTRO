"""Testes do motor de regras e das propriedades que a camada promete."""

from pathlib import Path

import pytest

from conformidade.agents.deterministic import analyze, analyze_path, list_controls
from conformidade.agents.deterministic.models import ArtifactKind, Severity

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def dockerfile_inseguro():
    return analyze_path(FIXTURES / "inseguro.Dockerfile")


@pytest.fixture(scope="module")
def compose_inseguro():
    return analyze_path(FIXTURES / "inseguro-compose.yaml")


@pytest.fixture(scope="module")
def k8s_inseguro():
    return analyze_path(FIXTURES / "inseguro-k8s.yaml")


def _controles(report) -> set[str]:
    return {f.control_id for f in report.findings}


# ------------------------------------------------------------ invariantes


def test_todo_achado_tem_controle_no_catalogo(dockerfile_inseguro, compose_inseguro, k8s_inseguro):
    """A promessa central da camada: nenhum achado sem identificador de controle
    conhecido — é a chave que o agente de recuperação vai buscar no corpus."""
    catalogo = {c.control_id for c in list_controls()}
    for report in (dockerfile_inseguro, compose_inseguro, k8s_inseguro):
        for f in report.findings:
            assert f.control_id in catalogo
            assert f.title and f.remediation
            assert f.location.file


def test_catalogo_sem_control_id_duplicado():
    ids = [c.control_id for c in list_controls()]
    assert len(ids) == len(set(ids))


def test_achados_ordenados_por_severidade():
    report = analyze_path(FIXTURES / "inseguro-k8s.yaml")
    rank = {
        s: i
        for i, s in enumerate(
            [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
        )
    }
    posicoes = [rank[f.severity] for f in report.findings]
    assert posicoes == sorted(posicoes)


# ------------------------------------------------------- reprodutibilidade


def test_mesma_entrada_produz_relatorio_identico():
    """A razão de ser desta camada. Se dois runs divergirem, ela não serve como
    linha de base e nenhuma comparação entre execuções tem valor."""
    conteudo = (FIXTURES / "inseguro-k8s.yaml").read_bytes()
    a = analyze(conteudo, "inseguro-k8s.yaml").model_dump_json()
    b = analyze(conteudo, "inseguro-k8s.yaml").model_dump_json()
    assert a == b


def test_relatorio_nao_contem_campo_de_relogio():
    """Timestamp ou duração quebrariam a igualdade byte a byte acima."""
    report = analyze("FROM alpine\n", "Dockerfile")
    serializado = report.model_dump_json().lower()
    for proibido in ("timestamp", "duration", "elapsed", "generated_at", "analyzed_at"):
        assert proibido not in serializado


def test_fingerprint_estavel_entre_execucoes():
    conteudo = (FIXTURES / "inseguro-compose.yaml").read_bytes()
    p1 = [f.fingerprint for f in analyze(conteudo, "c.yaml").findings]
    p2 = [f.fingerprint for f in analyze(conteudo, "c.yaml").findings]
    assert p1 == p2 and all(p1)


# ----------------------------------------------------------------- regras


@pytest.mark.parametrize(
    "control_id",
    [
        "CONF-DKR-001",  # stage final sem USER
        "CONF-DKR-003",  # ADD local
        "CONF-DKR-004",  # ADD remoto
        "CONF-DKR-005",  # curl | sh
        "CONF-DKR-006",  # apt-get upgrade
        "CONF-DKR-007",  # sudo
        "CONF-DKR-008",  # chmod 777
        "CONF-DKR-011",  # COPY .
        "CONF-DKR-012",  # EXPOSE 22
        "CONF-DKR-013",  # ENTRYPOINT forma shell
        "CONF-DKR-014",  # segredo em ENV/ARG
        "CONF-DKR-015",  # MAINTAINER
        "CONF-IMG-001",  # imagem sem tag
    ],
)
def test_dockerfile_dispara_controle(dockerfile_inseguro, control_id):
    assert control_id in _controles(dockerfile_inseguro)


def test_dockerfile_detecta_chmod_dentro_do_heredoc(dockerfile_inseguro):
    """Sem suporte a heredoc, o comando dentro dele passaria despercebido."""
    achados = [f for f in dockerfile_inseguro.findings if f.control_id == "CONF-DKR-008"]
    assert any("chmod 777" in (f.evidence or "") for f in achados)


@pytest.mark.parametrize(
    "control_id",
    [
        "CONF-WLD-001",  # privileged
        "CONF-WLD-002",  # docker.sock
        "CONF-WLD-003",  # /etc do host
        "CONF-WLD-004",  # host namespace
        "CONF-WLD-005",  # SYS_ADMIN
        "CONF-WLD-007",  # root
        "CONF-SEC-001",  # token literal
        "CONF-CMP-001",  # no-new-privileges
        "CONF-CMP-002",  # porta 5432 exposta
        "CONF-IMG-002",  # tag latest
    ],
)
def test_compose_dispara_controle(compose_inseguro, control_id):
    assert control_id in _controles(compose_inseguro)


@pytest.mark.parametrize(
    "control_id",
    ["CONF-K8S-001", "CONF-K8S-002", "CONF-K8S-003", "CONF-K8S-004", "CONF-K8S-005"],
)
def test_k8s_dispara_controle(k8s_inseguro, control_id):
    assert control_id in _controles(k8s_inseguro)


def test_workload_bem_configurada_nao_gera_achado(k8s_inseguro):
    """Ruído mata auditor: o pod endurecido do fixture precisa sair limpo."""
    do_pod_seguro = [f for f in k8s_inseguro.findings if f.target == "app-seguro/app"]
    assert do_pod_seguro == []


def test_compose_servico_endurecido_gera_poucos_achados(compose_inseguro):
    """O serviço `banco` só erra em hostPID e user root; o resto está correto."""
    controles = {f.control_id for f in compose_inseguro.findings if f.target == "banco"}
    assert controles == {"CONF-WLD-004", "CONF-WLD-007"}


# -------------------------------------------------- falsos positivos comuns


def test_variavel_com_sufixo_file_nao_e_segredo(compose_inseguro):
    """`DB_PASSWORD_FILE` aponta para um segredo, não o contém."""
    nomes = [f.evidence or "" for f in compose_inseguro.findings if f.control_id == "CONF-SEC-001"]
    assert not any("DB_PASSWORD_FILE" in n for n in nomes)


def test_env_por_referencia_nao_e_segredo(k8s_inseguro):
    """`valueFrom.secretKeyRef` não tem valor no arquivo."""
    nomes = [f.evidence or "" for f in k8s_inseguro.findings if f.control_id == "CONF-SEC-001"]
    assert not any("TOKEN_FROM_SECRET" in n for n in nomes)


def test_volume_nomeado_nao_vira_host_path(compose_inseguro):
    achados = [f for f in compose_inseguro.findings if f.control_id == "CONF-WLD-003"]
    assert all("dados" not in (f.evidence or "") for f in achados)


def test_imagem_com_digest_nao_gera_achado_de_pinagem(compose_inseguro):
    do_banco = {f.control_id for f in compose_inseguro.findings if f.target == "banco"}
    assert "CONF-IMG-003" not in do_banco


def test_init_container_nao_exige_probe(k8s_inseguro):
    achados = [f for f in k8s_inseguro.findings if f.control_id == "CONF-WLD-010"]
    assert all("setup" not in (f.target or "") for f in achados)


# ---------------------------------------------------------------- segredos


def test_segredo_nunca_aparece_no_relatorio(dockerfile_inseguro, compose_inseguro):
    """O relatório circula entre agentes e vai para logs — não pode carregar
    o segredo em claro."""
    for report in (dockerfile_inseguro, compose_inseguro):
        texto = report.model_dump_json()
        assert "SenhaSuperSecreta123" not in texto
        assert "AKIAIOSFODNN7EXAMPLE" not in texto
        assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in texto


# ------------------------------------------------------------------ geral


def test_arquivo_desconhecido_nao_gera_achado():
    report = analyze("apenas um texto qualquer\n", "notas.txt")
    assert report.artifact.kind is ArtifactKind.UNKNOWN
    assert report.findings == []
    assert report.artifact.parse_errors


def test_arquivo_vazio_nao_estoura():
    report = analyze("", "vazio.yaml")
    assert report.summary.total == 0


def test_dockerfile_do_proprio_projeto_esta_limpo():
    """Dogfooding: a imagem que este sistema roda não pode violar seus controles
    de severidade alta."""
    report = analyze_path(Path(__file__).parent.parent / "Dockerfile")
    graves = [f for f in report.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    assert graves == [], [f"{f.control_id}: {f.message}" for f in graves]
