"""Modelo normalizado.

Dockerfile, docker-compose e manifestos Kubernetes descrevem a mesma coisa por
baixo: uma carga de trabalho com imagem, usuário, capabilities, montagens,
portas e limites. Normalizar para `Workload` permite que uma regra como
"não roda como root" seja escrita uma vez e valha para as três fontes.

O que é específico de cada formato (stages do Dockerfile, docs do Kubernetes)
fica preservado em campos próprios, para as regras que precisam dessa fidelidade.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# Ordem para ranquear achados. Maior = mais grave.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}


class ArtifactKind(StrEnum):
    DOCKERFILE = "dockerfile"
    DOCKER_COMPOSE = "docker_compose"
    KUBERNETES = "kubernetes"
    UNKNOWN = "unknown"


class WorkloadKind(StrEnum):
    BUILD_STAGE = "build_stage"
    COMPOSE_SERVICE = "compose_service"
    CONTAINER = "container"
    INIT_CONTAINER = "init_container"


class MountType(StrEnum):
    BIND = "bind"
    VOLUME = "volume"
    TMPFS = "tmpfs"
    HOST_PATH = "host_path"
    CONFIG_MAP = "config_map"
    SECRET = "secret"
    EMPTY_DIR = "empty_dir"
    PROJECTED = "projected"
    OTHER = "other"


class SourceLocation(BaseModel):
    """Onde o achado está no arquivo original. `pointer` é o caminho lógico
    (ex.: `services.api.privileged`), útil quando a linha não basta."""

    model_config = ConfigDict(frozen=True)

    file: str
    start_line: int | None = None
    end_line: int | None = None
    pointer: str | None = None


_IMAGE_RE = re.compile(
    r"^(?:(?P<registry>[a-zA-Z0-9.\-]+(?::\d+)?)/)?"
    r"(?P<repository>[a-zA-Z0-9._\-/]+?)"
    r"(?::(?P<tag>[a-zA-Z0-9._\-]+))?"
    r"(?:@(?P<digest>[a-zA-Z0-9]+:[a-zA-Z0-9]+))?$"
)

# Tags que mudam debaixo do pé: reconstruir hoje e amanhã dá imagens diferentes.
MUTABLE_TAGS = frozenset(
    {"latest", "edge", "stable", "main", "master", "dev", "devel", "test", "nightly"}
)


class ImageRef(BaseModel):
    """Referência de imagem decomposta."""

    model_config = ConfigDict(frozen=True)

    raw: str
    registry: str | None = None
    repository: str = ""
    tag: str | None = None
    digest: str | None = None

    # Derivados no parse (e não como @property) para irem ao JSON do relatório.
    pinned_by_digest: bool = False
    mutable_tag: bool = False
    tag_omitted: bool = False
    is_scratch: bool = False
    # `FROM builder` num multi-stage não é uma imagem externa.
    is_stage_ref: bool = False
    templated: bool = False

    @classmethod
    def parse(cls, raw: str, known_stages: frozenset[str] = frozenset()) -> ImageRef:
        raw = (raw or "").strip()
        low = raw.lower()

        if low in known_stages:
            return cls(raw=raw, repository=low, is_stage_ref=True)
        if low == "scratch":
            return cls(raw=raw, repository="scratch", is_scratch=True)

        # `${VERSION}` / `$TAG` — não dá para avaliar estaticamente.
        if "$" in raw or "{{" in raw:
            return cls(raw=raw, repository=raw, templated=True)

        m = _IMAGE_RE.match(raw)
        if not m:
            return cls(raw=raw, repository=raw)

        registry = m.group("registry")
        repository = m.group("repository") or ""
        tag = m.group("tag")
        digest = m.group("digest")

        # O regex trata "localhost/foo" e "meu-host:5000/foo"; um primeiro
        # segmento sem ponto nem porta é namespace do Docker Hub, não registry.
        if registry and "." not in registry and ":" not in registry and registry != "localhost":
            repository = f"{registry}/{repository}"
            registry = None

        return cls(
            raw=raw,
            registry=registry,
            repository=repository,
            tag=tag,
            digest=digest,
            pinned_by_digest=bool(digest),
            mutable_tag=bool(tag) and tag.lower() in MUTABLE_TAGS,
            tag_omitted=tag is None and digest is None,
        )


class EnvVar(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    value: str | None = None
    location: SourceLocation | None = None
    # True quando vem de secretKeyRef/configMapKeyRef: o valor não está no arquivo.
    from_reference: bool = False


class PortBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    container_port: int | None = None
    host_port: int | None = None
    host_ip: str | None = None
    protocol: str = "tcp"
    raw: str | None = None


class VolumeMount(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    source: str | None = None
    type: MountType = MountType.OTHER
    read_only: bool | None = None
    raw: str | None = None


class SecurityPosture(BaseModel):
    """Postura de segurança normalizada.

    `None` significa **não declarado** — diferente de `False`. A distinção
    importa: `privileged: false` é uma decisão explícita; ausente é omissão,
    e várias regras existem justamente para cobrar o explícito.
    """

    privileged: bool | None = None
    run_as_user: str | None = None
    run_as_group: str | None = None
    run_as_non_root: bool | None = None
    read_only_root_fs: bool | None = None
    allow_privilege_escalation: bool | None = None
    no_new_privileges: bool | None = None
    cap_add: list[str] = Field(default_factory=list)
    cap_drop: list[str] = Field(default_factory=list)
    host_network: bool | None = None
    host_pid: bool | None = None
    host_ipc: bool | None = None
    seccomp_profile: str | None = None
    apparmor_profile: str | None = None


class ResourceLimits(BaseModel):
    cpu_limit: str | None = None
    memory_limit: str | None = None
    cpu_request: str | None = None
    memory_request: str | None = None

    def has_any_limit(self) -> bool:
        return bool(self.cpu_limit or self.memory_limit)


class Workload(BaseModel):
    """Unidade auditável, comum aos três formatos."""

    name: str
    kind: WorkloadKind
    location: SourceLocation
    image: ImageRef | None = None

    entrypoint: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)

    env: list[EnvVar] = Field(default_factory=list)
    ports: list[PortBinding] = Field(default_factory=list)
    mounts: list[VolumeMount] = Field(default_factory=list)

    security: SecurityPosture = Field(default_factory=SecurityPosture)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)

    # "healthcheck" (Docker/Compose) ou liveness/readiness/startup (Kubernetes).
    probes: list[str] = Field(default_factory=list)

    # Só Dockerfile: apenas o último stage vira imagem final.
    is_final_stage: bool = False
    # Só Kubernetes.
    namespace: str | None = None
    owner_kind: str | None = None
    service_account: str | None = None
    automount_sa_token: bool | None = None


# --------------------------------------------------------------------------
# Detalhe específico de cada formato
# --------------------------------------------------------------------------


class DockerInstruction(BaseModel):
    keyword: str
    value: str
    flags: dict[str, str] = Field(default_factory=dict)
    start_line: int
    end_line: int
    raw: str
    stage_index: int | None = None
    # CMD/ENTRYPOINT/RUN em forma JSON (exec) vs. shell.
    json_form: bool = False


class DockerStage(BaseModel):
    index: int
    name: str | None
    base: ImageRef
    start_line: int
    is_final: bool = False
    instructions: list[DockerInstruction] = Field(default_factory=list)


class DockerfileSpec(BaseModel):
    directives: dict[str, str] = Field(default_factory=dict)
    stages: list[DockerStage] = Field(default_factory=list)
    instructions: list[DockerInstruction] = Field(default_factory=list)


class ComposeSpec(BaseModel):
    version: str | None = None
    service_names: list[str] = Field(default_factory=list)
    volume_names: list[str] = Field(default_factory=list)
    network_names: list[str] = Field(default_factory=list)
    secret_names: list[str] = Field(default_factory=list)


class K8sDocument(BaseModel):
    api_version: str | None = None
    kind: str | None = None
    name: str | None = None
    namespace: str | None = None
    location: SourceLocation
    is_workload: bool = False


class ParsedArtifact(BaseModel):
    """Saída do parse: o arquivo normalizado, sem nenhum julgamento ainda."""

    kind: ArtifactKind
    path: str
    sha256: str
    size_bytes: int
    detection_confidence: float = 0.0
    detection_reason: str = ""

    workloads: list[Workload] = Field(default_factory=list)

    dockerfile: DockerfileSpec | None = None
    compose: ComposeSpec | None = None
    documents: list[K8sDocument] = Field(default_factory=list)

    # Falhas de parse que não impedem a análise (ex.: um doc YAML inválido
    # dentro de um arquivo multi-doc).
    parse_errors: list[str] = Field(default_factory=list)
