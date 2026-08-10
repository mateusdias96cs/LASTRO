"""Regras que operam sobre o modelo normalizado.

Cada uma destas é escrita **uma vez** e vale para Dockerfile, Compose e
Kubernetes conforme o `applies_to`. É o retorno concreto de ter normalizado:
"monta o socket do Docker" é o mesmo risco em `volumes:` do Compose e em
`hostPath` do Kubernetes, e não deveria existir como duas regras divergentes.
"""

from __future__ import annotations

from collections.abc import Iterator

from conformidade.agents.deterministic.models import (
    ArtifactKind,
    ParsedArtifact,
    Severity,
    Workload,
)
from conformidade.agents.deterministic.rules.base import Observation, registry
from conformidade.agents.deterministic.rules.shared import (
    HIGH_RISK_CAPABILITIES,
    ROOT_USER_VALUES,
    detect_secret,
    is_container_socket,
    is_sensitive_host_path,
    redact,
)

ALL_KINDS = (ArtifactKind.DOCKERFILE, ArtifactKind.DOCKER_COMPOSE, ArtifactKind.KUBERNETES)
RUNTIME_KINDS = (ArtifactKind.DOCKER_COMPOSE, ArtifactKind.KUBERNETES)


def _runtime_workloads(artifact: ParsedArtifact) -> Iterator[Workload]:
    """No Dockerfile só o stage final vira runtime; os intermediários são descartados."""
    for w in artifact.workloads:
        if artifact.kind == ArtifactKind.DOCKERFILE and not w.is_final_stage:
            continue
        yield w


# --------------------------------------------------------------------------
# Cadeia de suprimentos: procedência da imagem
# --------------------------------------------------------------------------


@registry.register(
    control_id="CONF-IMG-001",
    title="Imagem sem tag explícita",
    severity=Severity.HIGH,
    applies_to=ALL_KINDS,
    rationale="Sem tag o runtime assume `latest`, que aponta para conteúdo diferente a "
    "cada pull. O que foi auditado não é necessariamente o que vai executar.",
    remediation="Declare a tag e, de preferência, fixe também o digest.",
)
def rule_image_no_tag(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        img = w.image
        if img and not img.is_stage_ref and not img.is_scratch and not img.templated:
            if img.tag_omitted:
                yield Observation(
                    message=f"`{img.raw}` não declara tag; o runtime resolverá para `latest`.",
                    location=w.location,
                    target=w.name,
                    evidence=img.raw,
                )


@registry.register(
    control_id="CONF-IMG-002",
    title="Imagem referenciada por tag mutável",
    severity=Severity.HIGH,
    applies_to=ALL_KINDS,
    rationale="Tags como `latest` e `stable` são móveis: o mesmo manifesto entrega "
    "conteúdo diferente em dois deploys, quebrando reprodutibilidade e rastreabilidade.",
    remediation="Use tag de versão imutável e fixe o digest (`imagem:1.2.3@sha256:...`).",
)
def rule_image_mutable_tag(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        img = w.image
        if img and img.mutable_tag and not img.pinned_by_digest:
            yield Observation(
                message=f"`{img.raw}` usa a tag mutável `{img.tag}`.",
                location=w.location,
                target=w.name,
                evidence=img.raw,
            )


@registry.register(
    control_id="CONF-IMG-003",
    title="Imagem não fixada por digest",
    severity=Severity.MEDIUM,
    applies_to=ALL_KINDS,
    rationale="Só o digest identifica o conteúdo de forma imutável. Tag de versão pode "
    "ser reapontada no registry sem que nada no repositório mude.",
    remediation="Fixe `@sha256:...` e automatize a atualização.",
)
def rule_image_not_pinned(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in artifact.workloads:
        img = w.image
        if not img or img.is_stage_ref or img.is_scratch or img.templated:
            continue
        # Sem tag ou com tag mutável já foi reportado com severidade maior.
        if img.tag_omitted or img.mutable_tag:
            continue
        if not img.pinned_by_digest:
            yield Observation(
                message=f"`{img.raw}` não fixa digest.",
                location=w.location,
                target=w.name,
                evidence=img.raw,
            )


# --------------------------------------------------------------------------
# Isolamento
# --------------------------------------------------------------------------


@registry.register(
    control_id="CONF-WLD-001",
    title="Container em modo privilegiado",
    severity=Severity.CRITICAL,
    applies_to=RUNTIME_KINDS,
    rationale="Privileged desliga praticamente todo o isolamento: o container recebe "
    "todas as capabilities e acesso aos devices do host. Escapar é trivial.",
    remediation="Remova `privileged`. Se precisar de um device específico, conceda só ele.",
    framework_refs=("CIS Docker Benchmark — 5.4", "CIS Kubernetes Benchmark — 5.2.2"),
)
def rule_privileged(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        if w.security.privileged is True:
            yield Observation(
                message="Executa em modo privilegiado.",
                location=w.location,
                target=w.name,
                evidence="privileged: true",
            )


@registry.register(
    control_id="CONF-WLD-002",
    title="Socket do runtime de container montado",
    severity=Severity.CRITICAL,
    applies_to=RUNTIME_KINDS,
    rationale=(
        "Acesso ao socket do Docker/containerd equivale a root no host: quem tem o "
        "socket cria um container privilegiado montando `/` e sai do isolamento."
    ),
    remediation="Remova a montagem. Se precisar de build dentro do cluster, use uma "
    "solução sem daemon privilegiado e com escopo restrito.",
    framework_refs=("CIS Docker Benchmark — 5.31",),
)
def rule_container_socket(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        for mount in w.mounts:
            if is_container_socket(mount.source) or is_container_socket(mount.target):
                yield Observation(
                    message=f"Monta o socket do runtime (`{mount.source or mount.target}`).",
                    location=w.location,
                    target=w.name,
                    evidence=mount.raw or f"{mount.source} -> {mount.target}",
                )


@registry.register(
    control_id="CONF-WLD-003",
    title="Caminho sensível do host montado no container",
    severity=Severity.HIGH,
    applies_to=RUNTIME_KINDS,
    rationale="Montar /etc, /proc, /var/run ou a raiz do host dá ao container leitura "
    "(e às vezes escrita) sobre a configuração e o estado da máquina.",
    remediation="Monte apenas o subdiretório necessário e em modo somente-leitura.",
)
def rule_sensitive_host_mount(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        for mount in w.mounts:
            if is_container_socket(mount.source):
                continue  # já coberto, com severidade maior, por CONF-WLD-002
            matched = is_sensitive_host_path(mount.source)
            if matched:
                mode = "somente-leitura" if mount.read_only else "leitura e escrita"
                yield Observation(
                    message=(
                        f"Monta o caminho do host `{mount.source}` (sensível: `{matched}`) "
                        f"em `{mount.target}` com {mode}."
                    ),
                    location=w.location,
                    target=w.name,
                    evidence=mount.raw or f"{mount.source}:{mount.target}",
                )


@registry.register(
    control_id="CONF-WLD-004",
    title="Namespace do host compartilhado",
    severity=Severity.HIGH,
    applies_to=RUNTIME_KINDS,
    rationale="Compartilhar rede, PID ou IPC do host remove a fronteira entre container "
    "e máquina: dá para enxergar processos do host, sniffar tráfego e acessar serviços locais.",
    remediation="Remova hostNetwork/hostPID/hostIPC (ou network_mode: host, pid: host).",
    framework_refs=(
        "CIS Docker Benchmark — 5.9",
        "CIS Kubernetes Benchmark — 5.2.3, 5.2.4, 5.2.5",
    ),
)
def rule_host_namespaces(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        sec = w.security
        for label, enabled in (
            ("rede (hostNetwork)", sec.host_network),
            ("processos (hostPID)", sec.host_pid),
            ("IPC (hostIPC)", sec.host_ipc),
        ):
            if enabled is True:
                yield Observation(
                    message=f"Compartilha o namespace de {label} com o host.",
                    location=w.location,
                    target=w.name,
                    evidence=label,
                )


@registry.register(
    control_id="CONF-WLD-005",
    title="Capability de alto risco concedida",
    severity=Severity.HIGH,
    applies_to=RUNTIME_KINDS,
    rationale="Capabilities como SYS_ADMIN ou SYS_PTRACE permitem manipular o kernel e "
    "outros processos; várias delas são caminho conhecido de fuga de container.",
    remediation="Conceda apenas a capability estritamente necessária, nunca ALL.",
    framework_refs=("CIS Kubernetes Benchmark — 5.2.9",),
)
def rule_dangerous_capabilities(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        risky = sorted(set(w.security.cap_add) & HIGH_RISK_CAPABILITIES)
        for cap in risky:
            yield Observation(
                message=f"Concede a capability de alto risco `{cap}`.",
                location=w.location,
                target=w.name,
                evidence=f"cap_add: {cap}",
            )


@registry.register(
    control_id="CONF-WLD-006",
    title="Capabilities não são descartadas por padrão",
    severity=Severity.MEDIUM,
    applies_to=RUNTIME_KINDS,
    rationale="Por padrão o runtime concede um conjunto de capabilities que a maioria "
    "das aplicações não usa. Descartar tudo e readicionar o necessário é o caminho seguro.",
    remediation="Declare `cap_drop: [ALL]` (Compose) ou "
    "`securityContext.capabilities.drop: [ALL]` (Kubernetes).",
    framework_refs=("CIS Kubernetes Benchmark — 5.2.10",),
)
def rule_capabilities_not_dropped(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        if "ALL" not in w.security.cap_drop:
            yield Observation(
                message="Não descarta todas as capabilities antes de readicionar o necessário.",
                location=w.location,
                target=w.name,
                evidence=f"cap_drop: {w.security.cap_drop or '(ausente)'}",
            )


@registry.register(
    control_id="CONF-WLD-007",
    title="Container executa como root",
    severity=Severity.HIGH,
    applies_to=RUNTIME_KINDS,
    rationale="Root no container amplifica qualquer outra falha: uma escrita indevida "
    "em volume montado ou uma fuga passam a ter privilégio total.",
    remediation="Defina um UID não-zero (`user:` no Compose, `runAsUser`/`runAsNonRoot` "
    "no Kubernetes).",
    framework_refs=("CIS Docker Benchmark — 4.1", "CIS Kubernetes Benchmark — 5.2.7"),
)
def rule_runs_as_root(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        sec = w.security
        if sec.run_as_non_root is True:
            continue
        if sec.run_as_user is not None and sec.run_as_user.lower() not in ROOT_USER_VALUES:
            continue

        if sec.run_as_user is None:
            message = (
                "Não declara usuário; o container roda com o usuário da imagem, "
                "que por padrão é root."
            )
            evidence = "user/runAsUser ausente"
        else:
            message = f"Declara execução como root (`{sec.run_as_user}`)."
            evidence = f"runAsUser: {sec.run_as_user}"
        yield Observation(message=message, location=w.location, target=w.name, evidence=evidence)


@registry.register(
    control_id="CONF-WLD-008",
    title="Sistema de arquivos raiz gravável",
    severity=Severity.MEDIUM,
    applies_to=RUNTIME_KINDS,
    rationale="Raiz gravável permite que um atacante grave binário ou webshell dentro do "
    "container e persista entre reinícios do processo.",
    remediation="Ative a raiz somente-leitura e monte um tmpfs nos diretórios que "
    "realmente precisam de escrita.",
    framework_refs=("CIS Docker Benchmark — 5.12",),
)
def rule_writable_root_fs(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        if w.security.read_only_root_fs is not True:
            yield Observation(
                message="Não declara o sistema de arquivos raiz como somente-leitura.",
                location=w.location,
                target=w.name,
                evidence="read_only/readOnlyRootFilesystem ausente ou false",
            )


# --------------------------------------------------------------------------
# Disponibilidade e segredos
# --------------------------------------------------------------------------


@registry.register(
    control_id="CONF-WLD-009",
    title="Sem limite de CPU ou memória",
    severity=Severity.MEDIUM,
    applies_to=RUNTIME_KINDS,
    rationale="Sem limite, um container consome todo o recurso do nó e derruba os "
    "vizinhos — negação de serviço por ruído, sem precisar de atacante.",
    remediation="Defina limites de CPU e memória (`deploy.resources.limits` ou "
    "`resources.limits`).",
    framework_refs=("CIS Docker Benchmark — 5.10, 5.11",),
)
def rule_no_resource_limits(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        missing = []
        if not w.resources.cpu_limit:
            missing.append("CPU")
        if not w.resources.memory_limit:
            missing.append("memória")
        if missing:
            yield Observation(
                message=f"Sem limite de {' e '.join(missing)}.",
                location=w.location,
                target=w.name,
                evidence="resources.limits ausente",
            )


@registry.register(
    control_id="CONF-WLD-010",
    title="Sem verificação de saúde",
    severity=Severity.LOW,
    applies_to=RUNTIME_KINDS,
    rationale="Sem probe, o orquestrador considera saudável um container que já não "
    "atende, e continua enviando tráfego para ele.",
    remediation="Declare healthcheck (Compose) ou liveness/readiness probes (Kubernetes).",
)
def rule_no_probes(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        # initContainer roda e termina: probe não se aplica.
        if w.kind.value == "init_container":
            continue
        if not w.probes:
            yield Observation(
                message="Nenhuma verificação de saúde declarada.",
                location=w.location,
                target=w.name,
                evidence="healthcheck/probes ausentes",
            )


@registry.register(
    control_id="CONF-SEC-001",
    title="Segredo literal em variável de ambiente",
    severity=Severity.CRITICAL,
    applies_to=RUNTIME_KINDS,
    rationale=(
        "Variável de ambiente com segredo vaza por vários caminhos ao mesmo tempo: "
        "`docker inspect`, `kubectl describe`, dump de processo, log de crash e o "
        "próprio arquivo versionado no repositório."
    ),
    remediation="Injete via secret do orquestrador ou referência ao Key Vault; no "
    "Compose use `secrets:` em vez de `environment:`.",
    framework_refs=("CIS Docker Benchmark — 4.10",),
)
def rule_secret_in_env(artifact: ParsedArtifact) -> Iterator[Observation]:
    for w in _runtime_workloads(artifact):
        for var in w.env:
            if var.from_reference:
                continue  # secretKeyRef: o valor não está no arquivo
            reason = detect_secret(var.name, var.value)
            if reason:
                yield Observation(
                    message=f"Variável `{var.name}` — {reason}.",
                    location=var.location or w.location,
                    target=w.name,
                    evidence=f"{var.name}={redact(var.value or '')}",
                )
