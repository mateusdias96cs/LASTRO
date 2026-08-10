"""Agente determinístico — primeira camada do pipeline de conformidade.

Detecta o tipo do arquivo, parseia para o modelo normalizado e roda um conjunto
fixo de checagens. Sem LLM: rápida, barata e reprodutível.

A saída são **achados candidatos**, cada um com o `control_id` que os próximos
agentes vão usar — o de recuperação para buscar o controle no corpus, o de
análise para avaliar o contexto, o crítico para validar citação e coerência.
"""

from conformidade.agents.deterministic.agent import (
    ENGINE_NAME,
    ENGINE_VERSION,
    ControlDescriptor,
    DeterministicReport,
    analyze,
    analyze_path,
    evaluate,
    list_controls,
    parse,
    ruleset_version,
)
from conformidade.agents.deterministic.findings import Finding, FindingsSummary
from conformidade.agents.deterministic.models import (
    ArtifactKind,
    ParsedArtifact,
    Severity,
    Workload,
)

__all__ = [
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "ArtifactKind",
    "ControlDescriptor",
    "DeterministicReport",
    "Finding",
    "FindingsSummary",
    "ParsedArtifact",
    "Severity",
    "Workload",
    "analyze",
    "analyze_path",
    "evaluate",
    "list_controls",
    "parse",
    "ruleset_version",
]
