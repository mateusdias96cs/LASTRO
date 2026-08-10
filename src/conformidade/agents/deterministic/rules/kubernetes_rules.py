"""Regras específicas de Kubernetes.

Só o que não existe nos outros formatos; privileged, hostPath, capabilities,
root e limites estão em `workload_rules`.
"""

from __future__ import annotations

from collections.abc import Iterator

from conformidade.agents.deterministic.models import ArtifactKind, ParsedArtifact, Severity
from conformidade.agents.deterministic.rules.base import Observation, registry

K8S_ONLY = (ArtifactKind.KUBERNETES,)

VALID_SECCOMP_TYPES = frozenset({"RuntimeDefault", "Localhost"})


@registry.register(
    control_id="CONF-K8S-001",
    title="Escalada de privilégio permitida",
    severity=Severity.HIGH,
    applies_to=K8S_ONLY,
    rationale=(
        "Com `allowPrivilegeEscalation` diferente de false, um binário setuid deixa o "
        "processo obter privilégios além dos concedidos na criação do container. O "
        "PodSecurityStandard `restricted` rejeita o pod sem esse campo em false."
    ),
    remediation="Defina `securityContext.allowPrivilegeEscalation: false` no container.",
    framework_refs=("CIS Kubernetes Benchmark — 5.2.6",),
)
def rule_k8s_allow_privilege_escalation(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        if w.security.allow_privilege_escalation is not False:
            declared = w.security.allow_privilege_escalation
            yield Observation(
                message=(
                    "allowPrivilegeEscalation não está em false "
                    f"({'ausente' if declared is None else declared})."
                ),
                location=w.location,
                target=w.name,
                evidence=(
                    f"allowPrivilegeEscalation: {declared if declared is not None else '(ausente)'}"
                ),
            )


@registry.register(
    control_id="CONF-K8S-002",
    title="Perfil seccomp não definido",
    severity=Severity.MEDIUM,
    applies_to=K8S_ONLY,
    rationale=(
        "Sem seccomp o container pode emitir qualquer syscall, inclusive as usadas em "
        "exploits de kernel. `RuntimeDefault` bloqueia as perigosas sem custo prático."
    ),
    remediation="Defina `securityContext.seccompProfile.type: RuntimeDefault`.",
)
def rule_k8s_seccomp(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        profile = w.security.seccomp_profile
        if profile not in VALID_SECCOMP_TYPES:
            yield Observation(
                message=(f"Nenhum perfil seccomp válido definido ({profile or 'ausente'})."),
                location=w.location,
                target=w.name,
                evidence=f"seccompProfile: {profile or '(ausente)'}",
            )


@registry.register(
    control_id="CONF-K8S-003",
    title="Token da service account montado automaticamente",
    severity=Severity.MEDIUM,
    applies_to=K8S_ONLY,
    rationale=(
        "O token é montado no container por padrão. Uma aplicação que não fala com a "
        "API do Kubernetes não precisa dele — e, se comprometida, o token vira acesso "
        "à API com as permissões da service account."
    ),
    remediation="Defina `automountServiceAccountToken: false` no pod ou na service account.",
)
def rule_k8s_automount_token(artifact: ParsedArtifact) -> Iterator[Observation]:
    seen: set[str] = set()
    for w in artifact.workloads:
        if w.automount_sa_token is False:
            continue
        # A configuração é do pod: reporta uma vez por pod, não por container.
        pod_key = f"{w.owner_kind}/{w.namespace}/{w.name.split('/')[0]}"
        if pod_key in seen:
            continue
        seen.add(pod_key)
        yield Observation(
            message="O pod não desabilita a montagem automática do token da service account.",
            location=w.location,
            target=w.name,
            evidence=f"automountServiceAccountToken: {w.automount_sa_token or '(ausente)'}",
        )


@registry.register(
    control_id="CONF-K8S-004",
    title="Carga de trabalho no namespace default",
    severity=Severity.LOW,
    applies_to=K8S_ONLY,
    rationale=(
        "O namespace default não tem isolamento de RBAC nem de NetworkPolicy definidos "
        "por convenção, e mistura workloads de times diferentes."
    ),
    remediation="Declare um namespace dedicado no manifesto.",
    framework_refs=("CIS Kubernetes Benchmark — 5.7.4",),
)
def rule_k8s_default_namespace(artifact: ParsedArtifact) -> Iterator[Observation]:
    for doc in artifact.documents:
        if not doc.is_workload:
            continue
        if doc.namespace in (None, "", "default"):
            yield Observation(
                message=(
                    f"{doc.kind} `{doc.name}` "
                    + (
                        "não declara namespace."
                        if not doc.namespace
                        else "usa o namespace default."
                    )
                ),
                location=doc.location,
                target=doc.name or doc.kind,
                evidence=f"metadata.namespace: {doc.namespace or '(ausente)'}",
            )


@registry.register(
    control_id="CONF-K8S-005",
    title="hostPort mapeado no nó",
    severity=Severity.MEDIUM,
    applies_to=K8S_ONLY,
    rationale=(
        "hostPort reserva a porta diretamente no nó, contornando Service e "
        "NetworkPolicy, e limita o agendamento a um pod por nó."
    ),
    remediation="Exponha via Service (ClusterIP/LoadBalancer) em vez de hostPort.",
)
def rule_k8s_host_port(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        for port in w.ports:
            if port.host_port:
                yield Observation(
                    message=f"Container mapeia hostPort {port.host_port} no nó.",
                    location=w.location,
                    target=w.name,
                    evidence=f"hostPort: {port.host_port}",
                )
