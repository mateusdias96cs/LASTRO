"""Camada determinística: detectar → parsear → checar.

Sem LLM, sem rede, sem relógio. A mesma entrada produz o mesmo relatório byte a
byte — propriedade verificada em teste, não apenas afirmada aqui. É o que
permite usar esta camada como linha de base: se o relatório mudou, foi o
arquivo que mudou (ou o conjunto de regras, e aí `ruleset_version` muda junto).

O relatório propositalmente **não** carrega timestamp nem duração: qualquer
campo de relógio quebraria a reprodutibilidade que justifica esta camada. Quem
precisa medir tempo mede em volta.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

from conformidade.agents.deterministic.detector import Detection, detect
from conformidade.agents.deterministic.findings import Finding, FindingsSummary, sort_findings
from conformidade.agents.deterministic.models import ArtifactKind, ParsedArtifact
from conformidade.agents.deterministic.parsers import (
    parse_compose,
    parse_dockerfile,
    parse_kubernetes,
)
from conformidade.agents.deterministic.rules import registry
from conformidade.agents.deterministic.sanitize import sanitize

ENGINE_NAME = "conformidade.deterministic"
ENGINE_VERSION = "1.0.0"


def ruleset_version() -> str:
    """Derivado do conteúdo do conjunto de regras.

    Calcular em vez de manter à mão garante que a versão muda sozinha quando uma
    regra é adicionada ou tem a severidade alterada — sem isso, dois relatórios
    diferentes poderiam alegar a mesma versão de ruleset.
    """
    payload = ";".join(f"{r.control_id}:{r.severity.value}" for r in registry.all())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


class ControlDescriptor(BaseModel):
    """Catálogo exportável — é o que o corpus do RAG vai indexar."""

    control_id: str
    title: str
    severity: str
    applies_to: list[str]
    rationale: str
    remediation: str
    framework_refs: list[str]


class DeterministicReport(BaseModel):
    engine: str = ENGINE_NAME
    engine_version: str = ENGINE_VERSION
    ruleset_version: str = ""
    artifact: ParsedArtifact
    findings: list[Finding] = Field(default_factory=list)
    summary: FindingsSummary = Field(default_factory=FindingsSummary)


def list_controls() -> list[ControlDescriptor]:
    return [
        ControlDescriptor(
            control_id=r.control_id,
            title=r.title,
            severity=r.severity.value,
            applies_to=sorted(k.value for k in r.applies_to),
            rationale=r.rationale,
            remediation=r.remediation,
            framework_refs=list(r.framework_refs),
        )
        for r in registry.all()
    ]


def _decode(content: str | bytes) -> tuple[str, bytes]:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace"), content
    return content, content.encode("utf-8")


def parse(content: str | bytes, filename: str = "<stdin>") -> ParsedArtifact:
    """Detecta o formato e normaliza. Não avalia nada."""
    text, raw = _decode(content)
    detection: Detection = detect(text, filename)

    artifact = ParsedArtifact(
        kind=detection.kind,
        path=filename,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        detection_confidence=detection.confidence,
        detection_reason=detection.reason,
    )

    if detection.kind == ArtifactKind.DOCKERFILE:
        spec, workloads = parse_dockerfile(text, filename)
        artifact.dockerfile = spec
        artifact.workloads = workloads
        if not spec.stages:
            artifact.parse_errors.append("nenhuma instrução FROM encontrada")

    elif detection.kind == ArtifactKind.DOCKER_COMPOSE:
        spec, workloads, errors = parse_compose(text, filename)
        artifact.compose = spec
        artifact.workloads = workloads
        artifact.parse_errors.extend(errors)

    elif detection.kind == ArtifactKind.KUBERNETES:
        documents, workloads, errors = parse_kubernetes(text, filename)
        artifact.documents = documents
        artifact.workloads = workloads
        artifact.parse_errors.extend(errors)

    else:
        artifact.parse_errors.append(
            "formato não reconhecido: esperado Dockerfile, docker-compose ou manifesto Kubernetes"
        )

    return artifact


def evaluate(artifact: ParsedArtifact) -> tuple[list[Finding], int]:
    """Roda as regras aplicáveis. Devolve os achados e quantas regras rodaram."""
    rules = registry.for_kind(artifact.kind)
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(rule.run(artifact))
    return sort_findings(findings), len(rules)


def analyze(content: str | bytes, filename: str = "<stdin>") -> DeterministicReport:
    """Ponto de entrada: arquivo do usuário → estrutura parseada + achados.

    A ordem importa: as regras avaliam o artefato com os valores em claro e só
    depois ele é sanitizado. Inverter isso cegaria a detecção de segredo;
    omitir a sanitização faria o segredo sair no relatório.
    """
    artifact = parse(content, filename)
    findings, rules_evaluated = evaluate(artifact)
    artifact = sanitize(artifact)
    return DeterministicReport(
        ruleset_version=ruleset_version(),
        artifact=artifact,
        findings=findings,
        summary=FindingsSummary.build(findings, rules_evaluated, len(artifact.workloads)),
    )


def analyze_path(path: str | Path) -> DeterministicReport:
    p = Path(path)
    return analyze(p.read_bytes(), p.name)
