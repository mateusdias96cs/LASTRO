from conformidade.agents.deterministic.detector import detect
from conformidade.agents.deterministic.models import ArtifactKind

DOCKERFILE = "FROM python:3.12\nRUN echo oi\nUSER 1000\n"
COMPOSE = "services:\n  api:\n    image: nginx\n"
K8S = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: p\n"


def test_detecta_dockerfile_pelo_conteudo():
    d = detect(DOCKERFILE, "arquivo-sem-nome-util.txt")
    assert d.kind is ArtifactKind.DOCKERFILE
    assert d.confidence > 0.8


def test_detecta_compose_pelo_conteudo():
    assert detect(COMPOSE, "deploy.yaml").kind is ArtifactKind.DOCKER_COMPOSE


def test_detecta_kubernetes_pelo_conteudo():
    assert detect(K8S, "deploy.yaml").kind is ArtifactKind.KUBERNETES


def test_conteudo_vence_o_nome():
    """`docker-compose.yml` contendo manifesto Kubernetes é Kubernetes."""
    d = detect(K8S, "docker-compose.yml")
    assert d.kind is ArtifactKind.KUBERNETES


def test_nome_como_ultimo_recurso():
    d = detect("texto solto sem estrutura", "Dockerfile")
    assert d.kind is ArtifactKind.DOCKERFILE
    assert d.confidence < 0.5


def test_desconhecido():
    assert detect("# apenas um readme\n\ntexto", "README.md").kind is ArtifactKind.UNKNOWN


def test_yaml_invalido_nao_estoura():
    assert detect("a: [1, 2\n  b: }{", "x.yaml").kind is ArtifactKind.UNKNOWN
