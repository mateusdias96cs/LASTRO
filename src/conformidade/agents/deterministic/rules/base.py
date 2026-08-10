"""Motor de regras.

Uma regra é um predicado puro sobre o artefato já parseado. Ela devolve
`Observation` (fato observado + onde), e o motor a converte em `Finding`
anexando os metadados do controle. Esse desenho garante que **nenhum achado
existe sem `control_id`** — a chave que o agente de recuperação vai usar.

Regras não fazem I/O, não chamam rede e não dependem de relógio.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from conformidade.agents.deterministic.findings import Finding
from conformidade.agents.deterministic.models import (
    ArtifactKind,
    ParsedArtifact,
    Severity,
    SourceLocation,
)


@dataclass(frozen=True)
class Observation:
    """O que a regra viu. Sem veredito, sem metadado de controle."""

    message: str
    location: SourceLocation
    evidence: str | None = None
    target: str | None = None


CheckFn = Callable[[ParsedArtifact], Iterable[Observation]]


@dataclass(frozen=True)
class Rule:
    control_id: str
    title: str
    severity: Severity
    applies_to: frozenset[ArtifactKind]
    remediation: str
    check: CheckFn
    rationale: str = ""
    framework_refs: tuple[str, ...] = ()

    def run(self, artifact: ParsedArtifact) -> Iterator[Finding]:
        if artifact.kind not in self.applies_to:
            return
        for obs in self.check(artifact):
            yield Finding(
                control_id=self.control_id,
                title=self.title,
                severity=self.severity,
                message=obs.message,
                location=obs.location,
                evidence=obs.evidence,
                target=obs.target,
                remediation=self.remediation,
                framework_refs=self.framework_refs,
                fingerprint=Finding.compute_fingerprint(
                    self.control_id,
                    obs.location.file,
                    obs.target,
                    obs.location.start_line,
                    obs.evidence,
                ),
            )


@dataclass
class RuleRegistry:
    _rules: dict[str, Rule] = field(default_factory=dict)

    def register(
        self,
        *,
        control_id: str,
        title: str,
        severity: Severity,
        applies_to: Iterable[ArtifactKind],
        remediation: str,
        rationale: str = "",
        framework_refs: Iterable[str] = (),
    ) -> Callable[[CheckFn], CheckFn]:
        def decorator(fn: CheckFn) -> CheckFn:
            if control_id in self._rules:
                raise ValueError(f"control_id duplicado: {control_id}")
            self._rules[control_id] = Rule(
                control_id=control_id,
                title=title,
                severity=severity,
                applies_to=frozenset(applies_to),
                remediation=remediation,
                rationale=rationale,
                framework_refs=tuple(framework_refs),
                check=fn,
            )
            return fn

        return decorator

    def for_kind(self, kind: ArtifactKind) -> list[Rule]:
        # Ordenado por control_id: a ordem de avaliação não pode depender da
        # ordem de import dos módulos de regra.
        return sorted(
            (r for r in self._rules.values() if kind in r.applies_to),
            key=lambda r: r.control_id,
        )

    def all(self) -> list[Rule]:
        return sorted(self._rules.values(), key=lambda r: r.control_id)


registry = RuleRegistry()
