"""Detecção do tipo de artefato.

O nome do arquivo é só uma pista — gente renomeia, sistemas de upload perdem a
extensão, e `deploy.yaml` tanto pode ser Compose quanto Kubernetes. Por isso o
conteúdo é o que decide, e o nome só desempata. A detecção devolve confiança e
motivo, para o achado poder explicar por que foi analisado daquele jeito.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from conformidade.agents.deterministic.models import ArtifactKind
from conformidade.agents.deterministic.parsers.dockerfile import KNOWN_INSTRUCTIONS

_DOCKERFILE_NAMES = re.compile(r"^(dockerfile|containerfile)(\..+)?$", re.IGNORECASE)
_DOCKERFILE_SUFFIX = re.compile(r".*\.(dockerfile|containerfile)$", re.IGNORECASE)
_COMPOSE_NAMES = re.compile(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$", re.IGNORECASE)
_INSTRUCTION_LINE = re.compile(r"^\s*([A-Za-z]+)\s+\S")


@dataclass(frozen=True)
class Detection:
    kind: ArtifactKind
    confidence: float
    reason: str


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def _dockerfile_score(content: str) -> tuple[float, int]:
    """Fração das linhas úteis que começam com uma instrução Docker válida."""
    useful = 0
    hits = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        useful += 1
        m = _INSTRUCTION_LINE.match(stripped)
        if m and m.group(1).upper() in KNOWN_INSTRUCTIONS:
            hits += 1
    if useful == 0:
        return 0.0, 0
    return hits / useful, hits


def detect(content: str, filename: str = "") -> Detection:
    name = _basename(filename)
    name_is_dockerfile = bool(_DOCKERFILE_NAMES.match(name) or _DOCKERFILE_SUFFIX.match(name))

    # 1. Dockerfile: um FROM/ARG no topo e densidade alta de instruções.
    score, hits = _dockerfile_score(content)
    if hits > 0 and score >= 0.6:
        confidence = min(0.99, 0.6 + score * 0.35 + (0.05 if name_is_dockerfile else 0.0))
        return Detection(
            ArtifactKind.DOCKERFILE,
            round(confidence, 2),
            f"{hits} instruções Docker reconhecidas ({score:.0%} das linhas úteis)",
        )

    # 2. YAML: o conteúdo distingue Compose de Kubernetes com precisão.
    try:
        docs = [d for d in yaml.safe_load_all(content) if isinstance(d, dict)]
    except yaml.YAMLError:
        docs = []

    if docs:
        k8s_docs = [d for d in docs if "apiVersion" in d and "kind" in d]
        if k8s_docs:
            kinds = ", ".join(sorted({str(d.get("kind")) for d in k8s_docs}))
            return Detection(
                ArtifactKind.KUBERNETES,
                0.97,
                f"{len(k8s_docs)} documento(s) com apiVersion/kind ({kinds})",
            )
        if any("services" in d for d in docs):
            confidence = 0.95 if _COMPOSE_NAMES.match(name) else 0.85
            return Detection(
                ArtifactKind.DOCKER_COMPOSE, confidence, "chave `services` na raiz do YAML"
            )

    # 3. Sem sinal no conteúdo: o nome é o último recurso, com confiança baixa.
    if name_is_dockerfile:
        return Detection(
            ArtifactKind.DOCKERFILE, 0.4, f"nome `{name}`, mas o conteúdo não confirma"
        )
    if _COMPOSE_NAMES.match(name):
        return Detection(
            ArtifactKind.DOCKER_COMPOSE, 0.4, f"nome `{name}`, mas o conteúdo não confirma"
        )

    return Detection(ArtifactKind.UNKNOWN, 0.0, "nenhum formato reconhecido")
