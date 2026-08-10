"""Achados candidatos.

"Candidato" é literal: esta camada não afirma não-conformidade, ela aponta
evidência objetiva e o **controle esperado** (`control_id`). Quem busca o texto
do controle no corpus é o agente de recuperação; quem julga o contexto é o de
análise; quem valida a citação é o crítico. Aqui não há LLM nem interpretação.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from conformidade.agents.deterministic.models import SEVERITY_RANK, Severity, SourceLocation


class Finding(BaseModel):
    """Um achado candidato, pronto para ser enriquecido pelos próximos agentes."""

    model_config = ConfigDict(frozen=True)

    # Chave de junção com o corpus do RAG.
    control_id: str
    title: str
    severity: Severity
    message: str
    location: SourceLocation

    # Trecho do arquivo que motivou o achado. Sempre redigido quando o valor
    # pode conter segredo.
    evidence: str | None = None
    # Nome da workload (stage, serviço ou container) quando aplicável.
    target: str | None = None
    remediation: str = ""
    framework_refs: tuple[str, ...] = ()

    # Hash estável do achado: mesma entrada produz o mesmo id, então dá para
    # diferenciar execuções e suprimir achados aceitos sem depender de ordem.
    fingerprint: str = ""

    @staticmethod
    def compute_fingerprint(
        control_id: str, file: str, target: str | None, line: int | None, evidence: str | None
    ) -> str:
        payload = "|".join([control_id, file, target or "", str(line or ""), evidence or ""])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Ordenação total e determinística.

    Sem isso, dois runs sobre o mesmo arquivo poderiam emitir a mesma lista em
    ordens diferentes (dicionários, sets), quebrando a reprodutibilidade byte
    a byte que é a razão de ser desta camada.
    """
    return sorted(
        findings,
        key=lambda f: (
            -SEVERITY_RANK[f.severity],
            f.location.start_line if f.location.start_line is not None else 1 << 30,
            f.control_id,
            f.target or "",
            f.fingerprint,
        ),
    )


class FindingsSummary(BaseModel):
    total: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    controls_triggered: list[str] = Field(default_factory=list)
    rules_evaluated: int = 0
    workloads_analyzed: int = 0

    @classmethod
    def build(
        cls, findings: list[Finding], rules_evaluated: int, workloads: int
    ) -> FindingsSummary:
        by_sev = {s.value: 0 for s in Severity}
        for f in findings:
            by_sev[f.severity.value] += 1
        return cls(
            total=len(findings),
            by_severity=by_sev,
            controls_triggered=sorted({f.control_id for f in findings}),
            rules_evaluated=rules_evaluated,
            workloads_analyzed=workloads,
        )
